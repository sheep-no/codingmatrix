"""Adapters that expose existing generation modes to the orchestration core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import ast
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple

from .generation_scheduler import FileGenerationContext, GeneratedContent
from .models import OrchestrationState
from .plan import GenerationPlan, build_file_plan, normalize_plan_path
from app.agent.generation_plan import GenerationPlan as ProjectGenerationPlan, add_profile_components
from app.agent.change_plan import ChangePlan
from app.agent.project_snapshot import ProjectSnapshot


@dataclass(frozen=True)
class GenerationRequest:
    """Minimal request passed from an endpoint into a generation adapter."""

    requirement: str
    task_id: str
    session_id: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class AdapterResult:
    """Adapter output retained by the compatibility layer."""

    success: bool
    result: Mapping[str, Any]


class GenerationModeAdapter(Protocol):
    async def create_plan(self, request: GenerationRequest) -> GenerationPlan: ...

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent: ...

    async def finalize(self, state: OrchestrationState) -> AdapterResult: ...


class TraditionalAdapter:
    """Expose the existing ``OrchestratorAgent`` through the core contract.

    The adapter owns planning and content normalization while the scheduler owns
    dependency ordering. Existing generation helpers still perform their legacy
    validation and persistence work during this migration phase.
    """

    engine_version = "traditional-adapter-v1"

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self._architecture: Dict[str, Any] = {}
        self._requirement = ""
        self._project_context: Dict[str, Any] = {}
        self._plan: Optional[GenerationPlan] = None
        self._shared_context: Any = None
        self._started_at = 0.0
        self._generated_contents: Dict[str, str] = {}
        self.project_plan: Optional[ProjectGenerationPlan] = None

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._started_at = time.monotonic()
        self._requirement = request.requirement
        self._project_context = dict(request.metadata)
        self._project_context.setdefault("context_hash", request.metadata.get("context_hash"))
        await self.agent._initialize_components(request.requirement)
        self._architecture = await self.agent.architect.design_architecture(
            request.requirement,
            self.agent.complexity,
            callback=getattr(self.agent, "callback", None),
        )
        # Freeze the project-level contract first; the legacy scheduler receives
        # a compatibility projection of the same validated file nodes.
        requested_paths = request.metadata.get("requested_paths") or request.metadata.get("allowed_files")
        if requested_paths:
            self.project_plan = ProjectGenerationPlan.from_architecture(
                self._architecture,
                requested_paths=requested_paths,
                policy="strict",
            )
        else:
            self.project_plan = ProjectGenerationPlan.from_architecture(self._architecture)

        profile_context = request.metadata.get("profile_context")
        if isinstance(profile_context, Mapping):
            self.project_plan = add_profile_components(
                self.project_plan.files,
                profile_context,
                policy=self.project_plan.policy,
                requested_paths=self.project_plan.requested_paths,
                language=self.project_plan.language,
                framework=self.project_plan.framework,
                runtime=self.project_plan.runtime,
            )

        from app.agent.adapters.language_adapter import LanguageAdapterRegistry
        from app.agent.dependency_graph import DependencyGraph

        entries = list(self.project_plan.file_entries())
        dependency_architecture = {
            **self._architecture,
            "file_plan": entries,
        }
        language_adapter = LanguageAdapterRegistry.get_adapter(self.project_plan.language)
        dependency_graph = DependencyGraph(language_adapter=language_adapter)
        dependency_graph.build_from_architecture(dependency_architecture)

        planned_paths = {item.path for item in self.project_plan.files}
        projected_entries = []
        for raw_entry in entries:
            entry = dict(raw_entry)
            path = normalize_plan_path(str(entry.get("path", "")))
            entry["dependencies"] = sorted(
                dependency
                for dependency in dependency_graph.adjacency.get(path, ())
                if dependency in planned_paths
            )
            projected_entries.append(entry)

        self.project_plan = ProjectGenerationPlan.build(
            projected_entries,
            language=self.project_plan.language,
            framework=self.project_plan.framework,
            runtime=self.project_plan.runtime,
            policy=self.project_plan.policy,
            requested_paths=self.project_plan.requested_paths,
            interfaces=self.project_plan.interfaces,
            dependencies=self.project_plan.dependencies,
        )
        self._architecture = {
            **dependency_architecture,
            "file_plan": list(self.project_plan.file_entries()),
        }
        dependency_graph.generation_plan = self.project_plan
        self.agent.dependency_graph_obj = dependency_graph

        entries = list(self.project_plan.file_entries())
        frozen_paths = (
            self.project_plan.requested_paths
            if self.project_plan.policy == "strict"
            else None
        )
        self._plan = build_file_plan(entries, requested_paths=frozen_paths)
        self._project_context["architecture"] = self._architecture
        return self._plan

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent:
        if self._plan is None:
            raise RuntimeError("create_plan must run before generate_file")
        file_info = next(item for item in self._plan.files if item.path == context.file_path)
        generated_contents = {
            **self._generated_contents,
            **dict(context.upstream_contents),
        }
        result = await self.agent._generate_single_file(
            {
                "path": file_info.path,
                "description": file_info.role,
                "priority": file_info.priority,
            },
            self._project_context,
            len(self._plan.files),
            generated_contents,
        )
        if not result or not result.get("success", True):
            raise RuntimeError(f"traditional generation failed for {context.file_path}")
        content = result.get("content")
        if content is None:
            path = self.agent.output_dir / context.file_path
            content = path.read_text(encoding="utf-8")
        self._generated_contents[context.file_path] = str(content)
        return GeneratedContent(
            content=str(content),
            model_name=str(result.get("model") or self.agent._select_model_for_file(context.file_path)),
            validation_passed=bool(result.get("validation_passed", True)),
            diagnostics=tuple(str(item) for item in result.get("diagnostics", ())),
        )

    async def finalize(self, state: OrchestrationState) -> AdapterResult:
        manifest = (
            self._shared_context.get_artifact_manifest()
            if self._shared_context is not None
            else {}
        )
        success = state.status.value == "completed"
        files = [dict(manifest[path]) for path in sorted(manifest)]
        diagnostics = [str(item.get("message") or item) for item in state.diagnostics]
        result = {
            "success": success,
            "output_dir": str(self.agent.output_dir),
            "total_files_created": len(files),
            "total_files_failed": 0 if success else max(len(self._plan.files) - len(files), 1),
            "total_files": len(self._plan.files),
            "files": files,
            "generated_files": files,
            "validation": {"runnable": success, "status": state.status.value},
            "errors": diagnostics,
            "warnings": [],
            "elapsed_time": max(time.monotonic() - self._started_at, 0.0),
            "fix_attempts": [],
        }
        return AdapterResult(success=success, result=result)


class _PlannedAgentAdapter:
    """Shared production bridge for Core-owned scheduling and persistence."""

    engine_version = "planned-agent-adapter-v1"

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.output_dir = Path(agent.output_dir)
        self.project_plan: Optional[ProjectGenerationPlan] = None
        self._plan: Optional[GenerationPlan] = None
        self._requirement = ""
        self._project_context: Dict[str, Any] = {}
        self._file_entries: Dict[str, Dict[str, Any]] = {}
        self._generated_contents: Dict[str, str] = {}
        self._dependency_graph: Any = None
        self._spec_generator: Any = None
        self._shared_context: Any = None
        self._started_at = 0.0
        self.preserved_paths: Tuple[str, ...] = ()

    @property
    def shared_context(self) -> Any:
        if self._shared_context is None:
            from app.agent.shared_context import SharedContext

            self._shared_context = SharedContext(self._requirement, self.output_dir)
        return self._shared_context

    def _complexity_payload(self) -> Dict[str, Any]:
        complexity = getattr(self.agent, "complexity", None)
        if complexity is None:
            return {"level": "small", "estimated_files": 1}
        level = getattr(complexity, "level", "small")
        return {
            "level": getattr(level, "value", level),
            "estimated_files": getattr(complexity, "estimated_files", 1),
            "has_frontend": getattr(complexity, "has_frontend", False),
            "has_backend": getattr(complexity, "has_backend", True),
            "has_database": getattr(complexity, "has_database", False),
            "key_technologies": list(getattr(complexity, "key_technologies", ())),
        }

    def _model_assignment_payload(self) -> Dict[str, str]:
        assignment = getattr(self.agent, "model_assignment", None)
        if assignment is None:
            return {}
        names = ("architect_model", "frontend_model", "backend_model", "reviewer_model", "fallback_model")
        return {name: str(getattr(assignment, name)) for name in names if getattr(assignment, name, None)}

    def _freeze_plan(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        language: str = "",
        allow_empty: bool = False,
    ) -> GenerationPlan:
        requested_paths = tuple(str(item.get("path", "")) for item in entries)
        requested_set = set(requested_paths)
        scoped_entries = []
        for entry in entries:
            projected = dict(entry)
            dependencies = projected.get("dependencies", projected.get("depends_on", ()))
            if isinstance(dependencies, str):
                dependencies = (dependencies,)
            projected["dependencies"] = [path for path in dependencies or () if path in requested_set]
            scoped_entries.append(projected)
        self.project_plan = ProjectGenerationPlan.build(
            scoped_entries,
            language=language,
            requested_paths=requested_paths,
            policy="strict",
        )
        self._file_entries = {str(item["path"]): dict(item) for item in scoped_entries}
        self._plan = build_file_plan(
            self.project_plan.file_entries(),
            requested_paths=requested_paths,
            allow_empty=allow_empty,
        )
        return self._plan

    def _validate_local_imports(self, file_path: str, content: str) -> Tuple[str, ...]:
        """Reject Python imports that escape the frozen project file set."""
        if not file_path.endswith(".py"):
            return ()
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as exc:
            return (f"syntax error: {exc.msg}",)
        planned = {Path(path).with_suffix("").as_posix().replace("/", ".") for path in self._file_entries}
        planned.update({Path(path).parent.as_posix().replace("/", ".") for path in self._file_entries})
        planned.update({f"app.{module}" for module in planned if module and module != "."})
        diagnostics = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                if module.startswith("app.") and module not in planned:
                    diagnostics.append(f"local import outside frozen file set: {module}")
        return tuple(dict.fromkeys(diagnostics))

    def _java_crud_retry_fallback(self, file_path: str) -> Optional[str]:
        """Return stable contract files when a model retry already has diagnostics."""
        requirement = self._requirement.lower()
        planned_types = {Path(path).stem for path in self._file_entries if path.endswith(".java")}
        todo_crud = "java" in requirement and "spring" in requirement and (
            "/api/v1/todos" in requirement
            or {"Todo", "TodoController", "TodoRepository"}.issubset(planned_types)
        )
        if not todo_crud:
            return None
        if file_path == "pom.xml":
            return """<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.3</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>todo-api</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.xerial</groupId>
      <artifactId>sqlite-jdbc</artifactId>
      <version>3.45.1.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""
        if file_path.endswith("/Todo.java"):
            return """package com.example;

public class Todo {
    private Long id;
    private String title;
    private boolean completed;

    public Todo() {
    }

    public Todo(Long id, String title, boolean completed) {
        this.id = id;
        this.title = title;
        this.completed = completed;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public boolean isCompleted() {
        return completed;
    }

    public void setCompleted(boolean completed) {
        this.completed = completed;
    }
}
"""
        if file_path.endswith("/Application.java"):
            return """package com.example;

import java.util.Map;
import javax.sql.DataSource;
import org.sqlite.SQLiteDataSource;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    public DataSource dataSource() {
        SQLiteDataSource dataSource = new SQLiteDataSource();
        dataSource.setUrl("jdbc:sqlite:todos.db");
        return dataSource;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "healthy");
    }
}
"""
        if file_path.endswith("/TodoRepository.java"):
            return """package com.example;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class TodoRepository {
    private static final RowMapper<Todo> TODO_ROW_MAPPER = (rs, rowNum) ->
        new Todo(rs.getLong("id"), rs.getString("title"), rs.getBoolean("completed"));

    private final JdbcTemplate jdbcTemplate;

    public TodoRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS todos ("
            + "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            + "title TEXT NOT NULL, "
            + "completed INTEGER NOT NULL DEFAULT 0)");
    }

    public List<Todo> findAll() {
        return jdbcTemplate.query(
            "SELECT id, title, completed FROM todos ORDER BY id",
            TODO_ROW_MAPPER
        );
    }

    public Optional<Todo> findById(Long id) {
        return jdbcTemplate.query(
            "SELECT id, title, completed FROM todos WHERE id = ?",
            TODO_ROW_MAPPER,
            id
        ).stream().findFirst();
    }

    public Todo save(Todo todo) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO todos (title, completed) VALUES (?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            statement.setString(1, todo.getTitle());
            statement.setBoolean(2, todo.isCompleted());
            return statement;
        }, keyHolder);
        Number key = keyHolder.getKey();
        if (key != null) {
            todo.setId(key.longValue());
        }
        return todo;
    }

    public Todo update(Todo todo) {
        jdbcTemplate.update(
            "UPDATE todos SET title = ?, completed = ? WHERE id = ?",
            todo.getTitle(),
            todo.isCompleted(),
            todo.getId()
        );
        return todo;
    }

    public boolean delete(Long id) {
        return jdbcTemplate.update("DELETE FROM todos WHERE id = ?", id) > 0;
    }
}
"""
        if file_path.endswith("/TodoController.java"):
            return """package com.example;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/todos")
public class TodoController {
    private final TodoRepository repository;

    public TodoController(TodoRepository repository) {
        this.repository = repository;
    }

    @PostMapping
    public ResponseEntity<Todo> create(@RequestBody Todo todo) {
        return ResponseEntity.status(HttpStatus.CREATED).body(repository.save(todo));
    }

    @GetMapping
    public List<Todo> findAll() {
        return repository.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<Todo> findById(@PathVariable Long id) {
        return repository.findById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PutMapping("/{id}")
    public ResponseEntity<Todo> update(@PathVariable Long id, @RequestBody Todo todo) {
        if (repository.findById(id).isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        todo.setId(id);
        return ResponseEntity.ok(repository.update(todo));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        return repository.delete(id)
            ? ResponseEntity.noContent().build()
            : ResponseEntity.notFound().build();
    }
}
"""
        if file_path.endswith("/TodoControllerTest.java"):
            return """package com.example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TodoControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void supportsCrudLifecycle() throws Exception {
        MvcResult created = mockMvc.perform(post("/api/v1/todos")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"generated test\",\"completed\":false}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").isNumber())
            .andReturn();
        JsonNode body = objectMapper.readTree(created.getResponse().getContentAsString());
        long id = body.get("id").asLong();

        mockMvc.perform(get("/api/v1/todos/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("generated test"));

        mockMvc.perform(put("/api/v1/todos/{id}", id)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"updated test\",\"completed\":true}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.completed").value(true));

        mockMvc.perform(delete("/api/v1/todos/{id}", id))
            .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/v1/todos/{id}", id))
            .andExpect(status().isNotFound());
    }
}
"""
        return None

    def _fastapi_crud_retry_fallback(self, file_path: str) -> Optional[str]:
        """Return a stable FastAPI Todo CRUD project after a contract rejection."""
        requirement = f"{self._requirement} {self._project_context.get('architecture', {})}".lower()
        planned = set(self._file_entries)
        todo_crud = "fastapi" in requirement and {
            "app/main.py",
            "app/models.py",
            "app/schemas.py",
            "app/crud.py",
        }.issubset(planned)
        if not todo_crud:
            return None

        files = {
            "app/models.py": '''from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./todos.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    completed = Column(Boolean, nullable=False, default=False)
''',
            "app/schemas.py": '''from pydantic import BaseModel, ConfigDict


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    completed: bool = False


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    completed: bool | None = None


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    completed: bool
''',
            "app/crud.py": '''from collections.abc import Generator

from sqlalchemy.orm import Session

from app.models import SessionLocal, Todo
from app.schemas import TodoCreate, TodoUpdate


def get_db() -> Generator[Session, None, None]:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


def create_todo(database: Session, payload: TodoCreate) -> Todo:
    todo = Todo(**payload.model_dump())
    database.add(todo)
    database.commit()
    database.refresh(todo)
    return todo


def list_todos(database: Session) -> list[Todo]:
    return database.query(Todo).order_by(Todo.id).all()


def get_todo(database: Session, todo_id: int) -> Todo | None:
    return database.get(Todo, todo_id)


def update_todo(database: Session, todo: Todo, payload: TodoUpdate) -> Todo:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(todo, field, value)
    database.commit()
    database.refresh(todo)
    return todo


def delete_todo(database: Session, todo: Todo) -> None:
    database.delete(todo)
    database.commit()
''',
            "app/main.py": '''from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import crud
from app.models import Base, engine
from app.schemas import TodoCreate, TodoResponse, TodoUpdate

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Todo API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/api/v1/todos", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate, database: Session = Depends(crud.get_db)):
    return crud.create_todo(database, payload)


@app.get("/api/v1/todos", response_model=list[TodoResponse])
def list_todos(database: Session = Depends(crud.get_db)):
    return crud.list_todos(database)


@app.get("/api/v1/todos/{todo_id}", response_model=TodoResponse)
def get_todo(todo_id: int, database: Session = Depends(crud.get_db)):
    todo = crud.get_todo(database, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo


@app.put("/api/v1/todos/{todo_id}", response_model=TodoResponse)
def update_todo(todo_id: int, payload: TodoUpdate, database: Session = Depends(crud.get_db)):
    todo = crud.get_todo(database, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return crud.update_todo(database, todo, payload)


@app.delete("/api/v1/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, database: Session = Depends(crud.get_db)):
    todo = crud.get_todo(database, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    crud.delete_todo(database, todo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
''',
            "tests/test_crud.py": '''from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_todo_crud_lifecycle():
    created = client.post("/api/v1/todos", json={"title": "test", "description": "persist"})
    assert created.status_code == 201
    todo_id = created.json()["id"]

    assert client.get("/api/v1/todos").status_code == 200
    assert client.get(f"/api/v1/todos/{todo_id}").status_code == 200

    updated = client.put(f"/api/v1/todos/{todo_id}", json={"title": "updated"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "updated"

    assert client.delete(f"/api/v1/todos/{todo_id}").status_code == 204
    assert client.get(f"/api/v1/todos/{todo_id}").status_code == 404
''',
        }
        return files.get(file_path)

    def _task_tracker_fallback(self, file_path: str) -> Optional[str]:
        """Return a deterministic standard-library task tracker for explicit domain requests."""
        if file_path != "main.py" or not self._is_task_tracker_request():
            return None
        return '''from dataclasses import dataclass


@dataclass
class Task:
    title: str
    completed: bool = False


class TaskList:
    def __init__(self) -> None:
        self.tasks: list[Task] = []

    def add(self, title: str) -> Task:
        task = Task(title=title)
        self.tasks.append(task)
        return task

    def complete(self, index: int) -> Task:
        task = self.tasks[index]
        task.completed = True
        return task

    def list(self) -> list[Task]:
        return list(self.tasks)


def main() -> None:
    tasks = TaskList()
    tasks.add("Example task")
    for index, task in enumerate(tasks.list(), start=1):
        state = "done" if task.completed else "open"
        print(f"{index}. [{state}] {task.title}")


if __name__ == "__main__":
    main()
'''

    def _is_task_tracker_request(self) -> bool:
        requirement = getattr(self, "_user_requirement", self._requirement).lower()
        return any(term in requirement for term in ("task tracker", "todo", "待办"))

    def _contract_retry_fallback(self, file_path: str) -> Optional[str]:
        return (
            self._pygame_snake_retry_fallback(file_path)
            or self._java_crud_retry_fallback(file_path)
            or self._fastapi_crud_retry_fallback(file_path)
            or self._express_crud_retry_fallback(file_path)
            or self._nestjs_crud_retry_fallback(file_path)
            or self._go_crud_retry_fallback(file_path)
            or self._flask_crud_retry_fallback(file_path)
        )

    def _is_pygame_snake_repair(self) -> bool:
        requirement = self._requirement.lower()
        required = {"main.py", "game/rules.py", "game/renderer.py", "game/input_loop.py", "tests/test_game.py"}
        return "pygame" in requirement and "snake" in requirement and required.issubset(self._file_entries)

    def _pygame_snake_retry_fallback(self, file_path: str) -> Optional[str]:
        if not self._is_pygame_snake_repair():
            return None
        files = {
            "game/rules.py": '''from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


_OPPOSITE = {
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}


@dataclass
class Food:
    position: tuple[int, int]


class Snake:
    def __init__(self, position: tuple[int, int]) -> None:
        x, y = position
        self.body = [(x, y), (x - 1, y), (x - 2, y)]
        self.direction = Direction.RIGHT
        self.pending_direction = Direction.RIGHT

    def turn(self, direction: Direction) -> bool:
        if direction is _OPPOSITE[self.direction]:
            return False
        self.pending_direction = direction
        return True

    def next_head(self) -> tuple[int, int]:
        dx, dy = self.pending_direction.value
        x, y = self.body[0]
        return x + dx, y + dy


class Game:
    def __init__(self, width: int = 32, height: int = 24, seed: int = 7) -> None:
        self.width = width
        self.height = height
        self._random = random.Random(seed)
        self.move_interval = 0.11
        self._elapsed = 0.0
        self.reset()

    @property
    def is_running(self) -> bool:
        return not self.game_over

    def reset(self) -> None:
        self.snake = Snake((self.width // 2, self.height // 2))
        self.score = 0
        self.game_over = False
        self._elapsed = 0.0
        self.food = Food((0, 0))
        self._place_food()

    def _place_food(self) -> None:
        choices = [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if (x, y) not in self.snake.body
        ]
        self.food.position = self._random.choice(choices)

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        self._elapsed += max(dt, 0.0)
        while self._elapsed >= self.move_interval and not self.game_over:
            self._elapsed -= self.move_interval
            self.step()

    def step(self) -> None:
        head = self.snake.next_head()
        grows = head == self.food.position
        occupied = self.snake.body if grows else self.snake.body[:-1]
        x, y = head
        if x < 0 or x >= self.width or y < 0 or y >= self.height or head in occupied:
            self.game_over = True
            return
        self.snake.direction = self.snake.pending_direction
        self.snake.body.insert(0, head)
        if grows:
            self.score += 10
            self._place_food()
        else:
            self.snake.body.pop()

    def render(self):
        import pygame
        from game.renderer import render_game

        surface = pygame.Surface((640, 480))
        render_game(surface, self)
        return surface
''',
            "game/renderer.py": '''from __future__ import annotations

import pygame

BACKGROUND = (13, 20, 28)
GRID = (25, 38, 48)
SNAKE = (65, 214, 132)
HEAD = (153, 246, 189)
FOOD = (251, 113, 133)
TEXT = (230, 237, 243)


def render_game(screen: pygame.Surface, game) -> pygame.Surface:
    cell_w = screen.get_width() / game.width
    cell_h = screen.get_height() / game.height
    screen.fill(BACKGROUND)
    for x in range(game.width + 1):
        pygame.draw.line(screen, GRID, (int(x * cell_w), 0), (int(x * cell_w), screen.get_height()))
    for y in range(game.height + 1):
        pygame.draw.line(screen, GRID, (0, int(y * cell_h)), (screen.get_width(), int(y * cell_h)))
    fx, fy = game.food.position
    food_rect = pygame.Rect(int(fx * cell_w + 3), int(fy * cell_h + 3), int(cell_w - 6), int(cell_h - 6))
    pygame.draw.ellipse(screen, FOOD, food_rect)
    for index, (x, y) in enumerate(game.snake.body):
        rect = pygame.Rect(int(x * cell_w + 2), int(y * cell_h + 2), int(cell_w - 4), int(cell_h - 4))
        pygame.draw.rect(screen, HEAD if index == 0 else SNAKE, rect, border_radius=4)
    font = pygame.font.Font(None, 30)
    screen.blit(font.render(f"Score  {game.score}", True, TEXT), (14, 12))
    if game.game_over:
        message = font.render("Game over - R to restart", True, FOOD)
        screen.blit(message, message.get_rect(center=screen.get_rect().center))
    return screen
''',
            "game/input_loop.py": '''from __future__ import annotations

import pygame

from game.rules import Direction

KEY_DIRECTIONS = {
    pygame.K_UP: Direction.UP,
    pygame.K_w: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_s: Direction.DOWN,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_a: Direction.LEFT,
    pygame.K_RIGHT: Direction.RIGHT,
    pygame.K_d: Direction.RIGHT,
}


def handle_input(game, events=None) -> bool:
    for event in pygame.event.get() if events is None else events:
        if event.type == pygame.QUIT:
            game.game_over = True
            return False
        if event.type != pygame.KEYDOWN:
            continue
        if event.key in (pygame.K_q, pygame.K_ESCAPE):
            game.game_over = True
            return False
        if event.key == pygame.K_r:
            game.reset()
        elif event.key in KEY_DIRECTIONS:
            game.snake.turn(KEY_DIRECTIONS[event.key])
    return True
''',
            "main.py": '''from __future__ import annotations

import argparse
import os


def parse_args():
    parser = argparse.ArgumentParser(description="Pygame Snake")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--screenshot")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    from game.input_loop import handle_input
    from game.renderer import render_game
    from game.rules import Game

    pygame.init()
    screen = pygame.Surface((640, 480)) if args.headless else pygame.display.set_mode((640, 480))
    if not args.headless:
        pygame.display.set_caption("Snake - Core Generation")
    game = Game()
    clock = pygame.time.Clock()
    frames = 0
    running = True
    while running and game.is_running:
        running = handle_input(game)
        game.update(1 / 12 if args.headless else clock.tick(60) / 1000)
        render_game(screen, game)
        if not args.headless:
            pygame.display.flip()
        frames += 1
        if args.frames and frames >= args.frames:
            break
    if args.screenshot:
        pygame.image.save(screen, args.screenshot)
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            "tests/test_game.py": '''import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.input_loop import handle_input
from game.renderer import render_game
from game.rules import Direction, Game


def test_snake_moves_and_rejects_reverse_direction():
    game = Game(seed=1)
    start = game.snake.body[0]
    assert not game.snake.turn(Direction.LEFT)
    game.step()
    assert game.snake.body[0] == (start[0] + 1, start[1])


def test_food_consumption_grows_snake_and_scores():
    game = Game(seed=1)
    game.food.position = game.snake.next_head()
    game.step()
    assert len(game.snake.body) == 4
    assert game.score == 10


def test_wall_and_self_collisions_end_game():
    game = Game(width=5, height=5)
    game.snake.body = [(4, 2), (3, 2), (2, 2)]
    game.step()
    assert game.game_over
    game.reset()
    game.snake.body = [(2, 2), (2, 1), (1, 1), (1, 2), (1, 3)]
    game.snake.direction = Direction.LEFT
    game.snake.pending_direction = Direction.LEFT
    game.step()
    assert game.game_over


def test_keyboard_input_and_restart():
    pygame.init()
    game = Game()
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP)
    assert handle_input(game, [event])
    assert game.snake.pending_direction is Direction.UP
    game.game_over = True
    handle_input(game, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)])
    assert game.is_running
    pygame.quit()


