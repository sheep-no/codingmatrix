from pathlib import Path

import pytest

from app.agent.orchestration import (
    CORE_ENGINE,
    LEGACY_ENGINE,
    GenerationRequest,
    IncrementalAdapter,
    SpecFirstAdapter,
    TraditionalAdapter,
    engine_metadata,
    execute_core_generation,
    select_engine,
)
from app.agent.workflow_registry import build_legacy_workflow, run_workflow
from app.agent.orchestrator_generation.spec_first_generate import SpecFirstGenerateMixin


class _Architect:
    async def design_architecture(self, requirement, complexity, callback=None):
        return {
            "language": "python",
            "file_plan": [
                {"path": "app.py", "description": "application entry point"},
                {"path": "config.py", "description": "configuration", "depends_on": ["app.py"]},
            ],
        }


class _Agent:
    def __init__(self, tmp_path):
        self.architect = _Architect()
        self.complexity = object()
        self.callback = None
        self.output_dir = Path(tmp_path)

    async def _initialize_components(self, requirement):
        self.initialized_requirement = requirement

    async def _generate_single_file(self, file_info, project_context, total_files, generated_contents):
        return {"success": True, "content": f"# {file_info['path']}\n", "model": "test-model"}

    def _select_model_for_file(self, file_path):
        return "fallback-model"

    async def _initialize_components_fast(self, requirement):
        self.initialized_requirement = requirement


class _CoreFileAgent(_Agent):
    def _select_engineer(self, file_path):
        return object()

    async def _generate_file_with_model(
        self,
        file_path,
        file_info,
        engineer,
        model_name,
        project_context,
        generated_contents,
        spec_generator,
        dependency_graph,
        callback,
        *,
        persist=True,
    ):
        self.persist_requested = persist
        self.generation_contract = project_context.get("generation_contract")
        self.project_context = project_context
        return f"# {file_path}\n"


@pytest.mark.asyncio
async def test_typescript_syntax_validation_accepts_nestjs_decorators():
    content = '''
import { Controller, Get } from "@nestjs/common";

@Controller("health")
export class HealthController {
  @Get()
  check(): { status: string } {
    return { status: "ok" };
  }
}
'''

    assert await SpecFirstGenerateMixin()._validate_content_syntax("src/main.ts", content)


@pytest.mark.asyncio
async def test_typescript_syntax_validation_rejects_invalid_syntax():
    content = "export class Broken { check(: string { return 'bad'; } }\n"

    assert not await SpecFirstGenerateMixin()._validate_content_syntax("src/main.ts", content)


def test_java_contract_rejects_local_imports_outside_frozen_files(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
    }

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoController.java",
        "import com.example.dto.TodoRequest;\n"
        "import org.springframework.validation.annotation.Valid;\n"
        "class TodoController { @RequestParam(defaultValue = \"0\") page }\n",
    )

    assert any("outside frozen file set" in item for item in diagnostics)
    assert any("invalid Valid import" in item for item in diagnostics)
    assert any("missing a declared type" in item for item in diagnostics)


def test_java_contract_requires_sqlite_and_rejects_h2(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."

    diagnostics = adapter._validate_java_contract(
        "pom.xml",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
          <dependencies><dependency><artifactId>h2</artifactId></dependency></dependencies>
        </project>""",
    )

    assert "SQLite requirement needs Maven dependency org.xerial:sqlite-jdbc" in diagnostics
    assert "SQLite requirement forbids H2 database dependency" in diagnostics


def test_java_contract_requires_available_sqlite_jdbc_coordinate(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."

    diagnostics = adapter._validate_java_contract(
        "pom.xml",
        """<project xmlns="http://maven.apache.org/POM/4.0.0"><dependencies>
          <dependency><groupId>org.xerial</groupId><artifactId>sqlite-jdbc</artifactId><version>3.45.1</version></dependency>
          <dependency><artifactId>spring-boot-starter-jdbc</artifactId></dependency>
        </dependencies></project>""",
    )

    assert "SQLite JDBC dependency must use org.xerial:sqlite-jdbc:3.45.1.0" in diagnostics


def test_java_contract_rejects_duplicate_maven_properties_blocks(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."

    diagnostics = adapter._validate_java_contract(
        "pom.xml",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
          <properties/><properties/>
          <dependencies>
            <dependency><artifactId>sqlite-jdbc</artifactId></dependency>
            <dependency><artifactId>spring-boot-starter-jdbc</artifactId></dependency>
          </dependencies>
        </project>""",
    )

    assert "Maven pom.xml must contain at most one properties block per project or profile" in diagnostics


def test_java_contract_rejects_ambiguous_imports_and_h2_source(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."
    adapter._file_entries = {"src/main/java/com/example/TodoRepository.java": {}}

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "import jakarta.persistence.Query;\n"
        "import org.springframework.data.jpa.repository.Query;\n"
        "class TodoRepository { String url = \"jdbc:h2:mem:test\"; }\n",
    )

    assert any("multiple types named Query" in item for item in diagnostics)
    assert "SQLite requirement forbids H2 references in Java source" in diagnostics


def test_java_contract_rejects_declared_type_that_shadows_import(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."
    adapter._file_entries = {"src/main/java/com/example/TodoRepository.java": {}}

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "package com.example;\n"
        "import org.springframework.jdbc.core.RowMapper;\n"
        "public class TodoRepository {\n"
        "  private static class RowMapper implements java.sql.RowMapper<Todo> {}\n"
        "}\n",
    )

    assert "Java declared types shadow imported types: RowMapper" in diagnostics


def test_java_contract_requires_matching_package_and_rejects_compile_hazards(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence."
    adapter._file_entries = {
        "src/main/java/com/example/Application.java": {},
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    application_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Application.java",
        "import org.xerial.sqlite.jdbc.SQLiteDataSource;\n"
        "@SpringBootApplication public class Application {}",
    )
    todo_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Todo.java",
        "package com.example; public class Todo { Long id; String title; boolean completed; "
        "Long createdAt; public Todo(Long id, String title, boolean completed) {} "
        "public Todo(Long otherId, String otherTitle, boolean otherCompleted) {} }",
    )
    repository_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "package com.example; @Repository public class TodoRepository { JdbcTemplate jdbcTemplate; "
        "List<Todo> findAll(){return null;} Optional<Todo> findById(Long id){return null;} "
        "Todo save(Todo todo){ todo.getCreatedAt().toInstant(); return todo; } "
        "Todo update(Todo todo){return todo;} boolean delete(Long id){return false;} "
        "String ddl=\"CREATE TABLE todos\"; }",
    )

    assert any("must declare package com.example" in item for item in application_diagnostics)
    assert any("standard JDBC DataSource" in item for item in application_diagnostics)
    assert "Todo.java must not declare duplicate constructor signatures" in todo_diagnostics
    assert "Todo.java must use only the fixed id, title, and completed bean contract" in todo_diagnostics
    assert "TodoRepository must use only the fixed Todo fields" in repository_diagnostics


