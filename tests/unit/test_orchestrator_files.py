import types

import pytest

from app.agent.orchestrator_files import FilesMixin
from app.agent.orchestrator_files import _fix_absolute_imports
from app.agent.orchestrator_files import _validate_python_project_imports
from app.agent.orchestrator_files import _validate_python_implementation
from app.agent.orchestrator_files import _structured_import_diagnostics
from app.agent.architect import Architect
from app.agent.dependency_graph import DependencyGraph
from app.agent.backend_engineer import BackendEngineer
from app.agent.shared_context import SharedContext


class _FilesTestOrchestrator(FilesMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.feedback_learner = None
        self.dependency_graph_obj = None
        self.enable_validation = False
        self.enable_review = False
        self.require_approval = False
        self.api_contract_checker = None
        self.error_recovery = None
        self.enable_error_recovery = False
        self.callback = None
        self.cancel_event = None
        self.api_key_token = None
        self._generated_contents = {}
        self.dep_contexts = {}

    def _select_engineer(self, _file_path):
        async def generate_file(file_path, _description, _project_context, _spec_context, dep_context, **_kwargs):
            self.dep_contexts[file_path] = dep_context
            module_name = file_path.rsplit("/", 1)[-1].removesuffix(".py")
            return f"def {module_name}_value():\n    return 'persisted'\n"

        return types.SimpleNamespace(
            name="测试工程师",
            clear_edits=lambda: None,
            generate_file=generate_file,
        )

    def _select_model_for_file(self, _file_path):
        return "test-model"

    def _report_progress(self, *_args, **_kwargs):
        return None


    def _report_thinking(self, *_args, **_kwargs):
        return None

    def _report_file_event(self, *_args, **_kwargs):
        return None

    def _is_frontend_file(self, _file_path):
        return False


def test_structured_import_diagnostics_preserves_actionable_fields():
    diagnostics = _structured_import_diagnostics([
        "database.py 未导出符号 SessionLocal，请使用其真实接口",
        "名称 datetime 在模块全局作用域中未定义或导入",
        "调用 update_todo 缺少必需参数 todo_update",
    ])

    assert diagnostics[0]["type"] == "missing_export"
    assert diagnostics[0]["dependency_file"] == "database.py"
    assert diagnostics[0]["symbol"] == "SessionLocal"
    assert diagnostics[1]["type"] == "undefined_global"
    assert diagnostics[1]["symbol"] == "datetime"
    assert diagnostics[2]["type"] == "signature_mismatch"


def test_python_implementation_gate_rejects_import_only_placeholder():
    errors = _validate_python_implementation(
        "from sqlalchemy import Column\n# model implementation should be here\n",
        "models.py",
    )

    assert errors == ["Python 文件仅包含导入或说明文本，缺少可执行实现"]


def test_python_implementation_gate_accepts_real_definition():
    errors = _validate_python_implementation(
        "from sqlalchemy import Column\n\nclass Todo:\n    pass\n",
        "models.py",
    )

    assert errors == []


@pytest.mark.asyncio
async def test_single_file_generation_persists_without_review_or_validation(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )

    orchestrator = _FilesTestOrchestrator(tmp_path)
    result = await orchestrator._generate_single_file(
        {"path": "src/main.py", "description": "入口"},
        {"architecture": {"language": "python"}},
        1,
    )

    output_file = tmp_path / "src/main.py"
    assert result["success"] is True
    assert output_file.read_text(encoding="utf-8") == "def main_value():\n    return 'persisted'\n"
    assert output_file.exists()


@pytest.mark.asyncio
async def test_single_file_generation_records_verified_artifact_event(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    context = SharedContext("entry", tmp_path)
    context.register_file("main.py", "source")
    orchestrator.shared_context = context
    orchestrator.artifact_committer = ArtifactCommitter(
        tmp_path, context, task_id="task-1"
    )
    orchestrator.artifact_completion_events = []

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert [event.path for event in orchestrator.artifact_completion_events] == ["main.py"]


@pytest.mark.asyncio
async def test_dependency_layers_include_generated_upstream_context(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    graph = DependencyGraph()
    graph.add_file("database.py")
    graph.add_file("crud.py")
    graph.add_dependency("crud.py", "database.py")
    orchestrator.dependency_graph_obj = graph
    file_plan = [
        {"path": "database.py", "description": "database"},
        {"path": "crud.py", "description": "crud"},
    ]

    await orchestrator._generate_files_by_dep_layers(
        file_plan,
        {"architecture": {"language": "python"}},
        2,
        graph,
    )

    assert "## 依赖文件: database.py" in orchestrator.dep_contexts["crud.py"]
    assert "def database_value" in orchestrator.dep_contexts["crud.py"]


@pytest.mark.asyncio
async def test_single_file_generation_retries_invalid_cross_file_import(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    responses = iter([
        "from database import missing_symbol\n",
        "from database import get_db\n\ndef read_database():\n    return next(get_db())\n",
    ])
    calls = []

    async def generate_file(*args, **_kwargs):
        calls.append(args[1])
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate_file,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    graph = DependencyGraph()
    graph.add_file("database.py")
    graph.add_file("main.py")
    graph.add_dependency("main.py", "database.py")
    orchestrator.dependency_graph_obj = graph
    generated = {"database.py": "def get_db():\n    yield object()\n"}

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        2,
        generated,
    )

    assert result["success"] is True
    assert len(calls) == 2
    assert "未导出符号 missing_symbol" in calls[1]
    assert "只能使用已生成依赖上下文中真实存在的模块和导出" in calls[1]
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == (
        "from database import get_db\n\ndef read_database():\n    return next(get_db())\n"
    )


@pytest.mark.asyncio
async def test_single_file_generation_gives_actionable_undefined_name_feedback(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    responses = iter([
        "def created_at():\n    return func.now()\n",
        "from sqlalchemy import func\n\ndef created_at():\n    return func.now()\n",
    ])
    calls = []

    async def generate_file(*args, **_kwargs):
        calls.append(args[1])
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate_file,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    result = await orchestrator._generate_single_file(
        {"path": "models.py", "description": "models"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert len(calls) == 2
    assert "必须在模块顶层添加定义 X 的真实 import" in calls[1]
    assert "ORM 字段参数" in calls[1]


def test_top_level_relative_import_is_normalized_for_direct_execution():
    content = (
        "from .database import get_db\n"
        "from . import crud, schemas\n"
        "from .missing import value\n"
    )

    fixed = _fix_absolute_imports(
        content,
        "main.py",
        ["main.py", "database.py", "crud.py", "schemas.py"],
    )

    assert fixed == (
        "from database import get_db\n"
        "import crud, schemas\n"
        "from .missing import value\n"
    )


def test_top_level_prefixed_import_is_normalized_for_flat_file_scope():
    content = "from src.main import app\nfrom package.external import value\n"

    fixed = _fix_absolute_imports(content, "test_main.py", ["test_main.py", "main.py"])

    assert fixed == "from main import app\nfrom package.external import value\n"


def test_backend_prompt_scope_uses_top_level_imports_for_flat_files():
    constraints = BackendEngineer._build_file_scope_constraints(
        "main.py",
        {
            "file_plan": [
                {"path": "main.py"},
                {"path": "models.py"},
                {"path": "crud.py"},
            ]
        },
    )

    assert "main.py, models.py, crud.py" in constraints
    assert "项目内模块只能从上述文件集合导入" in constraints
    assert "同目录项目文件使用顶层绝对导入" in constraints


def test_backend_runtime_constraints_use_supported_fastapi_test_client_api():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "test_main.py",
        "test",
        "python",
        {"framework": "FastAPI"},
    )

    assert "fastapi.testclient.TestClient" in constraints
    assert "httpx.ASGITransport(app=app)" in constraints
    assert "禁止从 httpx 导入 ASGIApp" in constraints
    assert "同步/异步风格必须一致" in constraints
    assert "同名符号只能从一个模块导入" in constraints


def test_backend_runtime_constraints_define_module_level_crud_contract():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "crud.py",
        "repository",
        "python",
        {"framework": "FastAPI"},
    )

    assert "必须直接导出模块级函数 create_todo、get_todos、get_todo、update_todo、delete_todo" in constraints
    assert "禁止只定义 CRUDTodo 类或仅提供静态方法" in constraints


def test_backend_runtime_constraints_require_thread_safe_sqlite_access():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "database.py",
        "database",
        "python",
        {"framework": "FastAPI"},
    )

    assert "SQLite 连接必须按请求/调用创建并关闭" in constraints
    assert "check_same_thread=False" in constraints
    assert "整个项目必须统一选择 SQLAlchemy 或原生 sqlite3" in constraints


def test_backend_runtime_constraints_require_models_to_share_database_base():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "models.py",
        "model",
        "python",
        {"framework": "FastAPI"},
    )

    assert "from database import Base" in constraints
    assert "禁止在 models.py 中再次调用 declarative_base()" in constraints


def test_backend_runtime_constraints_are_empty_for_non_python_projects():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "main.go",
        "entry",
        "go",
        {"framework": "Gin"},
    )

    assert constraints == ""


def test_backend_dependency_import_constraints_keep_base_layer_independent():
    constraints = BackendEngineer._build_dependency_import_constraints("")

    assert "没有已生成的上游依赖" in constraints
    assert "禁止导入任何其他项目文件" in constraints


def test_backend_dependency_import_constraints_list_generated_upstream_files():
    constraints = BackendEngineer._build_dependency_import_constraints(
        "## 依赖文件: database.py\n```python\nengine = object()\n```\n"
        "## 依赖文件: models.py\n```python\nclass Todo: ...\n```"
    )

    assert "database.py, models.py" in constraints
    assert "禁止导入白名单之外的项目文件" in constraints


def test_python_import_gate_rejects_future_project_module():
    errors = _validate_python_project_imports(
        "from models import Todo\n",
        "database.py",
        {},
        ["database.py", "models.py"],
    )

    assert errors == ["项目模块 models.py 尚未生成，当前拓扑层禁止导入"]


def test_python_import_gate_rejects_missing_generated_symbol():
    errors = _validate_python_project_imports(
        "from database import get_db\n",
        "main.py",
        {"database.py": "def get_db_connection():\n    yield object()\n"},
        ["main.py", "database.py"],
    )

    assert errors == ["database.py 未导出符号 get_db，请使用其真实接口"]


def test_python_import_gate_accepts_real_generated_symbol():
    errors = _validate_python_project_imports(
        "from database import get_db_connection\n",
        "main.py",
        {"database.py": "def get_db_connection():\n    yield object()\n"},
        ["main.py", "database.py"],
    )

    assert errors == []


def test_python_import_gate_rejects_mismatched_project_function_signature():
    errors = _validate_python_project_imports(
        "from database import init_database\n\ndef setup():\n    init_database('test.db')\n",
        "test_main.py",
        {"database.py": "def init_database():\n    return None\n"},
        ["test_main.py", "database.py"],
    )

    assert errors == [
        "调用 init_database 传入 1 个位置参数，但 database.py 中定义最多接受 0 个"
    ]


def test_python_import_gate_accepts_matching_project_function_signature():
    errors = _validate_python_project_imports(
        "from database import init_database\n\ndef setup():\n    init_database('test.db')\n",
        "test_main.py",
        {"database.py": "def init_database(db_path):\n    return db_path\n"},
        ["test_main.py", "database.py"],
    )

    assert errors == []


def test_python_import_gate_rejects_duplicate_sqlalchemy_base():
    errors = _validate_python_project_imports(
        "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n",
        "models.py",
        {"database.py": "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"},
        ["models.py", "database.py"],
    )

    assert errors == [
        "database.py 已导出 SQLAlchemy Base，models.py 必须导入复用，禁止再次调用 declarative_base()"
    ]


def test_python_import_gate_rejects_sqlite_database_with_sqlalchemy_models():
    errors = _validate_python_project_imports(
        "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n",
        "models.py",
        {"database.py": "import sqlite3\ndef get_db():\n    return sqlite3.connect('todos.db')\n"},
        ["models.py", "database.py"],
    )

    assert errors == ["database.py 使用原生 sqlite3 时，models.py 禁止混用 SQLAlchemy ORM"]


def test_python_import_gate_rejects_sqlalchemy_database_with_sqlite_models():
    errors = _validate_python_project_imports(
        "import sqlite3\n\ndef load():\n    return sqlite3.connect('todos.db')\n",
        "models.py",
        {"database.py": "from sqlalchemy import create_engine\nengine = create_engine('sqlite:///todos.db')\n"},
        ["models.py", "database.py"],
    )

    assert errors == ["database.py 使用 SQLAlchemy 时，models.py 禁止混用原生 sqlite3"]


def test_python_import_gate_rejects_unavailable_undeclared_module():
    errors = _validate_python_project_imports(
        "import project_config_that_does_not_exist\n",
        "database.py",
        {},
        ["database.py", "models.py"],
    )

    assert errors == [
        "模块 project_config_that_does_not_exist 不在项目文件集合中且当前运行时不可用"
    ]


def test_python_import_gate_rejects_undefined_global_used_in_function():
    errors = _validate_python_project_imports(
        "def connect():\n    return sqlite3.connect('todos.db')\n",
        "database.py",
        {},
        ["database.py"],
    )

    assert errors == ["名称 sqlite3 在模块全局作用域中未定义或导入"]


def test_explicit_file_scope_prevents_completeness_expansion():
    requirement = "创建待办 API，只需要 main.py 和 models.py 两个文件。"
    assert Architect._extract_strict_file_paths(requirement) == {"main.py", "models.py"}

    architect = object.__new__(Architect)
    architecture = {
        "language": "python",
        "file_plan": [
            {"path": "main.py", "imports": []},
            {"path": "models.py", "imports": []},
        ],
    }
    result = architect._ensure_file_plan_completeness(
        architecture,
        target_language="python",
        strict_paths={"main.py", "models.py"},
    )

    assert [item["path"] for item in result["file_plan"]] == ["main.py", "models.py"]


def test_explicit_file_scope_normalizes_prefixed_paths_and_fills_omissions():
    architect = object.__new__(Architect)
    architecture = {
        "language": "python",
        "file_plan": [
            {"path": "app/main.py", "description": "entry", "imports": []},
            {"path": "app/models.py", "description": "models", "imports": []},
            {"path": "requirements.txt", "description": "dependencies", "imports": []},
        ],
    }

    result = architect._ensure_file_plan_completeness(
        architecture,
        target_language="python",
        strict_paths={"main.py", "models.py", "crud.py"},
    )

    assert [item["path"] for item in result["file_plan"]] == [
        "crud.py",
        "main.py",
        "models.py",
    ]
    assert result["file_plan"][0]["description"] == "实现 crud.py"
    assert result["file_plan"][1]["description"] == "entry"