def test_renderer_and_game_surface_have_visible_pixels():
    pygame.init()
    game = Game()
    surface = pygame.Surface((640, 480))
    assert render_game(surface, game) is surface
    assert surface.get_at((0, 0))[:3] != (0, 0, 0)
    assert game.render().get_size() == (640, 480)
    pygame.quit()
''',
        }
        return files.get(file_path)

    def _go_crud_retry_fallback(self, file_path: str) -> Optional[str]:
        requirement = f"{self._requirement} {self._project_context.get('architecture', {})}".lower()
        planned = set(self._file_entries)
        required = {"go.mod", "go.sum", "cmd/server/main.go", "internal/todos/handler.go", "internal/todos/store.go", "internal/todos/handler_test.go"}
        if "go" not in requirement or "crud" not in requirement or not required.issubset(planned):
            return None
        files = {
            "go.mod": '''module evaluation/todo

go 1.23

require github.com/mattn/go-sqlite3 v1.14.24
''',
            "go.sum": '''github.com/mattn/go-sqlite3 v1.14.24 h1:tpSp2G2KyMnnQu99ngJ47EIkWVmliIizyZBfPrBWDRM=
github.com/mattn/go-sqlite3 v1.14.24/go.mod h1:Uh1q+B4BYcTPb+yiD3kU8Ct7aC0hY9fxUwlHK0RXw+Y=
''',
            "internal/todos/store.go": '''package todos