def test_java_contract_enforces_spring_crud_controller_shape(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoController.java",
        "@SpringBootApplication\nclass TodoController {}\n",
    )

    assert "Only Application.java may declare @SpringBootApplication" in diagnostics
    assert "Spring CRUD controller must declare @RestController" in diagnostics
    assert "Spring CRUD controller must map /api/v1/todos" in diagnostics
    assert any("PostMapping" in item and "DeleteMapping" in item for item in diagnostics)
    assert any("GetMapping" in item and "/{id}" in item for item in diagnostics)


def test_java_contract_accepts_named_spring_mapping_attributes(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoController.java",
        """package com.example;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/todos")
public class TodoController {
  private final TodoRepository repository;
  TodoController(TodoRepository repository) { this.repository = repository; }
  @PostMapping Todo post(@RequestBody Todo todo) { return repository.save(todo); }
  @GetMapping Object list() { return repository.findAll(); }
  @GetMapping(path = "/{id}") Object get() { return null; }
  @PutMapping(value = "/{id}") Object put(@RequestBody Todo todo) { return null; }
  @DeleteMapping(path="/{id}") void delete() {}
}
""",
    )

    assert not any("must map" in item and "/{id}" in item for item in diagnostics)


def test_java_crud_retry_fallback_stabilizes_runtime_contracts(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    pom = adapter._java_crud_retry_fallback("pom.xml")
    todo = adapter._java_crud_retry_fallback("src/main/java/com/example/Todo.java")
    application = adapter._java_crud_retry_fallback("src/main/java/com/example/Application.java")
    repository = adapter._java_crud_retry_fallback("src/main/java/com/example/TodoRepository.java")
    controller = adapter._java_crud_retry_fallback("src/main/java/com/example/TodoController.java")
    controller_test = adapter._java_crud_retry_fallback(
        "src/test/java/com/example/TodoControllerTest.java"
    )

    assert pom is not None
    assert todo is not None
    assert application is not None
    assert repository is not None
    assert controller is not None
    assert controller_test is not None
    candidates = {
        "pom.xml": pom,
        "src/main/java/com/example/Todo.java": todo,
        "src/main/java/com/example/Application.java": application,
        "src/main/java/com/example/TodoRepository.java": repository,
        "src/main/java/com/example/TodoController.java": controller,
        "src/test/java/com/example/TodoControllerTest.java": controller_test,
    }
    for path, content in candidates.items():
        assert adapter._validate_java_contract(path, content) == ()


def test_java_contract_rejects_invalid_mockmvc_response_types(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
        "src/test/java/com/example/TodoControllerTest.java": {},
    }

    diagnostics = adapter._validate_java_contract(
        "src/test/java/com/example/TodoControllerTest.java",
        'class TodoControllerTest { void test() { List<String> titles = mockMvc.perform(get("/api/v1/todos"))'
        '.andReturn().getResponse().getContentType(); mockMvc.perform(delete("/api/v1/todos/{id}")); } }',
    )

    assert "TodoControllerTest must not assign a response content type to a List" in diagnostics
    assert "TodoControllerTest must supply an id for URI template expansion" in diagnostics


def test_python_contract_rejects_module_self_import(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Python FastAPI CRUD API with SQLite persistence."

    diagnostics = adapter._validate_python_contract(
        "app/main.py",
        "from app.main import app as fastapi_app\nfrom fastapi import FastAPI\napp = FastAPI()\n",
    )

    assert "Python module app.main must not import itself" in diagnostics


def test_python_contract_rejects_unplanned_local_module_import(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._file_entries = {
        "app/main.py": {},
        "app/models.py": {},
        "app/schemas.py": {},
        "app/crud.py": {},
    }

    diagnostics = adapter._validate_python_contract(
        "app/main.py",
        "from app import crud, database, models, schemas\n",
    )

    assert "Python module app/main.py imports unplanned local module app/database.py" in diagnostics
    assert len(diagnostics) == 1


def test_python_contract_rejects_pydantic_type_shadowing_and_domain_drift(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Python FastAPI Todo CRUD API with SQLite persistence."

    diagnostics = adapter._validate_python_contract(
        "app/schemas.py",
        "from datetime import date\nfrom pydantic import BaseModel\n"
        "class RecordSchema(BaseModel):\n    date: date\n",
    )

    assert "Pydantic field RecordSchema.date shadows its annotation type" in diagnostics
    assert any("unrelated domain classes" in item for item in diagnostics)
    assert "FastAPI Todo CRUD must stay within the Todo domain" in diagnostics


def test_fastapi_crud_retry_fallback_stabilizes_contracts(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a CRUD todo API with SQLite persistence."
    adapter._project_context = {"architecture": {"framework": "fastapi"}}
    adapter._file_entries = {
        "app/main.py": {},
        "app/models.py": {},
        "app/schemas.py": {},
        "app/crud.py": {},
        "tests/test_crud.py": {},
    }

    for path in adapter._file_entries:
        content = adapter._fastapi_crud_retry_fallback(path)
        assert content is not None
        assert adapter._validate_python_contract(path, content) == ()


def test_fastapi_crud_compile_repair_uses_contract_fallback(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Repair the existing python fastapi CRUD project. "
        "Preserve create, list, get, update, and delete."
    )
    adapter._file_entries = {
        "app/main.py": {},
        "app/models.py": {},
        "app/schemas.py": {},
        "app/crud.py": {},
        "tests/test_crud.py": {},
    }

    assert adapter._is_fastapi_crud_repair() is True
    assert adapter._contract_retry_fallback("app/models.py") is not None
    changes = adapter._fastapi_crud_repair_changes(set(adapter._file_entries))
    assert changes is not None
    assert [change["path"] for change in changes] == [
        "app/models.py",
        "app/schemas.py",
        "app/crud.py",
        "app/main.py",
        "tests/test_crud.py",
    ]
    assert changes[-1]["dependencies"] == ["app/main.py"]


def test_flask_crud_repair_uses_four_file_contract_fallback(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Repair the existing python flask CRUD project. "
        "Appended skill context includes FastAPI examples."
    )
    adapter._file_entries = {
        "app.py": {},
        "models.py": {},
        "crud.py": {},
        "tests/test_crud.py": {},
    }

    changes = adapter._flask_crud_repair_changes(set(adapter._file_entries))

    assert adapter._is_flask_crud_repair() is True
    assert changes is not None
    assert adapter._is_fastapi_crud_repair() is False
    assert [change["path"] for change in changes] == [
        "models.py",
        "crud.py",
        "app.py",
        "tests/test_crud.py",
    ]
    for path in adapter._file_entries:
        content = adapter._contract_retry_fallback(path)
        assert content is not None
        compile(content, path, "exec")


def test_express_crud_repair_uses_four_file_contract_fallback(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Repair the existing typescript express CRUD project."
    adapter._file_entries = {
        "src/app.ts": {},
        "src/routes/todos.ts": {},
        "src/db.ts": {},
        "tests/todos.test.ts": {},
    }

    changes = adapter._express_crud_repair_changes(set(adapter._file_entries))

    assert adapter._is_express_crud_repair() is True
    assert changes is not None
    assert [change["path"] for change in changes] == [
        "src/db.ts",
        "src/routes/todos.ts",
        "src/app.ts",
        "tests/todos.test.ts",
    ]
    for path in adapter._file_entries:
        content = adapter._contract_retry_fallback(path)
        assert content is not None
        assert "@ts-nocheck" in content


def test_nestjs_crud_repair_uses_four_file_contract_fallback(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Repair the existing typescript nestjs CRUD project."
    adapter._file_entries = {
        "src/main.ts": {},
        "src/todos/todos.controller.ts": {},
        "src/todos/todos.service.ts": {},
        "test/todos.e2e-spec.ts": {},
    }

    changes = adapter._nestjs_crud_repair_changes(set(adapter._file_entries))

    assert adapter._is_nestjs_crud_repair() is True
    assert changes is not None
    assert [change["path"] for change in changes] == [
        "src/todos/todos.service.ts",
        "src/todos/todos.controller.ts",
        "src/main.ts",
        "test/todos.e2e-spec.ts",
    ]
    for path in adapter._file_entries:
        assert adapter._contract_retry_fallback(path) is not None


def test_go_crud_repair_uses_self_contained_module_fallback(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Repair the existing go net/http CRUD project."
    adapter._file_entries = {
        "go.mod": {},
        "go.sum": {},
        "cmd/server/main.go": {},
        "internal/todos/handler.go": {},
        "internal/todos/store.go": {},
        "internal/todos/handler_test.go": {},
    }

    changes = adapter._go_crud_repair_changes(set(adapter._file_entries))

    assert adapter._is_go_crud_repair() is True
    assert changes is not None
    assert [change["path"] for change in changes] == [
        "go.mod",
        "go.sum",
        "internal/todos/store.go",
        "internal/todos/handler.go",
        "cmd/server/main.go",
        "internal/todos/handler_test.go",
    ]
    for path in adapter._file_entries:
        assert adapter._contract_retry_fallback(path) is not None


def test_java_contract_rejects_implicit_todo_accessors_and_repository_mismatch(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    todo_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Todo.java",
        "package com.example; import lombok.Data; @Data public class Todo { "
        "private Long id; private String title; private boolean completed; }",
    )
    repository_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "package com.example; @Repository public class TodoRepository { "
        "JdbcTemplate jdbcTemplate; List<Todo> findAll(){return null;} "
        "Optional<Todo> findById(Long id){return null;} Todo save(Todo todo){todo.getCompleted();return todo;} "
        "Todo update(Todo todo){return todo;} boolean delete(Long id){return false;} "
        "String ddl=\"CREATE TABLE todos\"; }",
    )

    assert "Todo.java must declare explicit conventional getters and setters" in todo_diagnostics
    assert "TodoRepository must use explicit construction and Todo.isCompleted()" in repository_diagnostics


def test_java_contract_rejects_type_that_does_not_match_file_name(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Todo.java",
        "public interface TodoRepository {}\n",
    )

    assert any("must declare top-level type Todo" in item for item in diagnostics)
    assert any("public type must match file name Todo" in item for item in diagnostics)
    assert "Todo.java must declare the Todo entity as a class or record" in diagnostics


def test_java_contract_enforces_fixed_sqlite_crud_runtime_shape(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Application.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    application_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Application.java",
        "@SpringBootApplication\n@EnableAspectJAutoProxy\npublic class Application {}\n",
    )
    repository_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "public class TodoRepository { void delete(Long id) { jdbcTemplate.getConnection(); } }\n",
    )

    assert any("AspectJ" in item for item in application_diagnostics)
    assert any("CRUD signatures" in item for item in repository_diagnostics)
    assert "TodoRepository must initialize the SQLite todos table" in repository_diagnostics
    assert "TodoRepository must use supported JdbcTemplate operations" in repository_diagnostics


def test_java_contract_keeps_fixed_crud_rules_during_incremental_repair(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Repair the existing Java Spring Boot CRUD project with SQLite persistence."
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    model_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Todo.java",
        "import javax.persistence.*;\n@Entity public class Todo { Long id; String title; boolean completed; User user; }",
    )
    controller_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoController.java",
        "@RestController @RequestMapping(\"/api/v1/todos\") public class TodoController {\n"
        "TodoService service; @PostMapping void post() {} @GetMapping void list() {}\n"
        "@GetMapping(\"/{id}\") void get() {} @PutMapping(\"/{id}\") void put() {}\n"
        "@DeleteMapping(\"/{id}\") void delete() {} }",
    )
    repository_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "@Repository public interface TodoRepository extends JpaRepository<Todo, Long> {\n"
        "List<Todo> findAll(); Optional<Todo> findById(Long id); Todo save(Todo todo);\n"
        "Todo update(Todo todo); boolean delete(Long id); String ddl = \"CREATE TABLE todos\"; }",
    )

    assert "Todo.java must be a self-contained plain Java model" in model_diagnostics
    assert "Spring CRUD PUT handler must read the Todo from @RequestBody" in controller_diagnostics
    assert "Spring CRUD controller must use only the frozen Todo repository API" in controller_diagnostics
    assert "TodoRepository must be a concrete class" in repository_diagnostics
    assert "TodoRepository must use Spring JdbcTemplate" in repository_diagnostics
    assert "TodoRepository must use JDBC instead of JPA" in repository_diagnostics


def test_java_contract_rejects_controller_owned_persistence_and_model(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoController.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoController.java",
        "@RestController @RequestMapping(\"/api/v1/todos\") public class TodoController {\n"
        "JdbcTemplate jdbcTemplate; @PostMapping void post() {} @GetMapping void list() {}\n"
        "@GetMapping(\"/{id}\") void get() {} @PutMapping(\"/{id}\") void put(@RequestBody Todo todo) {}\n"
        "@DeleteMapping(\"/{id}\") void delete() {} private class Todo {} }",
    )

    assert (
        "Spring CRUD controller must delegate persistence to TodoRepository and use the shared Todo model"
        in diagnostics
    )


def test_java_contract_rejects_repository_jdbc_field_injection(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = (
        "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."
    )
    adapter._file_entries = {
        "src/main/java/com/example/Todo.java": {},
        "src/main/java/com/example/TodoRepository.java": {},
    }

    diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/TodoRepository.java",
        "@Repository public class TodoRepository { @Autowired private JdbcTemplate jdbcTemplate; "
        "TodoRepository(JdbcTemplate jdbcTemplate) {} List<Todo> findAll(){return null;} "
        "Optional<Todo> findById(Long id){return null;} Todo save(Todo todo){return todo;} "
        "Todo update(Todo todo){return todo;} boolean delete(Long id){return false;} "
        "String ddl=\"CREATE TABLE todos\"; }",
    )

    assert "TodoRepository must use constructor injection for JdbcTemplate" in diagnostics


def test_java_contract_rejects_unsupported_sqlite_bootstrap_and_starters(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    adapter._requirement = "Create a Java Spring Boot CRUD API with SQLite persistence at /api/v1/todos."

    application_diagnostics = adapter._validate_java_contract(
        "src/main/java/com/example/Application.java",
        "@SpringBootApplication public class Application { DataSourceInitializer initializer; }",
    )
    pom_diagnostics = adapter._validate_java_contract(
        "pom.xml",
        """<project xmlns="http://maven.apache.org/POM/4.0.0"><dependencies>
        <dependency><artifactId>sqlite-jdbc</artifactId></dependency>
        <dependency><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
        </dependencies></project>""",
    )

    assert "Spring CRUD Application.java uses an unsupported SQLite initializer" in application_diagnostics
    assert "SQLite Spring CRUD requires spring-boot-starter-jdbc" in pom_diagnostics
    assert any("spring-boot-starter-data-jpa" in item for item in pom_diagnostics)


@pytest.mark.asyncio
async def test_traditional_adapter_creates_plan_and_generates_file(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build a python app",
        task_id="task-1",
        session_id="session-1",
        metadata={},
    )

    plan = await adapter.create_plan(request)
    generated = await adapter.generate_file(
        type("Context", (), {
            "file_path": "app.py",
            "upstream_contents": {},
        })()
    )

    assert [item.path for item in plan.files] == ["app.py", "config.py"]
    assert generated.content == "# app.py\n"
    assert generated.model_name == "test-model"
    assert adapter.project_plan is not None
    assert adapter.project_plan.language == "python"


@pytest.mark.asyncio
async def test_traditional_adapter_exposes_all_completed_files_to_validation(tmp_path):
    agent = _Agent(tmp_path)
    generated_contexts = {}

    async def generate(file_info, project_context, total_files, generated_contents):
        generated_contexts[file_info["path"]] = dict(generated_contents)
        return {"success": True, "content": f"# {file_info['path']}\n", "model": "test-model"}

    agent._generate_single_file = generate
    adapter = TraditionalAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a python app",
        task_id="task-completed-context",
        session_id="session-completed-context",
        metadata={},
    ))

    await adapter.generate_file(type("Context", (), {
        "file_path": "app.py",
        "upstream_contents": {},
    })())
    await adapter.generate_file(type("Context", (), {
        "file_path": "config.py",
        "upstream_contents": {},
    })())

    assert generated_contexts["config.py"] == {"app.py": "# app.py\n"}


@pytest.mark.asyncio
async def test_traditional_adapter_replaces_stale_architecture_context(tmp_path):
    agent = _Agent(tmp_path)
    captured_context = {}

    async def generate(file_info, project_context, total_files, generated_contents):
        captured_context.update(project_context)
        return {"success": True, "content": "# generated\n", "model": "test-model"}

    agent._generate_single_file = generate
    adapter = TraditionalAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a python app",
        task_id="task-projected-architecture",
        session_id="session-projected-architecture",
        metadata={"architecture": {"file_plan": [{"path": "app.py", "file_type": "backend"}]}},
    ))
    await adapter.generate_file(type("Context", (), {
        "file_path": "app.py",
        "upstream_contents": {},
    })())

    file_entries = {
        item["path"]: item for item in captured_context["architecture"]["file_plan"]
    }
    assert captured_context["architecture"] == adapter._architecture
    assert file_entries["app.py"]["file_type"] != "backend"


@pytest.mark.asyncio
async def test_traditional_adapter_preserves_architect_strict_file_set(tmp_path):
    agent = _Agent(tmp_path)

    async def design_strict_architecture(requirement, complexity, callback=None):
        return {
            "language": "python",
            "strict_file_paths": ["app.py", "config.py"],
            "file_plan": [
                {"path": "app.py", "description": "application entry point"},
                {"path": "config.py", "description": "configuration", "depends_on": ["app.py"]},
            ],
        }

    agent.architect.design_architecture = design_strict_architecture
    adapter = TraditionalAdapter(agent)

    plan = await adapter.create_plan(GenerationRequest(
        requirement="build exactly app.py and config.py",
        task_id="task-strict",
        session_id="session-strict",
        metadata={},
    ))

    assert plan.policy.value == "strict"
    assert plan.requested_paths == ("app.py", "config.py")
    assert set(agent.dependency_graph_obj.nodes) == {"app.py", "config.py"}


@pytest.mark.asyncio
@pytest.mark.parametrize("file_count", [4, 5, 6, 7])
async def test_traditional_adapter_projects_import_dag_for_any_file_count(
    tmp_path, file_count
):
    agent = _Agent(tmp_path)
    paths = [f"layer_{index}.py" for index in range(file_count)]

    async def design_architecture(requirement, complexity, callback=None):
        return {
            "language": "python",
            "strict_file_paths": paths,
            "file_plan": [
                {
                    "path": path,
                    "description": f"layer {index}",
                    "imports": [] if index == 0 else [f"layer_{index - 1}"],
                }
                for index, path in enumerate(paths)
            ],
        }

    agent.architect.design_architecture = design_architecture
    plan = await TraditionalAdapter(agent).create_plan(GenerationRequest(
        requirement=f"build exactly {file_count} files",
        task_id=f"task-{file_count}",
        session_id=f"session-{file_count}",
        metadata={},
    ))

    dependencies = {item.path: item.dependencies for item in plan.files}
    assert dependencies[paths[0]] == ()
    for index in range(1, file_count):
        assert paths[index - 1] in dependencies[paths[index]]


@pytest.mark.asyncio
async def test_traditional_adapter_resolves_renamed_imports_within_strict_scope(tmp_path):
    agent = _Agent(tmp_path)

    async def design_architecture(requirement, complexity, callback=None):
        return {
            "language": "python",
            "strict_file_paths": ["domain.py", "storage.py", "web.py", "tests/test_web.py"],
            "file_plan": [
                {"path": "domain.py", "description": "domain models"},
                {"path": "storage.py", "description": "storage", "imports": ["domain"]},
                {"path": "web.py", "description": "web entry", "imports": ["storage", "domain"]},
                {
                    "path": "tests/test_web.py",
                    "description": "web tests",
                    "imports": ["web"],
                },
            ],
        }

    agent.architect.design_architecture = design_architecture
    adapter = TraditionalAdapter(agent)
    plan = await adapter.create_plan(GenerationRequest(
        requirement="build exactly the renamed files",
        task_id="task-renamed",
        session_id="session-renamed",
        metadata={},
    ))

    dependencies = {item.path: set(item.dependencies) for item in plan.files}
    assert dependencies["storage.py"] == {"domain.py"}
    assert dependencies["web.py"].issuperset({"domain.py", "storage.py"})
    assert "web.py" in dependencies["tests/test_web.py"]
    assert {
        dependency
        for item in plan.files
        for dependency in item.dependencies
    }.issubset(set(plan.requested_paths))
    assert {
        item.path: item.dependencies for item in adapter.project_plan.files
    } == {
        item.path: item.dependencies for item in plan.files
    }


@pytest.mark.asyncio
async def test_traditional_adapter_projects_profile_components_into_extensible_plan(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build a game",
        task_id="task-2",
        session_id="session-2",
        metadata={"profile_context": {"capability_policy": {"component_file_plan": [
            {"path": "game/rules.py", "component": "rules"},
            {"path": "game/renderer.py", "component": "renderer"},
        ]}}},
    )

    plan = await adapter.create_plan(request)

    assert "game/rules.py" in {item.path for item in plan.files}
    renderer = next(item for item in adapter.project_plan.files if item.path == "game/renderer.py")
    assert renderer.dependencies == ("game/rules.py",)


def test_engine_selection_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv("AGENT_ORCHESTRATION_ENGINE", raising=False)
    assert select_engine() == LEGACY_ENGINE
    assert select_engine(CORE_ENGINE) == CORE_ENGINE
    assert engine_metadata(CORE_ENGINE)["engine_version"] == "core-v1"


@pytest.mark.asyncio
async def test_legacy_workflow_checkpoint_contains_selected_engine(monkeypatch):
    monkeypatch.setenv("AGENT_ORCHESTRATION_ENGINE", "core")
    workflow = build_legacy_workflow("test", "/test", lambda state: {"success": True})

    state = await run_workflow(
        workflow,
        session_id="session-adapter-test",
        task_id="task-adapter-test",
    )

    assert state.metadata["engine"] == CORE_ENGINE
    assert state.metadata["engine_version"] == "core-v1"
    assert state.metadata["engine_route"] == "experimental"


@pytest.mark.asyncio
async def test_traditional_adapter_requires_plan(tmp_path):
    adapter = TraditionalAdapter(_Agent(tmp_path))
    context = type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()

    with pytest.raises(RuntimeError, match="create_plan"):
        await adapter.generate_file(context)


@pytest.mark.asyncio
async def test_spec_first_adapter_freezes_supplied_specification_plan(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build from a specification",
        task_id="task-spec",
        session_id="session-spec",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "models.py", "description": "models"},
                    {"path": "app.py", "description": "entry", "depends_on": ["models.py"]},
                ],
            }
        },
    )

    plan = await adapter.create_plan(request)
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "models.py", "upstream_contents": {}})()
    )

    assert plan.policy.value == "strict"
    assert set(plan.requested_paths) == {"app.py", "models.py"}
    assert adapter.project_plan is not None
    assert adapter.project_plan.policy == "strict"
    assert generated.content == "# models.py\n"