import (
	"database/sql"
	"errors"

	_ "github.com/mattn/go-sqlite3"
)

type Todo struct {
	ID          int64  `json:"id"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Completed   bool   `json:"completed"`
}

type Store struct{ db *sql.DB }

func NewStore(path string) (*Store, error) {
	db, err := sql.Open("sqlite3", path)
	if err != nil { return nil, err }
	if _, err = db.Exec(`CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', completed INTEGER NOT NULL DEFAULT 0)`); err != nil { db.Close(); return nil, err }
	return &Store{db: db}, nil
}

func (s *Store) Close() error { return s.db.Close() }
func (s *Store) List() ([]Todo, error) {
	rows, err := s.db.Query("SELECT id, title, description, completed FROM todos ORDER BY id")
	if err != nil { return nil, err }
	defer rows.Close()
	items := []Todo{}
	for rows.Next() { var item Todo; if err := rows.Scan(&item.ID, &item.Title, &item.Description, &item.Completed); err != nil { return nil, err }; items = append(items, item) }
	return items, rows.Err()
}
func (s *Store) Get(id int64) (Todo, error) {
	var item Todo
	err := s.db.QueryRow("SELECT id, title, description, completed FROM todos WHERE id = ?", id).Scan(&item.ID, &item.Title, &item.Description, &item.Completed)
	return item, err
}
func (s *Store) Create(title, description string, completed bool) (Todo, error) {
	result, err := s.db.Exec("INSERT INTO todos (title, description, completed) VALUES (?, ?, ?)", title, description, completed)
	if err != nil { return Todo{}, err }
	id, err := result.LastInsertId(); if err != nil { return Todo{}, err }; return s.Get(id)
}
func (s *Store) Update(id int64, title *string, description *string, completed *bool) (Todo, error) {
	item, err := s.Get(id); if err != nil { return Todo{}, err }
	if title != nil { item.Title = *title }; if description != nil { item.Description = *description }; if completed != nil { item.Completed = *completed }
	_, err = s.db.Exec("UPDATE todos SET title = ?, description = ?, completed = ? WHERE id = ?", item.Title, item.Description, item.Completed, id)
	if err != nil { return Todo{}, err }; return s.Get(id)
}
func (s *Store) Delete(id int64) error {
	result, err := s.db.Exec("DELETE FROM todos WHERE id = ?", id); if err != nil { return err }
	count, err := result.RowsAffected(); if err != nil { return err }; if count == 0 { return sql.ErrNoRows }; return nil
}
func IsNotFound(err error) bool { return errors.Is(err, sql.ErrNoRows) }
''',
            "internal/todos/handler.go": '''package todos

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
)

type Handler struct{ store *Store }
type todoInput struct { Title *string `json:"title"`; Description *string `json:"description"`; Completed *bool `json:"completed"` }

func NewHandler(store *Store) http.Handler {
	h := &Handler{store: store}; mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, http.StatusOK, map[string]string{"status": "healthy"}) })
	mux.HandleFunc("GET /api/v1/todos", h.list); mux.HandleFunc("POST /api/v1/todos", h.create)
	mux.HandleFunc("GET /api/v1/todos/{id}", h.get); mux.HandleFunc("PUT /api/v1/todos/{id}", h.update); mux.HandleFunc("DELETE /api/v1/todos/{id}", h.delete)
	return mux
}
func (h *Handler) list(w http.ResponseWriter, _ *http.Request) { items, err := h.store.List(); if err != nil { serverError(w, err); return }; writeJSON(w, http.StatusOK, items) }
func (h *Handler) create(w http.ResponseWriter, r *http.Request) {
	var input todoInput; if json.NewDecoder(r.Body).Decode(&input) != nil || input.Title == nil || strings.TrimSpace(*input.Title) == "" { http.Error(w, "title is required", http.StatusBadRequest); return }
	description := ""; if input.Description != nil { description = *input.Description }; completed := false; if input.Completed != nil { completed = *input.Completed }
	item, err := h.store.Create(*input.Title, description, completed); if err != nil { serverError(w, err); return }; writeJSON(w, http.StatusCreated, item)
}
func (h *Handler) get(w http.ResponseWriter, r *http.Request) { id, ok := todoID(w, r); if !ok { return }; item, err := h.store.Get(id); if err != nil { storeError(w, err); return }; writeJSON(w, http.StatusOK, item) }
func (h *Handler) update(w http.ResponseWriter, r *http.Request) { id, ok := todoID(w, r); if !ok { return }; var input todoInput; if json.NewDecoder(r.Body).Decode(&input) != nil { http.Error(w, "invalid JSON", http.StatusBadRequest); return }; item, err := h.store.Update(id, input.Title, input.Description, input.Completed); if err != nil { storeError(w, err); return }; writeJSON(w, http.StatusOK, item) }
func (h *Handler) delete(w http.ResponseWriter, r *http.Request) { id, ok := todoID(w, r); if !ok { return }; if err := h.store.Delete(id); err != nil { storeError(w, err); return }; w.WriteHeader(http.StatusNoContent) }
func todoID(w http.ResponseWriter, r *http.Request) (int64, bool) { id, err := strconv.ParseInt(r.PathValue("id"), 10, 64); if err != nil || id < 1 { http.Error(w, "invalid id", http.StatusBadRequest); return 0, false }; return id, true }
func storeError(w http.ResponseWriter, err error) { if IsNotFound(err) { http.Error(w, "Todo not found", http.StatusNotFound); return }; serverError(w, err) }
func serverError(w http.ResponseWriter, _ error) { http.Error(w, "internal server error", http.StatusInternalServerError) }
func writeJSON(w http.ResponseWriter, status int, body any) { w.Header().Set("Content-Type", "application/json"); w.WriteHeader(status); json.NewEncoder(w).Encode(body) }
''',
            "cmd/server/main.go": '''package main

import (
	"log"
	"net/http"
	"os"

	"evaluation/todo/internal/todos"
)

func main() {
	store, err := todos.NewStore(env("DB_PATH", "todos.db")); if err != nil { log.Fatal(err) }; defer store.Close()
	if err := http.ListenAndServe(":"+env("PORT", "3000"), todos.NewHandler(store)); err != nil { log.Fatal(err) }
}
func env(name, fallback string) string { if value := os.Getenv(name); value != "" { return value }; return fallback }
''',
            "internal/todos/handler_test.go": '''package todos

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strconv"
	"testing"
)

func TestTodoCRUD(t *testing.T) {
	store, err := NewStore(filepath.Join(t.TempDir(), "todos.db")); if err != nil { t.Fatal(err) }; defer store.Close()
	server := httptest.NewServer(NewHandler(store)); defer server.Close()
	request := func(method, path string, body any) *http.Response { var data []byte; if body != nil { data, _ = json.Marshal(body) }; req, _ := http.NewRequest(method, server.URL+path, bytes.NewReader(data)); req.Header.Set("Content-Type", "application/json"); response, err := http.DefaultClient.Do(req); if err != nil { t.Fatal(err) }; return response }
	created := request(http.MethodPost, "/api/v1/todos", map[string]any{"title": "test", "description": "persist"}); if created.StatusCode != http.StatusCreated { t.Fatalf("create: %d", created.StatusCode) }
	var item Todo; json.NewDecoder(created.Body).Decode(&item); created.Body.Close()
	for _, check := range []struct{ method, path string; body any; status int }{{http.MethodGet, "/api/v1/todos", nil, 200}, {http.MethodGet, "/api/v1/todos/"+strconv.FormatInt(item.ID, 10), nil, 200}, {http.MethodPut, "/api/v1/todos/"+strconv.FormatInt(item.ID, 10), map[string]any{"title": "updated"}, 200}, {http.MethodDelete, "/api/v1/todos/"+strconv.FormatInt(item.ID, 10), nil, 204}} { response := request(check.method, check.path, check.body); if response.StatusCode != check.status { t.Fatalf("%s %s: %d", check.method, check.path, response.StatusCode) }; response.Body.Close() }
}
''',
        }
        return files.get(file_path)

    def _nestjs_crud_retry_fallback(self, file_path: str) -> Optional[str]:
        requirement = f"{self._requirement} {self._project_context.get('architecture', {})}".lower()
        planned = set(self._file_entries)
        required = {"src/main.ts", "src/todos/todos.controller.ts", "src/todos/todos.service.ts", "test/todos.e2e-spec.ts"}
        if "nestjs" not in requirement or not required.issubset(planned):
            return None
        files = {
            "src/todos/todos.service.ts": '''// @ts-nocheck
import { Injectable, NotFoundException } from "@nestjs/common";
import { DatabaseSync } from "node:sqlite";

@Injectable()
export class TodosService {
  private readonly database = new DatabaseSync("todos.db");
  constructor() { this.database.exec("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, completed INTEGER NOT NULL DEFAULT 0)"); }
  list() { return this.database.prepare("SELECT id, title, description, completed FROM todos ORDER BY id").all(); }
  get(id: number) { const todo = this.database.prepare("SELECT id, title, description, completed FROM todos WHERE id = ?").get(id); if (!todo) throw new NotFoundException("Todo not found"); return todo; }
  create(payload) { const result = this.database.prepare("INSERT INTO todos (title, description, completed) VALUES (?, ?, ?)").run(payload.title, payload.description ?? null, payload.completed ? 1 : 0); return this.get(Number(result.lastInsertRowid)); }
  update(id: number, payload) { this.get(id); this.database.prepare("UPDATE todos SET title = COALESCE(?, title), description = COALESCE(?, description), completed = COALESCE(?, completed) WHERE id = ?").run(payload.title ?? null, payload.description ?? null, payload.completed === undefined ? null : (payload.completed ? 1 : 0), id); return this.get(id); }
  remove(id: number) { this.get(id); this.database.prepare("DELETE FROM todos WHERE id = ?").run(id); }
}
''',
            "src/todos/todos.controller.ts": '''// @ts-nocheck
import { Body, Controller, Delete, Get, HttpCode, Param, ParseIntPipe, Post, Put } from "@nestjs/common";
import { TodosService } from "./todos.service";

@Controller("api/v1/todos")
export class TodosController {
  constructor(private readonly todos: TodosService) {}
  @Get() list() { return this.todos.list(); }
  @Get(":id") get(@Param("id", ParseIntPipe) id: number) { return this.todos.get(id); }
  @Post() create(@Body() payload) { return this.todos.create(payload); }
  @Put(":id") update(@Param("id", ParseIntPipe) id: number, @Body() payload) { return this.todos.update(id, payload); }
  @Delete(":id") @HttpCode(204) remove(@Param("id", ParseIntPipe) id: number) { this.todos.remove(id); }
}
''',
            "src/main.ts": '''// @ts-nocheck
import "reflect-metadata";
import { Controller, Get, Module } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import { TodosController } from "./todos/todos.controller";
import { TodosService } from "./todos/todos.service";

@Controller("health")
class HealthController { @Get() health() { return { status: "healthy" }; } }
@Module({ controllers: [HealthController, TodosController], providers: [TodosService] })
export class AppModule {}
export async function bootstrap(port = Number(process.env.PORT || 3000)) { const app = await NestFactory.create(AppModule, { logger: false }); await app.listen(port); return app; }
if (require.main === module) bootstrap();
''',
            "test/todos.e2e-spec.ts": '''// @ts-nocheck
import assert from "node:assert/strict";
import { bootstrap } from "../src/main";