@pytest.mark.asyncio
async def test_spec_first_adapter_projects_dependency_graph_into_plan(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="build from a specification",
        task_id="task-spec-dependencies",
        session_id="session-spec-dependencies",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "models.py", "description": "models", "imports": []},
                    {
                        "path": "app.py",
                        "description": "entry",
                        "imports": ["models"],
                    },
                ],
            }
        },
    )

    plan = await adapter.create_plan(request)

    app_file = next(item for item in plan.files if item.path == "app.py")
    assert app_file.dependencies == ("models.py",)
    assert (tmp_path / ".dep_graph.json").is_file()


@pytest.mark.asyncio
async def test_planned_adapter_leaves_persistence_to_core_committer(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build an app",
        task_id="task-core-write",
        session_id="session-core-write",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            }
        },
    ))

    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()
    )

    assert generated.content == "# app.py\n"
    assert agent.persist_requested is False
    assert agent.generation_contract["frozen_file_set"] == ["app.py"]
    assert agent.generation_contract["target_file"] == "app.py"
    assert agent.project_context["retrieval_status"]["enabled"] is True
    assert agent.project_context["retrieval_status"]["source_count"] == 3
    assert not (tmp_path / "app.py").exists()


@pytest.mark.asyncio
async def test_planned_adapter_rejects_local_import_outside_frozen_set(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build an app",
        task_id="task-core-import-contract",
        session_id="session-core-import-contract",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            }
        },
    ))

    agent._generate_file_with_model = lambda *args, **kwargs: None

    async def generate_invalid(*args, **kwargs):
        return "from app.database import get_session\n"

    agent._generate_file_with_model = generate_invalid
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "app.py", "upstream_contents": {}})()
    )

    assert generated.validation_passed is False
    assert "outside frozen file set" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_planned_adapter_rejects_orm_schema_inheritance(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a FastAPI CRUD app",
        task_id="task-schema-contract",
        session_id="session-schema-contract",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "models.py", "description": "SQLAlchemy models"},
                    {"path": "schemas.py", "description": "Pydantic schemas", "depends_on": ["models.py"]},
                ],
            }
        },
    ))

    async def generate_model(*args, **kwargs):
        return "class Base: pass\nclass Todo(Base): pass\n"

    async def generate_schema(*args, **kwargs):
        return "from pydantic import BaseModel\nfrom app.models import Todo\nclass TodoResponse(Todo): pass\n"

    agent._generate_file_with_model = generate_model
    await adapter.generate_file(type("Context", (), {"file_path": "models.py", "upstream_contents": {}})())
    agent._generate_file_with_model = generate_schema
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "schemas.py", "upstream_contents": {"models.py": "class Base: pass\nclass Todo(Base): pass\n"}})()
    )

    assert generated.validation_passed is False
    assert "must not inherit SQLAlchemy ORM" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_planned_adapter_enforces_fastapi_entrypoint_contract(tmp_path):
    agent = _CoreFileAgent(tmp_path)
    adapter = SpecFirstAdapter(agent)
    await adapter.create_plan(GenerationRequest(
        requirement="build a FastAPI app",
        task_id="task-fastapi-entrypoint",
        session_id="session-fastapi-entrypoint",
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "main.py", "description": "FastAPI entrypoint"}],
            }
        },
    ))

    async def generate_main(*args, **kwargs):
        return "from fastapi import APIRouter\nrouter = APIRouter()\n"

    agent._generate_file_with_model = generate_main
    generated = await adapter.generate_file(
        type("Context", (), {"file_path": "main.py", "upstream_contents": {}})()
    )

    assert generated.validation_passed is False
    assert "must instantiate FastAPI" in generated.diagnostics[0]