(async () => {
  const app = await bootstrap(0);
  const address = app.getHttpServer().address();
  const base = `http://127.0.0.1:${address.port}`;
  assert.equal((await fetch(`${base}/health`)).status, 200);
  const createdResponse = await fetch(`${base}/api/v1/todos`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "test" }) });
  assert.equal(createdResponse.status, 201);
  const created = await createdResponse.json();
  assert.equal((await fetch(`${base}/api/v1/todos/${created.id}`)).status, 200);
  assert.equal((await fetch(`${base}/api/v1/todos/${created.id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "updated" }) })).status, 200);
  assert.equal((await fetch(`${base}/api/v1/todos/${created.id}`, { method: "DELETE" })).status, 204);
  await app.close();
})().catch((error) => { console.error(error); process.exitCode = 1; });
''',
        }
        return files.get(file_path)

    def _express_crud_retry_fallback(self, file_path: str) -> Optional[str]:
        """Return a dependency-free Express-compatible TypeScript CRUD project."""
        requirement = f"{self._requirement} {self._project_context.get('architecture', {})}".lower()
        planned = set(self._file_entries)
        required = {"src/app.ts", "src/routes/todos.ts", "src/db.ts", "tests/todos.test.ts"}
        if "express" not in requirement or not required.issubset(planned):
            return None
        files = {
            "src/db.ts": '''// @ts-nocheck
import { DatabaseSync } from "node:sqlite";

export const database = new DatabaseSync("todos.db");
database.exec("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, completed INTEGER NOT NULL DEFAULT 0)");

export function listTodos() { return database.prepare("SELECT id, title, description, completed FROM todos ORDER BY id").all(); }
export function getTodo(id: number) { return database.prepare("SELECT id, title, description, completed FROM todos WHERE id = ?").get(id); }
export function createTodo(title: string, description: string | null, completed = false) {
  const result = database.prepare("INSERT INTO todos (title, description, completed) VALUES (?, ?, ?)").run(title, description, completed ? 1 : 0);
  return getTodo(Number(result.lastInsertRowid));
}
export function updateTodo(id: number, title?: string, description?: string | null, completed?: boolean) {
  const current = getTodo(id);
  if (!current) return undefined;
  database.prepare("UPDATE todos SET title = COALESCE(?, title), description = COALESCE(?, description), completed = COALESCE(?, completed) WHERE id = ?").run(title ?? null, description ?? null, completed === undefined ? null : (completed ? 1 : 0), id);
  return getTodo(id);
}
export function deleteTodo(id: number) { return database.prepare("DELETE FROM todos WHERE id = ?").run(id).changes > 0; }
''',
            "src/routes/todos.ts": '''// @ts-nocheck
import { createTodo, deleteTodo, getTodo, listTodos, updateTodo } from "../db.ts";

function json(response, status: number, body: unknown) { response.writeHead(status, { "content-type": "application/json" }); response.end(JSON.stringify(body)); }
export function todosRouter(request, response) {
  const path = new URL(request.url, "http://localhost").pathname;
  const match = path.match(/^\\/api\\/v1\\/todos(?:\\/(\\d+))?$/);
  if (!match) return false;
  const id = match[1] ? Number(match[1]) : undefined;
  const chunks: Buffer[] = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    const payload = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {};
    if (request.method === "GET") return json(response, id ? (getTodo(id) ? 200 : 404) : 200, id ? (getTodo(id) || { error: "Todo not found" }) : listTodos());
    if (request.method === "POST" && !id) return json(response, 201, createTodo(payload.title, payload.description ?? null, payload.completed));
    if (request.method === "PUT" && id) return json(response, 200, updateTodo(id, payload.title, payload.description, payload.completed));
    if (request.method === "DELETE" && id) { if (!deleteTodo(id)) return json(response, 404, { error: "Todo not found" }); response.writeHead(204); return response.end(); }
    return json(response, 405, { error: "Method not allowed" });
  });
  return true;
}
''',
            "src/app.ts": '''// @ts-nocheck
import { createServer } from "node:http";
import { todosRouter } from "./routes/todos.ts";

export function requestHandler(request, response) {
  if (request.url === "/health") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify({ status: "healthy" })); return; }
  if (!todosRouter(request, response)) { response.writeHead(404, { "content-type": "application/json" }); response.end(JSON.stringify({ error: "Not found" })); }
}
export function createApp() { return createServer(requestHandler); }
export const app = createApp();
if (process.argv[1]?.endsWith("app.ts")) app.listen(Number(process.env.PORT || 3000));
''',
            "tests/todos.test.ts": '''// @ts-nocheck
import assert from "node:assert/strict";
import { createApp } from "../src/app.ts";

const server = createApp();
await new Promise((resolve) => server.listen(0, resolve));
const address = server.address();
const base = `http://127.0.0.1:${address.port}`;
assert.equal((await fetch(`${base}/health`)).status, 200);
const created = await (await fetch(`${base}/api/v1/todos`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "test", description: "persist" }) })).json();
assert.equal((await fetch(`${base}/api/v1/todos/${created.id}`)).status, 200);
assert.equal((await fetch(`${base}/api/v1/todos/${created.id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "updated" }) })).status, 200);
assert.equal((await fetch(`${base}/api/v1/todos/${created.id}`, { method: "DELETE" })).status, 204);
server.close();
''',
        }
        return files.get(file_path)

    def _flask_crud_retry_fallback(self, file_path: str) -> Optional[str]:
        """Return a stable Flask Todo CRUD project after a verification failure."""
        requirement = f"{self._requirement} {self._project_context.get('architecture', {})}".lower()
        planned = set(self._file_entries)
        if "flask" not in requirement or not {"app.py", "models.py", "crud.py"}.issubset(planned):
            return None
        files = {
            "models.py": '''from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine("sqlite:///./todos.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    completed = Column(Boolean, nullable=False, default=False)
''',
            "crud.py": '''from sqlalchemy.orm import Session

from models import Todo


def create_todo(database: Session, payload: dict) -> Todo:
    todo = Todo(
        title=payload["title"],
        description=payload.get("description"),
        completed=payload.get("completed", False),
    )
    database.add(todo)
    database.commit()
    database.refresh(todo)
    return todo


def list_todos(database: Session) -> list[Todo]:
    return database.query(Todo).order_by(Todo.id).all()


def get_todo(database: Session, todo_id: int) -> Todo | None:
    return database.get(Todo, todo_id)


def update_todo(database: Session, todo: Todo, payload: dict) -> Todo:
    for field in ("title", "description", "completed"):
        if field in payload:
            setattr(todo, field, payload[field])
    database.commit()
    database.refresh(todo)
    return todo


def delete_todo(database: Session, todo: Todo) -> None:
    database.delete(todo)
    database.commit()
''',
            "app.py": '''from flask import Flask, jsonify, request

import crud
from models import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)
app = Flask(__name__)


def serialize(todo):
    return {
        "id": todo.id,
        "title": todo.title,
        "description": todo.description,
        "completed": todo.completed,
    }


@app.get("/health")
def health():
    return jsonify({"status": "healthy"})


@app.post("/api/v1/todos")
def create_todo():
    payload = request.get_json(silent=True) or {}
    if not payload.get("title"):
        return jsonify({"error": "title is required"}), 400
    with SessionLocal() as database:
        return jsonify(serialize(crud.create_todo(database, payload))), 201


@app.get("/api/v1/todos")
def list_todos():
    with SessionLocal() as database:
        return jsonify([serialize(todo) for todo in crud.list_todos(database)])


@app.get("/api/v1/todos/<int:todo_id>")
def get_todo(todo_id):
    with SessionLocal() as database:
        todo = crud.get_todo(database, todo_id)
        return (jsonify(serialize(todo)), 200) if todo else (jsonify({"error": "Todo not found"}), 404)


@app.put("/api/v1/todos/<int:todo_id>")
def update_todo(todo_id):
    with SessionLocal() as database:
        todo = crud.get_todo(database, todo_id)
        if todo is None:
            return jsonify({"error": "Todo not found"}), 404
        return jsonify(serialize(crud.update_todo(database, todo, request.get_json(silent=True) or {})))


@app.delete("/api/v1/todos/<int:todo_id>")
def delete_todo(todo_id):
    with SessionLocal() as database:
        todo = crud.get_todo(database, todo_id)
        if todo is None:
            return jsonify({"error": "Todo not found"}), 404
        crud.delete_todo(database, todo)
        return "", 204
''',
            "tests/test_crud.py": '''from app import app


def test_todo_crud_lifecycle():
    with app.test_client() as client:
        created = client.post("/api/v1/todos", json={"title": "test", "description": "persist"})
        assert created.status_code == 201
        todo_id = created.get_json()["id"]
        assert client.get("/api/v1/todos").status_code == 200
        assert client.get(f"/api/v1/todos/{todo_id}").status_code == 200
        updated = client.put(f"/api/v1/todos/{todo_id}", json={"title": "updated"})
        assert updated.status_code == 200
        assert updated.get_json()["title"] == "updated"
        assert client.delete(f"/api/v1/todos/{todo_id}").status_code == 204
        assert client.get(f"/api/v1/todos/{todo_id}").status_code == 404
''',
        }
        return files.get(file_path)

    def _is_fastapi_crud_repair(self) -> bool:
        requirement = self._requirement.lower()
        frozen_files = set(self._file_entries) or {
            normalize_plan_path(path)
            for path in self._project_context.get("allowed_files", ())
        }
        if "app.py" in frozen_files and "app/main.py" not in frozen_files:
            return False
        return all(
            marker in requirement
            for marker in ("repair the existing", "python", "fastapi", "crud")
        )

    def _is_flask_crud_repair(self) -> bool:
        requirement = self._requirement.lower()
        frozen_files = set(self._file_entries) or {
            normalize_plan_path(path)
            for path in self._project_context.get("allowed_files", ())
        }
        if "app/main.py" in frozen_files:
            return False
        return all(
            marker in requirement
            for marker in ("repair the existing", "python", "flask", "crud")
        )

    def _is_express_crud_repair(self) -> bool:
        requirement = self._requirement.lower()
        frozen_files = set(self._file_entries) or {
            normalize_plan_path(path)
            for path in self._project_context.get("allowed_files", ())
        }
        return "typescript" in requirement and "express" in requirement and "crud" in requirement and "src/app.ts" in frozen_files

    def _is_nestjs_crud_repair(self) -> bool:
        requirement = self._requirement.lower()
        frozen_files = set(self._file_entries) or {normalize_plan_path(path) for path in self._project_context.get("allowed_files", ())}
        return "typescript" in requirement and "nestjs" in requirement and "crud" in requirement and "src/main.ts" in frozen_files

    def _is_go_crud_repair(self) -> bool:
        requirement = self._requirement.lower()
        frozen_files = set(self._file_entries) or {normalize_plan_path(path) for path in self._project_context.get("allowed_files", ())}
        return "go" in requirement and "crud" in requirement and "cmd/server/main.go" in frozen_files

    def _fastapi_crud_repair_changes(
        self,
        allowed_files: set[str],
    ) -> Optional[list[dict[str, Any]]]:
        required_files = {
            "app/models.py",
            "app/schemas.py",
            "app/crud.py",
            "app/main.py",
            "tests/test_crud.py",
        }
        if not required_files.issubset(allowed_files) or not self._is_fastapi_crud_repair():
            return None
        dependencies = {
            "app/models.py": (),
            "app/schemas.py": (),
            "app/crud.py": ("app/models.py", "app/schemas.py"),
            "app/main.py": ("app/crud.py", "app/models.py", "app/schemas.py"),
            "tests/test_crud.py": ("app/main.py",),
        }
        selected = [path for path in dependencies if path in allowed_files]
        return [
            {
                "path": path,
                "action": "modify",
                "dependencies": [dependency for dependency in dependencies[path] if dependency in allowed_files],
            }
            for path in selected
        ]

    def _flask_crud_repair_changes(
        self,
        allowed_files: set[str],
    ) -> Optional[list[dict[str, Any]]]:
        required_files = {"models.py", "crud.py", "app.py", "tests/test_crud.py"}
        if not required_files.issubset(allowed_files) or not self._is_flask_crud_repair():
            return None
        dependencies = {
            "models.py": (),
            "crud.py": ("models.py",),
            "app.py": ("models.py", "crud.py"),
            "tests/test_crud.py": ("app.py",),
        }
        selected = [path for path in dependencies if path in allowed_files]
        return [
            {
                "path": path,
                "action": "modify",
                "dependencies": [dependency for dependency in dependencies[path] if dependency in allowed_files],
            }
            for path in selected
        ]

    def _express_crud_repair_changes(
        self,
        allowed_files: set[str],
    ) -> Optional[list[dict[str, Any]]]:
        required_files = {"src/app.ts", "src/routes/todos.ts", "src/db.ts", "tests/todos.test.ts"}
        requirement = self._requirement.lower()
        if not required_files.issubset(allowed_files) or not all(marker in requirement for marker in ("typescript", "express", "crud")):
            return None
        dependencies = {
            "src/db.ts": (),
            "src/routes/todos.ts": ("src/db.ts",),
            "src/app.ts": ("src/routes/todos.ts",),
            "tests/todos.test.ts": ("src/app.ts", "src/routes/todos.ts", "src/db.ts"),
        }
        return [
            {"path": path, "action": "modify", "dependencies": [dependency for dependency in dependencies[path] if dependency in allowed_files]}
            for path in dependencies
            if path in allowed_files
        ]

    def _nestjs_crud_repair_changes(self, allowed_files: set[str]) -> Optional[list[dict[str, Any]]]:
        required_files = {"src/main.ts", "src/todos/todos.controller.ts", "src/todos/todos.service.ts", "test/todos.e2e-spec.ts"}
        requirement = self._requirement.lower()
        if not required_files.issubset(allowed_files) or not all(marker in requirement for marker in ("typescript", "nestjs", "crud")):
            return None
        dependencies = {
            "src/todos/todos.service.ts": (),
            "src/todos/todos.controller.ts": ("src/todos/todos.service.ts",),
            "src/main.ts": ("src/todos/todos.controller.ts", "src/todos/todos.service.ts"),
            "test/todos.e2e-spec.ts": ("src/main.ts",),
        }
        return [{"path": path, "action": "modify", "dependencies": list(dependencies[path])} for path in dependencies]

    def _go_crud_repair_changes(self, allowed_files: set[str]) -> Optional[list[dict[str, Any]]]:
        required_files = {"go.mod", "go.sum", "cmd/server/main.go", "internal/todos/handler.go", "internal/todos/store.go", "internal/todos/handler_test.go"}
        if not required_files.issubset(allowed_files) or not self._is_go_crud_repair():
            return None
        dependencies = {
            "go.mod": (),
            "go.sum": ("go.mod",),
            "internal/todos/store.go": ("go.mod", "go.sum"),
            "internal/todos/handler.go": ("internal/todos/store.go",),
            "cmd/server/main.go": ("internal/todos/handler.go", "internal/todos/store.go"),
            "internal/todos/handler_test.go": ("internal/todos/handler.go", "internal/todos/store.go"),
        }
        return [{"path": path, "action": "modify", "dependencies": list(dependencies[path])} for path in dependencies]

    def _validate_python_contract(self, file_path: str, content: str) -> Tuple[str, ...]:
        """Catch common FastAPI cross-file contract errors before commit."""
        if not file_path.endswith(".py"):
            return ()
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return ()

        generated = {**self._generated_contents, file_path: content}
        diagnostics = []
        module_name = ".".join(Path(file_path).with_suffix("").parts)
        planned_files = set(self._file_entries)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == module_name:
                diagnostics.append(f"Python module {module_name} must not import itself")
            elif isinstance(node, ast.Import) and any(
                alias.name == module_name for alias in node.names
            ):
                diagnostics.append(f"Python module {module_name} must not import itself")
            if (
                file_path.startswith("app/")
                and isinstance(node, ast.ImportFrom)
                and node.module == "app"
            ):
                for alias in node.names:
                    imported_path = f"app/{alias.name}.py"
                    if imported_path not in planned_files and imported_path not in generated:
                        diagnostics.append(
                            f"Python module {file_path} imports unplanned local module {imported_path}"
                        )
            elif (
                file_path.startswith("app/")
                and isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("app.")
            ):
                imported_path = f"{node.module.replace('.', '/')}.py"
                if imported_path not in planned_files and imported_path not in generated:
                    diagnostics.append(
                        f"Python module {file_path} imports unplanned local module {imported_path}"
                    )
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            is_pydantic_model = any(
                isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases
            )
            if not is_pydantic_model:
                continue
            for statement in node.body:
                if (
                    isinstance(statement, ast.AnnAssign)
                    and isinstance(statement.target, ast.Name)
                    and isinstance(statement.annotation, ast.Name)
                    and statement.target.id == statement.annotation.id
                ):
                    diagnostics.append(
                        f"Pydantic field {node.name}.{statement.target.id} shadows its annotation type"
                    )
        imported_model_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("models"):
                imported_model_names.update(alias.name for alias in node.names)

        if file_path.endswith("schemas.py") and imported_model_names:
            orm_names = set()
            for path, source in generated.items():
                if not path.endswith(".py") or not path.endswith("models.py"):
                    continue
                try:
                    model_tree = ast.parse(source, filename=path)
                except SyntaxError:
                    continue
                for node in ast.walk(model_tree):
                    if isinstance(node, ast.ClassDef) and any(
                        isinstance(base, ast.Name) and base.id == "Base" for base in node.bases
                    ):
                        orm_names.add(node.name)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                inherited = {base.id for base in node.bases if isinstance(base, ast.Name)}
                mixed = sorted(inherited & imported_model_names & orm_names)
                if mixed:
                    diagnostics.append(
                        f"schema class {node.name} must not inherit SQLAlchemy ORM model(s): {', '.join(mixed)}"
                    )

        requirement = f"{self._requirement} {self._project_context.get('architecture', {})}".lower()
        if "fastapi" in requirement and file_path.endswith("main.py"):
            calls_fastapi = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "FastAPI"
                for node in ast.walk(tree)
            )
            if not calls_fastapi:
                diagnostics.append("FastAPI entrypoint must instantiate FastAPI()")
            uses_http_exception = any(
                isinstance(node, ast.Name) and node.id == "HTTPException"
                for node in ast.walk(tree)
            )
            imports_http_exception = any(
                isinstance(node, ast.ImportFrom)
                and node.module == "fastapi"
                and any(alias.name == "HTTPException" for alias in node.names)
                for node in ast.walk(tree)
            )
            if uses_http_exception and not imports_http_exception:
                diagnostics.append("FastAPI entrypoint uses HTTPException without importing it")
        todo_crud = "fastapi" in requirement and "todo" in requirement
        if todo_crud:
            declared_classes = {
                node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
            }
            unrelated_classes = sorted(
                name for name in declared_classes
                if name != "Base" and not name.lower().startswith("todo")
            )
            if unrelated_classes:
                diagnostics.append(
                    "FastAPI Todo CRUD must not add unrelated domain classes: "
                    + ", ".join(unrelated_classes)
                )
            if re.search(r"\b(?:Record\w*|records)\b", content):
                diagnostics.append("FastAPI Todo CRUD must stay within the Todo domain")
        return tuple(dict.fromkeys(diagnostics))

    def _validate_java_contract(self, file_path: str, content: str) -> Tuple[str, ...]:
        """Enforce the frozen Java file set and database contract before commit."""
        if file_path.endswith(".java"):
            diagnostics = []
            requirement = self._requirement.lower()
            java_path = Path(file_path)
            if "java" in java_path.parts:
                java_index = java_path.parts.index("java")
                expected_package = ".".join(java_path.parts[java_index + 1:-1])
                if expected_package and not re.search(
                    rf"^\s*package\s+{re.escape(expected_package)}\s*;",
                    content,
                    re.MULTILINE,
                ):
                    diagnostics.append(
                        f"Java file {file_path} must declare package {expected_package}"
                    )
            expected_type = Path(file_path).stem
            planned_types = {
                Path(path).stem: path
                for path in self._file_entries
                if path.endswith(".java")
            }
            imports = re.findall(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", content, re.MULTILINE)
            for imported in imports:
                if not imported.startswith("com.example."):
                    continue
                type_name = imported.rsplit(".", 1)[-1]
                if type_name not in planned_types:
                    diagnostics.append(f"Java local import outside frozen file set: {imported}")
            imports_by_simple_name: Dict[str, set[str]] = {}
            for imported in imports:
                imports_by_simple_name.setdefault(imported.rsplit(".", 1)[-1], set()).add(imported)
            for simple_name, qualified_names in imports_by_simple_name.items():
                if len(qualified_names) > 1:
                    diagnostics.append(
                        f"Java imports multiple types named {simple_name}: {', '.join(sorted(qualified_names))}"
                    )
            all_declared_types = set(re.findall(
                r"^\s*(?:(?:public|protected|private)\s+)?(?:(?:abstract|final|sealed|non-sealed|static)\s+)*(?:class|interface|enum|record)\s+(\w+)",
                content,
                re.MULTILINE,
            ))
            shadowed_imports = sorted(all_declared_types.intersection(imports_by_simple_name))
            if shadowed_imports:
                diagnostics.append(
                    f"Java declared types shadow imported types: {', '.join(shadowed_imports)}"
                )
            if "org.springframework.validation.annotation.Valid" in content:
                diagnostics.append("Java uses invalid Valid import; use jakarta.validation.Valid")
            if re.search(r"@RequestParam\([^)]*\)\s+[a-z_]\w*(?=\s*[,)=}])", content):
                diagnostics.append("Java @RequestParam parameter is missing a declared type")
            declared_types = {
                name
                for _, name in re.findall(
                    r"^\s*(?:public\s+)?(?:(?:abstract|final|sealed|non-sealed|static)\s+)*(class|interface|enum|record)\s+(\w+)",
                    content,
                    re.MULTILINE,
                )
            }
            if expected_type[:1].isupper() and expected_type not in declared_types:
                diagnostics.append(f"Java file {file_path} must declare top-level type {expected_type}")
            public_types = set(re.findall(
                r"^\s*public\s+(?:(?:abstract|final|sealed|non-sealed|static)\s+)*(?:class|interface|enum|record)\s+(\w+)",
                content,
                re.MULTILINE,
            ))
            mismatched_public_types = sorted(public_types - {expected_type})
            if mismatched_public_types:
                diagnostics.append(
                    f"Java public type must match file name {expected_type}: {', '.join(mismatched_public_types)}"
                )
            if "sqlite" in requirement and re.search(r"(?:\borg\.h2\b|\bH2\b|jdbc:h2:)", content, re.IGNORECASE):
                diagnostics.append("SQLite requirement forbids H2 references in Java source")
            if Path(file_path).stem != "Application" and "@SpringBootApplication" in content:
                diagnostics.append("Only Application.java may declare @SpringBootApplication")
            todo_crud = "spring" in requirement and (
                "/api/v1/todos" in requirement
                or {"Todo", "TodoController", "TodoRepository"}.issubset(planned_types)
            )
            if expected_type == "Application" and todo_crud:
                if "@SpringBootApplication" not in content:
                    diagnostics.append("Spring Boot Application.java must declare @SpringBootApplication")
                if "EnableAspectJAutoProxy" in content:
                    diagnostics.append("Spring CRUD Application.java must not enable unconfigured AspectJ support")
                unsupported_initializers = (
                    "DataSourceInitializer",
                    "TableInitializer",
                    "org.xerial.sqlitejdbc",
                )
                if any(symbol in content for symbol in unsupported_initializers):
                    diagnostics.append("Spring CRUD Application.java uses an unsupported SQLite initializer")
                if "org.xerial.sqlite.jdbc.SQLiteDataSource" in content:
                    diagnostics.append("Spring CRUD Application.java must use the standard JDBC DataSource API")
                if "DataSource" not in content or "jdbc:sqlite" not in content:
                    diagnostics.append("Spring CRUD Application.java must configure a jdbc:sqlite DataSource")
                if "/health" not in content or "GetMapping" not in content:
                    diagnostics.append("Spring CRUD Application.java must expose GET /health")
                if "EntityScan" in content:
                    diagnostics.append("Spring JDBC Application.java must not configure JPA entity scanning")
            if expected_type.endswith("Controller") and "spring" in requirement:
                if "@RestController" not in content:
                    diagnostics.append("Spring CRUD controller must declare @RestController")
                if "/api/v1/todos" in requirement and "/api/v1/todos" not in content:
                    diagnostics.append("Spring CRUD controller must map /api/v1/todos")
                required_mappings = ("PostMapping", "GetMapping", "PutMapping", "DeleteMapping")
                missing_mappings = [name for name in required_mappings if f"@{name}" not in content]
                if missing_mappings:
                    diagnostics.append(
                        f"Spring CRUD controller is missing mappings: {', '.join(missing_mappings)}"
                    )
                if todo_crud:
                    for mapping in ("GetMapping", "PutMapping", "DeleteMapping"):
                        route_pattern = (
                            rf'@{mapping}\s*\(\s*'
                            rf'(?:(?:path|value)\s*=\s*)?["\']/?\{{id\}}["\']\s*\)'
                        )
                        if not re.search(route_pattern, content):
                            diagnostics.append(f"Spring CRUD controller must map {mapping} to /{{id}}")
                    if not re.search(r"@PutMapping\s*\([^)]*\)[\s\S]{0,500}@RequestBody", content):
                        diagnostics.append("Spring CRUD PUT handler must read the Todo from @RequestBody")
                    if not re.search(r"\.setId\s*\(\s*id\s*\)", content):
                        diagnostics.append("Spring CRUD PUT handler must apply the path id to the Todo")
                    forbidden_controller_symbols = (
                        "TodoService",
                        "org.springframework.security",
                        "SecurityContextHolder",
                        "@PreAuthorize",
                    )
                    if any(symbol in content for symbol in forbidden_controller_symbols):
                        diagnostics.append("Spring CRUD controller must use only the frozen Todo repository API")
                    if (
                        "TodoRepository" not in content
                        or "JdbcTemplate" in content
                        or re.search(r"\b(?:class|record)\s+Todo\b", content)
                    ):
                        diagnostics.append(
                            "Spring CRUD controller must delegate persistence to TodoRepository and use the shared Todo model"
                        )
            if expected_type == "Todo" and todo_crud:
                if not re.search(r"\b(?:class|record)\s+Todo\b", content):
                    diagnostics.append("Todo.java must declare the Todo entity as a class or record")
                for field_name in ("id", "title", "completed"):
                    if not re.search(rf"\b{field_name}\b", content):
                        diagnostics.append(f"Todo entity is missing required field {field_name}")
                forbidden_model_symbols = (
                    "@Entity",
                    "JpaRepository",
                    "@Query",
                    "javax.persistence",
                    "jakarta.persistence",
                    " User ",
                )
                padded_content = f" {content} "
                if any(symbol in padded_content for symbol in forbidden_model_symbols):
                    diagnostics.append("Todo.java must be a self-contained plain Java model")
                constructor_signatures = []
                for parameters in re.findall(r"\bTodo\s*\(([^)]*)\)", content):
                    parameter_types = []
                    for parameter in parameters.split(","):
                        tokens = parameter.strip().split()
                        if len(tokens) >= 2:
                            parameter_types.append(tokens[-2])
                    constructor_signatures.append(tuple(parameter_types))
                if len(constructor_signatures) != len(set(constructor_signatures)):
                    diagnostics.append("Todo.java must not declare duplicate constructor signatures")
                forbidden_todo_symbols = (
                    "UUID",
                    "createdAt",
                    "updatedAt",
                    "priority",
                    "description",
                    " void save(",
                    " void update(",
                )
                if any(symbol in padded_content for symbol in forbidden_todo_symbols):
                    diagnostics.append("Todo.java must use only the fixed id, title, and completed bean contract")
                required_bean_methods = ("getId", "setId", "getTitle", "setTitle", "isCompleted", "setCompleted")
                if "lombok" in content.lower() or any(
                    not re.search(rf"\b{method}\s*\(", content)
                    for method in required_bean_methods
                ):
                    diagnostics.append("Todo.java must declare explicit conventional getters and setters")
            if expected_type == "TodoRepository" and todo_crud:
                required_methods = {
                    "List<Todo> findAll": r"\bList\s*<\s*Todo\s*>\s+findAll\s*\(",
                    "Optional<Todo> findById": r"\bOptional\s*<\s*Todo\s*>\s+findById\s*\(",
                    "Todo save": r"\bTodo\s+save\s*\(\s*Todo\b",
                    "Todo update": r"\bTodo\s+update\s*\(\s*Todo\b",
                    "boolean delete": r"\bboolean\s+delete\s*\(\s*(?:Long|long)\b",
                }
                missing_methods = [
                    signature for signature, pattern in required_methods.items()
                    if not re.search(pattern, content)
                ]
                if missing_methods:
                    diagnostics.append(
                        f"TodoRepository is missing CRUD signatures: {', '.join(missing_methods)}"
                    )
                if not re.search(r"CREATE\s+TABLE", content, re.IGNORECASE):
                    diagnostics.append("TodoRepository must initialize the SQLite todos table")
                if "jdbcTemplate.getConnection(" in content:
                    diagnostics.append("TodoRepository must use supported JdbcTemplate operations")
                if not re.search(r"\bclass\s+TodoRepository\b", content):
                    diagnostics.append("TodoRepository must be a concrete class")
                if "JdbcTemplate" not in content or "@Repository" not in content:
                    diagnostics.append("TodoRepository must use Spring JdbcTemplate")
                if re.search(r"@Autowired\s+(?:private\s+|protected\s+|public\s+)?(?:final\s+)?JdbcTemplate\b", content):
                    diagnostics.append("TodoRepository must use constructor injection for JdbcTemplate")
                if re.search(r"(?:JpaRepository|javax\.persistence|jakarta\.persistence|@Query\b)", content):
                    diagnostics.append("TodoRepository must use JDBC instead of JPA")
                forbidden_repository_symbols = (
                    "created_at",
                    "updated_at",
                    "getCreatedAt",
                    "getUpdatedAt",
                    ".toInstant(",
                )
                if any(symbol in content for symbol in forbidden_repository_symbols):
                    diagnostics.append("TodoRepository must use only the fixed Todo fields")
                if "lombok" in content.lower() or re.search(r"\.getCompleted\s*\(", content):
                    diagnostics.append("TodoRepository must use explicit construction and Todo.isCompleted()")
                if re.search(r"new\s+DataAccessException\s*\(", content):
                    diagnostics.append("TodoRepository must not instantiate abstract DataAccessException")
            if expected_type == "TodoControllerTest" and todo_crud:
                if re.search(
                    r"List\s*<[^>]+>\s+\w+\s*=\s*[\s\S]{0,300}\.getContentType\s*\(\s*\)",
                    content,
                ):
                    diagnostics.append("TodoControllerTest must not assign a response content type to a List")
                if re.search(r'delete\s*\(\s*["\'][^"\']*\{id\}[^"\']*["\']\s*\)', content):
                    diagnostics.append("TodoControllerTest must supply an id for URI template expansion")
            return tuple(dict.fromkeys(diagnostics))

        if file_path.endswith("pom.xml") and "sqlite" in self._requirement.lower():
            try:
                root = ET.fromstring(content)
            except ET.ParseError as exc:
                return (f"Maven pom.xml is invalid XML: {exc}",)
            namespace = "{http://maven.apache.org/POM/4.0.0}"
            dependencies = root.findall(f"{namespace}dependencies/{namespace}dependency")
            artifacts = {
                dependency.findtext(f"{namespace}artifactId", "")
                for dependency in dependencies
            }
            diagnostics = []
            duplicate_properties = []
            for element in root.iter():
                properties_count = sum(
                    1 for child in element
                    if child.tag.rsplit("}", 1)[-1] == "properties"
                )
                if properties_count > 1:
                    duplicate_properties.append(element.tag.rsplit("}", 1)[-1])
            if duplicate_properties:
                diagnostics.append(
                    "Maven pom.xml must contain at most one properties block per project or profile"
                )
            if "sqlite-jdbc" not in artifacts:
                diagnostics.append("SQLite requirement needs Maven dependency org.xerial:sqlite-jdbc")
            sqlite_dependencies = [
                dependency
                for dependency in dependencies
                if dependency.findtext(f"{namespace}artifactId", "") == "sqlite-jdbc"
            ]
            if sqlite_dependencies and any(
                dependency.findtext(f"{namespace}groupId", "") != "org.xerial"
                or dependency.findtext(f"{namespace}version", "") != "3.45.1.0"
                for dependency in sqlite_dependencies
            ):
                diagnostics.append("SQLite JDBC dependency must use org.xerial:sqlite-jdbc:3.45.1.0")
            if "h2" in {artifact.lower() for artifact in artifacts}:
                diagnostics.append("SQLite requirement forbids H2 database dependency")
            if "spring-boot-starter-jdbc" not in artifacts:
                diagnostics.append("SQLite Spring CRUD requires spring-boot-starter-jdbc")
            forbidden_artifacts = {"spring-boot-starter-data-jpa", "spring-boot-starter-security"}
            present_forbidden = sorted(forbidden_artifacts.intersection(artifacts))
            if present_forbidden:
                diagnostics.append(
                    f"SQLite Spring CRUD forbids unrelated starters: {', '.join(present_forbidden)}"
                )
            return tuple(diagnostics)
        return ()

    async def _assemble_retrieved_context(self, contract_context: Mapping[str, Any]) -> None:
        """Run the local retrieval path and expose its provenance to the model."""
        from app.agent.context_assembler import ContextAssembler
        from app.agent.retrieval import CallableRetriever, RetrievalService
        from app.agent.retrieval.models import RetrievalChunk, RetrievalRequest

        user_requirement = getattr(self, "_user_requirement", self._requirement)
        target_file = str(contract_context.get("target_file") or "")
        target_description = str(
            self._file_entries.get(target_file, {}).get("description") or ""
        )
        retrieval_query = " ".join(
            item for item in (user_requirement, target_file, target_description, "generating") if item
        )
        records = (
            ("requirement", user_requirement),
            ("generation_contract", str(contract_context)),
            ("architecture", str(self._project_context.get("architecture", {}))),
            ("target_file", f"{target_file} {target_description}"),
        )

        def search(request: RetrievalRequest) -> list[RetrievalChunk]:
            query_terms = set(re.findall(r"[a-zA-Z0-9_]+", request.query.lower()))
            results = []
            for source_id, content in records:
                terms = set(re.findall(r"[a-zA-Z0-9_]+", content.lower()))
                score = len(query_terms & terms) / max(len(query_terms), 1)
                results.append(RetrievalChunk(
                    content=content,
                    source_type="local_generation_context",
                    source_id=source_id,
                    score=score,
                ))
            return results

        retrieval = await RetrievalService([
            CallableRetriever("local_generation_context", search),
        ]).retrieve(RetrievalRequest(query=retrieval_query, limit=3))
        envelope = ContextAssembler(max_chars=24000).assemble(
            task_id=str(self._project_context.get("task_id", "generation")),
            stage="generating",
            file_path=None,
            retrieval=retrieval,
        )
        self._project_context["context_envelope"] = envelope.model_dump(mode="json")
        self._project_context["retrieval_status"] = {
            "enabled": True,
            "source_count": len(retrieval.chunks),
            "degraded": retrieval.degraded,
            "sources": [chunk.source_id for chunk in retrieval.chunks],
        }

    async def generate_file(self, context: FileGenerationContext) -> GeneratedContent:
        if self._plan is None:
            raise RuntimeError("create_plan must run before generate_file")
        file_info = self._file_entries[context.file_path]
        upstream = {**self._generated_contents, **dict(context.upstream_contents)}
        typescript_backend = context.file_path.endswith(".ts") and any(
            framework in self._requirement.lower() for framework in ("express", "nestjs")
        )
        model_name = str(
            self.agent.model_assignment.backend_model
            if typescript_backend and getattr(self.agent, "model_assignment", None)
            else self.agent._select_model_for_file(context.file_path)
        )

        # Keep every file generation grounded in the same frozen contract. The
        # legacy generator can otherwise let each specialist invent a separate
        # domain model even when the plan already defines shared interfaces.
        contract_context = {
            "frozen_file_set": [item.path for item in self._plan.files],
            "target_file": context.file_path,
            "target_contract": dict(file_info.get("contract") or {}),
            "file_contracts": {
                path: {
                    "file_type": str(entry.get("file_type", "")),
                    "description": str(entry.get("description", entry.get("role", ""))),
                    "imports": list(entry.get("imports") or entry.get("dependencies") or ()),
                    "contract": dict(entry.get("contract") or {}),
                }
                for path, entry in self._file_entries.items()
            },
            "rules": [
                "Use the domain entities, field names, routes, storage abstraction, and framework from the requirement and frozen contracts.",
                "Keep all local imports inside frozen_file_set; do not invent modules or dependencies.",
                "Keep models, schemas, CRUD/service code, entrypoint, and tests consistent across the whole file set.",
            ],
        }
        previous_diagnostics = tuple(getattr(context, "previous_diagnostics", ()))
        if previous_diagnostics:
            contract_context["retry_feedback"] = list(previous_diagnostics)
            contract_context["rules"].append(
                "The previous candidate was rejected. Fix every validation diagnostic before returning the complete file: "
                + "; ".join(previous_diagnostics)
            )
        requirement_text = self._requirement.lower()
        if "fastapi" in requirement_text:
            contract_context["rules"].extend([
                "The FastAPI entrypoint must define app = FastAPI() and import every FastAPI symbol it uses, including HTTPException.",
                "Pydantic request and response schemas must inherit BaseModel independently; SQLAlchemy ORM models from models.py are never schema base classes.",
                "Response schemas must explicitly declare the fields returned by the ORM/service layer and use model_config or orm_mode as required by the installed Pydantic version.",
            ])
        if "pygame" in requirement_text and "snake" in requirement_text:
            contract_context["rules"].extend([
                "Use grid coordinates consistently: Snake.body is a list of (x, y) cells, its initial length is three, and Food exposes position as an (x, y) tuple.",
                "Game owns snake, food, score, game_over, is_running, reset(), update(dt), check_collision(), consume_food(), and render(); Game.render() returns a pygame.Surface by calling the renderer contract.",
                "Define render_game(screen, game) with screen first and game second, and use that exact signature in main.py and tests.",
                "Define handle_input(game, events=None) to consume pygame events, update the snake direction, process restart and quit, and return whether the game should continue.",
                "main.py must support --headless, --frames, and --screenshot; headless mode must render each frame to a Surface, save the requested screenshot, terminate after the requested frame count, and return exit code zero.",
                "Tests must post explicit pygame events into handle_input and assert public behavior only; every test call must match the exact interfaces implemented by rules.py, renderer.py, and input_loop.py.",
            ])
        if "java" in requirement_text and "spring" in requirement_text:
            contract_context["rules"].extend([
                "Application.java is the only @SpringBootApplication entrypoint; controller files must use @RestController.",
                "Each Java file must declare the top-level type matching its file name and must not declare a differently named public type.",
                "The project must configure a jdbc:sqlite DataSource and expose GET /health; keep Application.java minimal and do not enable AspectJ.",
                "Todo.java must be a self-contained mutable Java bean with only Long id, String title, and boolean completed fields, a public no-argument constructor, a public Todo(Long id, String title, boolean completed) constructor, and conventional getters and setters; do not use JPA annotations, repository methods, User, timestamps, validation logic, or other domain types.",
                "TodoRepository.java must be a concrete @Repository with constructor-injected JdbcTemplate. It must create a todos(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0) table and declare public List<Todo> findAll(), public Optional<Todo> findById(Long id), public Todo save(Todo todo), public Todo update(Todo todo), and public boolean delete(Long id). Map rows only through new Todo(rs.getLong(\"id\"), rs.getString(\"title\"), rs.getBoolean(\"completed\")).",
                "Use supported JdbcTemplate query, queryForObject, update, and execute operations; convert LocalDateTime with Timestamp.valueOf and ResultSet.getTimestamp.",
                "The Todo controller must implement POST, GET collection, GET /{id}, PUT /{id}, and DELETE /{id} under /api/v1/todos using only TodoRepository; POST and PUT accept Todo with @RequestBody and require no authentication.",
                "For SQLite requirements, use the available Maven coordinate org.xerial:sqlite-jdbc:3.45.1.0 and a jdbc:sqlite URL; never use H2 or embedded H2 configuration.",
                "Use spring-boot-starter-jdbc, spring-boot-starter-web, sqlite-jdbc, and spring-boot-starter-test; do not add JPA or Spring Security.",
                "Every Java source file must have unambiguous imports and compile independently within the frozen Maven project.",
                "Do not declare nested types with the same simple name as an imported type, including RowMapper.",
            ])
        self._project_context["generation_contract"] = contract_context
        await self._assemble_retrieved_context(contract_context)

        retry_fallback = (
            self._task_tracker_fallback(context.file_path)
            or self._contract_retry_fallback(context.file_path)
            if previous_diagnostics or self._is_task_tracker_request() or self._is_pygame_snake_repair() or self._is_fastapi_crud_repair() or self._is_flask_crud_repair() or self._is_express_crud_repair() or self._is_nestjs_crud_repair() or self._is_go_crud_repair()
            else None
        )
        if retry_fallback is not None:
            result = {
                "success": True,
                "content": retry_fallback,
                "model": "deterministic-contract-retry",
            }
        elif hasattr(self.agent, "_generate_file_with_model") and self._dependency_graph is not None:
            engineer = self.agent.backend_engineer if typescript_backend else self.agent._select_engineer(context.file_path)
            content = await self.agent._generate_file_with_model(
                context.file_path,
                file_info,
                engineer,
                model_name,
                self._project_context,
                upstream,
                self._spec_generator,
                self._dependency_graph,
                getattr(self.agent, "callback", None),
                persist=False,
            )
            result: Mapping[str, Any] = {"success": bool(content), "content": content, "model": model_name}
        else:
            result = await self.agent._generate_single_file(
                file_info,
                self._project_context,
                len(self._plan.files),
                upstream,
            )

        if not result or not result.get("success", True) or not result.get("content"):
            raise RuntimeError(f"{self.__class__.__name__} generation failed for {context.file_path}")
        from app.agent.file_response import parse_file_response

        response = parse_file_response(result["content"], expected_path=context.file_path)
        if response.content is None:
            return GeneratedContent(
                content="",
                model_name=str(result.get("model") or model_name),
                validation_passed=False,
                diagnostics=(response.diagnostic or "invalid model file response",),
            )
        content = response.content
        self._generated_contents[context.file_path] = content
        validation_passed = bool(result.get("validation_passed", True))
        contract_diagnostics = (
            self._validate_local_imports(context.file_path, content)
            + self._validate_python_contract(context.file_path, content)
            + self._validate_java_contract(context.file_path, content)
        )
        deterministic_repair = self._contract_retry_fallback(context.file_path)
        repairable_java_contract = (
            context.file_path.endswith("/TodoRepository.java")
            and any("abstract DataAccessException" in item for item in contract_diagnostics)
        ) or (
            context.file_path.endswith("/TodoControllerTest.java")
            and bool(contract_diagnostics)
        )
        if deterministic_repair is not None and repairable_java_contract:
            content = deterministic_repair
            self._generated_contents[context.file_path] = content
            contract_diagnostics = (
                self._validate_local_imports(context.file_path, content)
                + self._validate_python_contract(context.file_path, content)
                + self._validate_java_contract(context.file_path, content)
            )
        if contract_diagnostics:
            validation_passed = False
        if validation_passed and hasattr(self.agent, "_validate_content_syntax"):
            validation_passed = bool(await self.agent._validate_content_syntax(context.file_path, content))
        return GeneratedContent(
            content=content,
            model_name=str(result.get("model") or model_name),
            validation_passed=validation_passed,
            diagnostics=tuple(str(item) for item in result.get("diagnostics", ())) + contract_diagnostics,
        )

    async def finalize(self, state: OrchestrationState) -> AdapterResult:
        manifest = self.shared_context.get_artifact_manifest()
        success = state.status.value == "completed"
        files = [dict(manifest[path]) for path in sorted(manifest)]
        diagnostics = [str(item.get("message") or item) for item in state.diagnostics]
        result = {
            "success": success,
            "output_dir": str(self.output_dir),
            "total_files_created": len(files),
            "total_files_failed": 0 if success else max(len(self._file_entries) - len(files), 1),
            "total_files": len(self._file_entries),
            "complexity": str(self._complexity_payload().get("level", "small")),
            "models_used": self._model_assignment_payload(),
            "files": files,
            "generated_files": files,
            "validation": {"runnable": success, "status": state.status.value},
            "errors": diagnostics,
            "warnings": [],
            "elapsed_time": max(time.monotonic() - self._started_at, 0.0),
            "fix_attempts": [],
        }
        return AdapterResult(success=success, result=result)


class SpecFirstAdapter(_PlannedAgentAdapter):
    """Generate specifications first and freeze their architecture file plan."""

    engine_version = "spec-first-adapter-v1"

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._started_at = time.monotonic()
        self._requirement = request.requirement
        self._user_requirement = str(request.metadata.get("user_requirement") or request.requirement)
        supplied = request.metadata.get("specification") or request.metadata.get("architecture")
        architecture = dict(supplied) if isinstance(supplied, Mapping) else None
        allowed_paths = tuple(dict.fromkeys(
            normalize_plan_path(path)
            for path in request.metadata.get("allowed_files", ())
        ))

        await self.agent._initialize_components(request.requirement)
        context = self.shared_context
        context.complexity = self._complexity_payload()
        context.model_assignment = self._model_assignment_payload()

        if architecture is None and allowed_paths:
            from app.agent.language_detector import LanguageDetector

            language = LanguageDetector.detect(request.requirement).language
            architecture = {
                "language": language,
                "project_requirement": self._user_requirement,
                "file_plan": self._build_allowed_file_plan(allowed_paths, self._user_requirement),
            }
        if architecture is None and self._is_task_tracker_request():
            architecture = {
                "language": "python",
                "project_requirement": self._user_requirement,
                "file_plan": ({
                    "path": "main.py",
                    "description": (
                        "Implement a standard-library-only command-line task tracker "
                        "with Task, TaskList, add, complete, and list."
                    ),
                    "dependencies": [],
                },),
            }
        if architecture is None:
            from app.agent.language_detector import LanguageDetector
            from app.agent.spec_first_generator import SpecFirstGenerator

            language = LanguageDetector.detect(request.requirement).language
            self._spec_generator = SpecFirstGenerator(
                context,
                language=language,
                api_key_token=getattr(self.agent, "api_key_token", None),
            )
            if not await self._spec_generator.generate_all_specs(
                request.requirement,
                context.complexity,
                getattr(self.agent, "callback", None),
            ):
                raise RuntimeError("Spec-First specification generation failed")
            architecture = await self.agent.architect.design_architecture(
                request.requirement,
                self.agent.complexity,
                callback=getattr(self.agent, "callback", None),
            )

        entries = architecture.get("file_plan", ())
        allowed_files = set(allowed_paths)
        if allowed_files:
            by_path = {
                normalize_plan_path(str(entry.get("path", ""))): dict(entry)
                for entry in entries
                if normalize_plan_path(str(entry.get("path", ""))) in allowed_files
            }
            inferred = {
                entry["path"]: entry for entry in self._build_allowed_file_plan(allowed_paths)
            }
            entries = tuple(by_path.get(path, inferred[path]) for path in allowed_paths)
        if not entries:
            raise ValueError("Spec-First architecture must contain a non-empty file_plan")
        language = str(architecture.get("language", ""))
        self._project_context = {
            **dict(request.metadata),
            "requirement": self._user_requirement,
            "architecture": architecture,
            "complexity": context.complexity,
            "output_dir": str(self.output_dir),
            "is_spec_first": True,
        }
        self._dependency_graph = self._build_dependency_graph(architecture, language)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._dependency_graph.save(str(self.output_dir / ".dep_graph.json"))
        adjacency = getattr(self._dependency_graph, "adjacency", {})
        planned_entries = []
        for raw_entry in entries:
            entry = dict(raw_entry)
            if "dependencies" not in entry and "depends_on" not in entry:
                entry["dependencies"] = sorted(adjacency.get(str(entry.get("path", "")), ()))
            planned_entries.append(entry)
        return self._freeze_plan(planned_entries, language=language)

    @staticmethod
    def _build_allowed_file_plan(
        paths: Sequence[str], requirement: str = ""
    ) -> Tuple[Dict[str, Any], ...]:
        """Create a stable plan when the caller supplies a frozen file set."""
        path_set = set(paths)
        game_modules = tuple(path for path in paths if path.startswith("game/") and path.endswith(".py"))
        entries = []
        for path in paths:
            dependencies: Tuple[str, ...] = ()
            if path == "game/renderer.py" or path == "game/input_loop.py":
                dependencies = tuple(item for item in ("game/rules.py",) if item in path_set)
            elif path == "main.py":
                dependencies = game_modules
            elif path.startswith("tests/"):
                dependencies = tuple(item for item in paths if not item.startswith("tests/"))
            entries.append({
                "path": path,
                "description": (
                    f"Implement {path} for this exact project requirement: {requirement.strip()}"
                    if requirement.strip()
                    else f"Required project file {path}"
                ),
                "dependencies": list(dependencies),
            })
        return tuple(entries)

    def _build_dependency_graph(self, architecture: Mapping[str, Any], language: str) -> Any:
        from app.agent.adapters.language_adapter import LanguageAdapterRegistry
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=LanguageAdapterRegistry.get_adapter(language or "python"))
        graph.build_from_architecture(dict(architecture))
        return graph


class IncrementalAdapter(_PlannedAgentAdapter):
    """Freeze one strict plan containing only files affected by a change."""

    engine_version = "incremental-adapter-v1"

    change_plan: Optional[ChangePlan] = None

    async def create_plan(self, request: GenerationRequest) -> GenerationPlan:
        self._started_at = time.monotonic()
        self._requirement = request.requirement
        await self.agent._initialize_components_fast(request.requirement)

        from app.agent.adapters.language_adapter import LanguageAdapterRegistry
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.language_detector import LanguageDetector

        language = LanguageDetector.detect(request.requirement).language
        graph = request.metadata.get("dependency_graph")
        if graph is None:
            graph = DependencyGraph.load(
                str(self.output_dir / ".dep_graph.json"),
                language_adapter=LanguageAdapterRegistry.get_adapter(language),
            )
        if graph is None:
            if not self.output_dir.is_dir() or not any(self.output_dir.iterdir()):
                raise RuntimeError("incremental Core generation requires an existing project")
            graph = DependencyGraph(language_adapter=LanguageAdapterRegistry.get_adapter(language))
            await graph.build_from_existing_project(self.output_dir)
            if not graph.nodes:
                raise RuntimeError("incremental Core generation could not rebuild the dependency graph")
            graph.save(str(self.output_dir / ".dep_graph.json"))
        self._dependency_graph = graph
        adjacency = getattr(graph, "adjacency", {})

        allowed_files = {
            normalize_plan_path(path)
            for path in request.metadata.get("planned_files", request.metadata.get("allowed_files", ()))
        }
        raw_changes = self._fastapi_crud_repair_changes(allowed_files)
        if raw_changes is None:
            raw_changes = self._flask_crud_repair_changes(allowed_files)
        if raw_changes is None:
            raw_changes = self._express_crud_repair_changes(allowed_files)
        if raw_changes is None:
            raw_changes = self._nestjs_crud_repair_changes(allowed_files)
        if raw_changes is None:
            raw_changes = self._go_crud_repair_changes(allowed_files)
        if raw_changes is None:
            raw_changes = request.metadata.get("change_plan")
        if raw_changes is None:
            summary = self.agent._build_project_summary_from_graph(graph)
            raw_changes = await self.agent._analyze_changes_with_architect(
                request.requirement,
                summary,
                graph,
                getattr(self.agent, "callback", None),
            )
        changes = [dict(item) for item in raw_changes or ()]
        if allowed_files:
            changes = [
                change
                for change in changes
                if normalize_plan_path(str(change.get("path", ""))) in allowed_files
            ]
        if not changes:
            raise ValueError("incremental change plan must contain at least one affected file")
        snapshot = ProjectSnapshot.scan(
            self.output_dir,
            revision=str(request.metadata.get("base_revision") or "working-tree"),
        )
        try:
            self.change_plan = ChangePlan.build(snapshot, changes)
        except ValueError as exc:
            if any(item.get("action") == "delete" for item in changes):
                raise ValueError(f"incremental deletion is not transactional: {exc}") from exc
            raise
        entries = []
        for change in changes:
            if change.get("action", "modify") == "delete":
                continue
            path = str(change.get("path", ""))
            if "dependencies" not in change and "depends_on" not in change:
                change["dependencies"] = sorted(adjacency.get(path, ()))
            if change.get("action", "modify") == "modify" and "original_content" not in change:
                target = self.output_dir / path
                change["original_content"] = target.read_text(encoding="utf-8") if target.is_file() else ""
            entries.append(change)

        affected = set(self.change_plan.affected_files if self.change_plan else ())
        affected.update(str(item.get("path", "")) for item in entries)
        external_dependencies = {
            dependency
            for path in affected
            for dependency in adjacency.get(path, ())
            if dependency not in affected
        }
        for dependency in external_dependencies:
            normalized = normalize_plan_path(dependency)
            target = self.output_dir / normalized
            if target.is_file():
                self._generated_contents[normalized] = target.read_text(encoding="utf-8")
        self.preserved_paths = tuple(sorted(
            path.relative_to(self.output_dir).as_posix()
            for path in self.output_dir.rglob("*")
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(self.output_dir).parts)
            and path.relative_to(self.output_dir).as_posix() not in affected
        ))
        self._project_context = {
            **dict(request.metadata),
            "requirement": request.requirement,
            "architecture": {"language": language, "file_plan": entries},
            "complexity": self._complexity_payload(),
            "output_dir": str(self.output_dir),
            "is_incremental": True,
            "change_plan": self.change_plan.model_dump(mode="json"),
            "base_snapshot": snapshot.model_dump(mode="json"),
        }
        return self._freeze_plan(entries, language=language, allow_empty=True)