@pytest.mark.asyncio
async def test_incremental_adapter_freezes_affected_files_and_preserves_existing_files(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "unchanged.py").write_text("UNCHANGED = True\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="change existing behavior",
        task_id="task-incremental",
        session_id="session-incremental",
        metadata={
            "dependency_graph": object(),
            "change_plan": [
                {
                    "path": "existing.py",
                    "action": "modify",
                    "description": "update value",
                    "depends_on": ["unchanged.py"],
                }
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.policy.value == "strict"
    assert plan.requested_paths == ("existing.py",)
    assert plan.files[0].dependencies == ()
    assert adapter.preserved_paths == ("unchanged.py",)
    assert adapter._file_entries["existing.py"]["original_content"] == "VALUE = 1\n"


@pytest.mark.asyncio
async def test_incremental_adapter_normalizes_model_priority(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="change existing behavior",
        task_id="task-incremental-priority",
        session_id="session-incremental-priority",
        metadata={
            "dependency_graph": object(),
            "change_plan": [{
                "path": "existing.py",
                "action": "modify",
                "description": "update value",
                "priority": 6,
            }],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.files[0].priority == 5


@pytest.mark.asyncio
async def test_incremental_adapter_filters_changes_outside_allowed_files(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="repair existing behavior",
        task_id="task-incremental-allowed-files",
        session_id="session-incremental-allowed-files",
        metadata={
            "dependency_graph": object(),
            "allowed_files": ["existing.py"],
            "change_plan": [
                {"path": "existing.py", "action": "modify", "description": "repair value"},
                {"path": "invented.py", "action": "add", "description": "scope drift"},
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.requested_paths == ("existing.py",)


@pytest.mark.asyncio
async def test_incremental_adapter_rebuilds_missing_dependency_graph(tmp_path):
    (tmp_path / "existing.py").write_text("from unchanged import VALUE\n", encoding="utf-8")
    (tmp_path / "unchanged.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="change existing Python behavior",
        task_id="task-incremental-rebuild",
        session_id="session-incremental-rebuild",
        metadata={
            "change_plan": [
                {
                    "path": "existing.py",
                    "action": "modify",
                    "description": "update behavior",
                }
            ],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.requested_paths == ("existing.py",)
    assert adapter._dependency_graph is not None
    assert set(adapter._dependency_graph.nodes) == {"existing.py", "unchanged.py"}
    assert (tmp_path / ".dep_graph.json").is_file()
    assert adapter._file_entries["existing.py"]["original_content"] == "from unchanged import VALUE\n"
    assert adapter.preserved_paths == ("unchanged.py",)


@pytest.mark.asyncio
async def test_incremental_adapter_supports_delete_only_plans(tmp_path):
    (tmp_path / "obsolete.py").write_text("legacy\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="remove obsolete file",
        task_id="task-delete",
        session_id="session-delete",
        metadata={
            "change_plan": [{"path": "obsolete.py", "action": "delete"}],
        },
    )

    plan = await adapter.create_plan(request)

    assert plan.files == ()
    assert adapter.change_plan is not None


@pytest.mark.asyncio
async def test_core_executes_delete_only_change_transaction(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    output_dir.mkdir()
    obsolete = output_dir / "obsolete.py"
    obsolete.write_text("legacy\n", encoding="utf-8")
    adapter = IncrementalAdapter(_Agent(output_dir))

    result = await execute_core_generation(
        adapter,
        requirement="remove obsolete file",
        task_id="task-delete-only",
        session_id="session-delete-only",
        mode="incremental",
        output_dir=output_dir,
        metadata={
            "change_plan": [{"path": "obsolete.py", "action": "delete"}],
        },
    )

    assert result["success"], result
    assert not obsolete.exists()


@pytest.mark.asyncio
async def test_core_runtime_projects_spec_first_result_to_existing_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    adapter = SpecFirstAdapter(_Agent(output_dir))

    result = await execute_core_generation(
        adapter,
        requirement="build from a specification",
        task_id="task-runtime",
        session_id="session-runtime",
        mode="spec_first",
        output_dir=output_dir,
        metadata={
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            }
        },
    )

    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert result["validation"] == {"runnable": True, "status": "completed"}
    assert (output_dir / "app.py").read_text(encoding="utf-8") == "# app.py\n"


@pytest.mark.asyncio
async def test_spec_first_adapter_freezes_plan_to_allowed_files(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="generate an application",
        task_id="task-allowed",
        session_id="session-allowed",
        metadata={
            "allowed_files": ["app.py"],
            "specification": {
                "language": "python",
                "file_plan": [
                    {"path": "app.py", "description": "entry"},
                    {"path": "README.md", "description": "documentation"},
                ],
            },
        },
    )

    plan = await adapter.create_plan(request)

    assert [item.path for item in plan.files] == ["app.py"]


@pytest.mark.asyncio
async def test_spec_first_allowed_file_plan_preserves_business_requirement(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    requirement = "Build a CLI task tracker with TaskList.add and TaskList.complete"
    request = GenerationRequest(
        requirement=requirement,
        task_id="task-business-context",
        session_id="session-business-context",
        metadata={"allowed_files": ["main.py"]},
    )

    plan = await adapter.create_plan(request)

    assert requirement in adapter._file_entries["main.py"]["description"]


@pytest.mark.asyncio
async def test_spec_first_adapter_adds_missing_allowed_files(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    request = GenerationRequest(
        requirement="generate an application",
        task_id="task-missing-allowed",
        session_id="session-missing-allowed",
        metadata={
            "allowed_files": ["app.py", "game/rules.py"],
            "specification": {
                "language": "python",
                "file_plan": [{"path": "app.py", "description": "entry"}],
            },
        },
    )

    plan = await adapter.create_plan(request)

    assert [item.path for item in plan.files] == ["app.py", "game/rules.py"]


def test_pygame_snake_fallback_covers_frozen_contract(tmp_path):
    adapter = SpecFirstAdapter(_Agent(tmp_path))
    paths = ("main.py", "game/rules.py", "game/renderer.py", "game/input_loop.py", "tests/test_game.py")
    adapter._requirement = "Generate a Pygame Snake game"
    adapter._file_entries = {path: {"path": path} for path in paths}

    contents = {path: adapter._pygame_snake_retry_fallback(path) for path in paths}

    assert all(contents.values())
    for path, content in contents.items():
        compile(content, path, "exec")
    assert "pygame.image.save" in contents["main.py"]


def test_change_plan_tracks_dynamic_incremental_files(tmp_path):
    from app.agent.change_plan import ChangeAction, ChangePlan
    from app.agent.project_snapshot import ProjectSnapshot

    (tmp_path / "main.py").write_text("print('old')\n", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [
        {"path": "main.py", "action": "modify", "reason": "pause support"},
        {"path": "game/leaderboard.py", "action": "add", "reason": "score history"},
        {"path": "ui.py", "action": "rename", "previous_path": "main.py"},
    ])

    assert plan.base_revision == "r1"
    assert plan.affected_files == ("game/leaderboard.py", "main.py", "ui.py")
    assert plan.changes[1].action is ChangeAction.ADD

    (tmp_path / "unrelated.py").write_text("changed\n", encoding="utf-8")
    current = ProjectSnapshot.scan(tmp_path, revision="r2")
    assert plan.verify_untouched(snapshot, current) == ("unrelated.py",)


def test_incremental_file_transaction_rolls_back_rename(tmp_path):
    from app.agent.change_plan import ChangePlan
    from app.agent.orchestration.file_transaction import IncrementalFileTransaction
    from app.agent.project_snapshot import ProjectSnapshot

    old = tmp_path / "old.py"
    old.write_text("content", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [{
        "path": "new.py", "action": "rename", "previous_path": "old.py",
    }])
    transaction = IncrementalFileTransaction(tmp_path, plan, transaction_id="test")
    transaction.stage()
    assert not old.exists()
    transaction.rollback()
    assert old.read_text(encoding="utf-8") == "content"


def test_incremental_file_transaction_commits_delete(tmp_path):
    from app.agent.change_plan import ChangePlan
    from app.agent.orchestration.file_transaction import IncrementalFileTransaction
    from app.agent.project_snapshot import ProjectSnapshot

    obsolete = tmp_path / "obsolete.py"
    obsolete.write_text("legacy", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")
    plan = ChangePlan.build(snapshot, [{"path": "obsolete.py", "action": "delete"}])
    transaction = IncrementalFileTransaction(tmp_path, plan, transaction_id="delete-test")
    transaction.stage()
    transaction.commit()
    assert not obsolete.exists()


@pytest.mark.asyncio
async def test_core_runtime_preserves_unaffected_incremental_artifacts(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    monkeypatch.setenv("AGENT_CORE_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    output_dir = tmp_path / "project"
    output_dir.mkdir()
    (output_dir / "changed.py").write_text("VALUE = 1\n", encoding="utf-8")
    (output_dir / "unchanged.py").write_text("UNCHANGED = True\n", encoding="utf-8")
    graph = type("Graph", (), {"adjacency": {"changed.py": {"unchanged.py"}}})()
    monkeypatch.setattr(DependencyGraph, "load", lambda *args, **kwargs: graph)

    result = await execute_core_generation(
        IncrementalAdapter(_CoreFileAgent(output_dir)),
        requirement="change existing behavior",
        task_id="task-incremental-runtime",
        session_id="session-incremental-runtime",
        mode="incremental",
        output_dir=output_dir,
        metadata={
            "change_plan": [
                {"path": "changed.py", "action": "modify", "description": "update value"}
            ]
        },
    )

    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert (output_dir / "changed.py").read_text(encoding="utf-8") == "# changed.py\n"
    assert (output_dir / "unchanged.py").read_text(encoding="utf-8") == "UNCHANGED = True\n"
