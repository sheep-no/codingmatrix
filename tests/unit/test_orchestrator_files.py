import types

import pytest

from app.agent.orchestrator_files import FilesMixin
from app.agent.orchestrator_files import _fix_absolute_imports
from app.agent.orchestrator_files import _validate_python_project_imports
from app.agent.orchestrator_files import _validate_python_implementation
from app.agent.orchestrator_files import _structured_import_diagnostics
from app.agent.orchestrator_files import _validate_python_database_abstraction
from app.agent.orchestrator_files import _validate_python_contract
from app.agent.orchestrator_files import _repair_python_shared_base
from app.agent.orchestrator_files import _repair_python_sqlalchemy_metadata_owner
from app.agent.orchestrator_files import _repair_python_sqlalchemy_text_execute
from app.agent.orchestrator_files import _repair_python_sqlalchemy_get_db
from app.agent.orchestrator_files import _repair_python_sqlalchemy_table_initialization
from app.agent.orchestrator_files import _repair_python_test_database_fixtures
from app.agent.orchestrator_files import _repair_python_project_call_keywords
from app.agent.orchestrator_files import _repair_python_schema_field_access
from app.agent.orchestrator_files import _repair_python_known_imports
from app.agent.orchestrator_files import _repair_python_project_symbol_imports
from app.agent.orchestrator_files import _repair_python_sync_async_calls
from app.agent.orchestrator_files import _validate_python_sqlalchemy_metadata_owner
from app.agent.orchestrator_files import _validate_python_schema_field_access
from app.agent.architect import Architect
from app.agent.dependency_graph import DependencyGraph
from app.agent.backend_engineer import BackendEngineer
from app.agent.shared_context import SharedContext
from app.agent.orchestration.artifact_committer import ArtifactCommitter


def test_sync_project_call_does_not_use_await():
    content = "from repository import create_todo\n\nasync def route(db, todo):\n    return await create_todo(db, todo)\n"
    generated = {
        "repository.py": "def create_todo(db, todo):\n    return todo\n",
    }

    repaired = _repair_python_sync_async_calls(content, generated)

    assert "return create_todo(db, todo)" in repaired
    compile(repaired, "main.py", "exec")


def test_async_project_call_keeps_await():
    content = "from repository import create_todo\n\nasync def route(db, todo):\n    return await create_todo(db, todo)\n"
    generated = {
        "repository.py": "async def create_todo(db, todo):\n    return todo\n",
    }

    assert _repair_python_sync_async_calls(content, generated) == content


def test_database_fixture_context_is_not_called_directly():
    content = """import pytest
from fastapi.testclient import TestClient
from database import Base, engine

@pytest.fixture(scope='function')
def test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope='function')
def test_client(test_db):
    with TestClient(app) as client:
        yield client

def test_create(test_client):
    with test_db() as db:
        response = test_client.get('/health')
        assert response.status_code == 200
"""

    repaired = _repair_python_test_database_fixtures(content, "api_test.py", {})

    assert "with test_db()" not in repaired
    assert "response = test_client.get('/health')" in repaired


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


def test_known_import_repair_adds_only_reported_framework_symbols():
    content = "def endpoint(db: Session = Depends(get_db)):\n    return db\n"

    repaired = _repair_python_known_imports(content, [
        "名称 Depends 在模块全局作用域中未定义或导入",
        "名称 Session 在模块全局作用域中未定义或导入",
        "名称 get_db 在模块全局作用域中未定义或导入",
    ])

    assert repaired.startswith(
        "from fastapi import Depends\nfrom sqlalchemy.orm import Session\n"
    )
    assert "from database import get_db" not in repaired


def test_known_import_repair_adds_datetime_for_model_defaults():
    content = "created_at = Column(DateTime, default=datetime.utcnow)\n"

    repaired = _repair_python_known_imports(content, [
        "名称 datetime 在模块全局作用域中未定义或导入",
    ])

    assert repaired == "from datetime import datetime\n" + content


def test_known_import_repair_normalizes_sqlalchemy_sessionmaker_module():
    repaired = _repair_python_known_imports(
        "from sqlalchemy.ext.session import sessionmaker\n",
        ["模块 sqlalchemy.ext.session 当前运行时不可导入"],
    )

    assert repaired == "from sqlalchemy.orm import sessionmaker\n"


def test_known_import_repair_adds_reported_typing_symbol():
    content = "def list_todos() -> List[str]:\n    return []\n"

    repaired = _repair_python_known_imports(content, [
        "名称 List 在模块全局作用域中未定义或导入",
    ])

    assert repaired == "from typing import List\n" + content


def test_sqlalchemy_table_initialization_uses_renamed_contract_roles():
    architecture = {
        "file_plan": [
            {"path": "persistence.py", "file_type": "database", "contract": {"role": "database"}},
            {"path": "entities.py", "file_type": "model", "contract": {"role": "model"}},
            {"path": "app_entry.py", "file_type": "entry", "contract": {"role": "entry"}},
        ]
    }
    generated = {
        "persistence.py": (
            "from sqlalchemy import create_engine\n"
            "engine = create_engine('sqlite:///todos.db')\n"
            "Base = object()\n"
        ),
        "entities.py": "class Todo:\n    pass\n",
    }

    repaired = _repair_python_sqlalchemy_table_initialization(
        "from entities import Todo\napp = object()\n",
        "app_entry.py",
        generated,
        architecture,
    )

    assert "from persistence import Base, engine" in repaired
    assert "Base.metadata.create_all(bind=engine)" in repaired


def test_sqlalchemy_table_initialization_replaces_session_bind_with_engine():
    architecture = {
        "file_plan": [
            {"path": "persistence.py", "file_type": "database"},
            {"path": "app_entry.py", "file_type": "entry"},
        ]
    }
    generated = {
        "persistence.py": (
            "from sqlalchemy import create_engine\n"
            "engine = create_engine('sqlite:///todos.db')\n"
            "Base = object()\n"
        ),
    }
    content = (
        "from persistence import Base, SessionLocal\n"
        "def create_tables():\n"
        "    with SessionLocal() as db:\n"
        "        Base.metadata.create_all(bind=db)\n"
    )

    repaired = _repair_python_sqlalchemy_table_initialization(
        content, "app_entry.py", generated, architecture
    )

    assert "from persistence import engine" in repaired
    assert "Base.metadata.create_all(bind=engine)" in repaired


def test_database_test_fixture_repair_adds_setup_dependency_and_isolation():
    content = (
        "import pytest\n"
        "from fastapi.testclient import TestClient\n\n"
        "@pytest.fixture(scope='module')\n"
        "def test_db():\n"
        "    Base.metadata.create_all(bind=engine)\n"
        "    yield\n"
        "    Base.metadata.drop_all(bind=engine)\n\n"
        "@pytest.fixture(scope='module')\n"
        "def client():\n"
        "    return TestClient(app)\n"
    )

    repaired = _repair_python_test_database_fixtures(content, "api_test.py", {
        "file_plan": [
            {"path": "api_test.py", "file_type": "test", "contract": {"role": "test"}},
        ]
    })

    assert repaired.count("@pytest.fixture(scope='function')") == 2
    assert "def client(test_db):" in repaired


def test_sqlalchemy_text_execute_repair_wraps_raw_sql_literals():
    content = (
        "from sqlalchemy import create_engine\n\n"
        "def reset(engine):\n"
        "    with engine.connect() as connection:\n"
        "        connection.execute(\"DROP TABLE IF EXISTS todos\")\n"
        "        connection.execute(text(\"SELECT 1\"))\n"
    )

    repaired = _repair_python_sqlalchemy_text_execute(content, "test_main.py")

    assert repaired.startswith("from sqlalchemy import text\n")
    assert 'connection.execute(text("DROP TABLE IF EXISTS todos"))' in repaired
    assert repaired.count('connection.execute(text("SELECT 1"))') == 1


def test_sqlalchemy_get_db_repair_completes_session_dependency():
    content = (
        "from sqlalchemy.orm import sessionmaker\n"
        "SessionLocal = sessionmaker()\n"
    )

    repaired = _repair_python_sqlalchemy_get_db(content, "database.py")

    assert "def get_db():" in repaired
    assert "db = SessionLocal()" in repaired
    assert "finally:\n        db.close()" in repaired


def test_sqlalchemy_get_db_repair_uses_renamed_database_role():
    architecture = {
        "file_plan": [{"path": "persistence.py", "file_type": "database"}]
    }
    repaired = _repair_python_sqlalchemy_get_db(
        "SessionLocal = sessionmaker()\n", "persistence.py", architecture
    )

    assert "def get_db():" in repaired


def test_project_call_keyword_repair_removes_only_rejected_keywords():
    content = "items = get_todos(db, skip=skip, limit=limit, active=True)\n"

    repaired = _repair_python_project_call_keywords(content, [
        "调用 get_todos 使用了未声明参数 limit, skip，请匹配 crud.py 中的真实签名"
    ])

    assert repaired == "items = get_todos(db, active=True)\n"


def test_schema_field_repair_removes_invalid_create_keyword_and_update_branch():
    content = (
        "def create_record(record):\n"
        "    return Record(title=record.title, user_id=record.user_id)\n\n"
        "def update_record(db_record, record_update):\n"
        "    if record_update.user_id is not None:\n"
        "        db_record.user_id = record_update.user_id\n"
        "    if record_update.title is not None:\n"
        "        db_record.title = record_update.title\n"
        "    return db_record\n"
    )

    repaired = _repair_python_schema_field_access(content, [
        "crud.py 访问 record.user_id，但 schemas.py 的 RecordCreate 未定义字段 user_id",
        "crud.py 访问 record_update.user_id，但 schemas.py 的 RecordUpdate 未定义字段 user_id",
    ])

    assert "user_id=record.user_id" not in repaired
    assert "record_update.user_id" not in repaired
    assert "title=record.title" in repaired
    assert "db_record.title = record_update.title" in repaired
    compile(repaired, "crud.py", "exec")


def test_project_symbol_repair_imports_unique_dependency_export():
    repaired = _repair_python_project_symbol_imports(
        "def build():\n    return Todo(title='test')\n",
        ["名称 Todo 在模块全局作用域中未定义或导入"],
        {
            "models.py": "class Todo:\n    pass\n",
            "schemas.py": "class TodoCreate:\n    pass\n",
        },
    )

    assert repaired.startswith("from models import Todo\n")


def test_project_symbol_repair_prefers_definition_over_reexport():
    repaired = _repair_python_project_symbol_imports(
        "payload = TodoUpdate(title='updated')\n",
        ["名称 TodoUpdate 在模块全局作用域中未定义或导入"],
        {
            "schemas.py": "class TodoUpdate:\n    pass\n",
            "main.py": "from schemas import TodoUpdate\n",
        },
    )

    assert repaired.startswith("from schemas import TodoUpdate\n")


def test_schema_field_gate_rejects_missing_request_attributes():
    content = (
        "from schemas import TodoCreate\n\n"
        "def create_todo(todo: TodoCreate):\n"
        "    return todo.title, todo.created_at\n"
    )

    errors = _validate_python_schema_field_access(
        content,
        "crud.py",
        {
            "schemas.py": (
                "from pydantic import BaseModel\n\n"
                "class TodoCreate(BaseModel):\n"
                "    title: str\n"
            ),
        },
    )

    assert errors == [
        "crud.py 访问 todo.created_at，但 schemas.py 的 TodoCreate 未定义字段 created_at"
    ]


def test_schema_field_gate_allows_declared_fields_and_pydantic_methods():
    content = (
        "from schemas import TodoUpdate\n\n"
        "def update_todo(todo: TodoUpdate):\n"
        "    return todo.title, todo.model_dump(exclude_unset=True)\n"
    )

    errors = _validate_python_schema_field_access(
        content,
        "crud.py",
        {"schemas.py": "class TodoUpdate:\n    title: str | None = None\n"},
    )

    assert errors == []


def test_test_contract_allows_pytest_and_fastapi_client_imports():
    architecture = {
        "file_plan": [{
            "path": "test_main.py",
            "file_type": "test",
            "contract": {
                "role": "verification",
                "forbidden_imports": ["pytest", "fastapi.testclient", "requests"],
            },
        }],
    }
    content = "import pytest\nfrom fastapi.testclient import TestClient\nimport requests\n"

    errors = _validate_python_contract(content, "test_main.py", architecture)

    assert errors == ["test_main.py 违反架构契约，禁止导入模块 requests"]


def test_test_contract_allows_standard_library_isolation_helpers():
    architecture = {
        "file_plan": [{
            "path": "test_main.py",
            "file_type": "test",
            "contract": {
                "role": "verification",
                "forbidden_imports": [
                    "os", "sys", "pathlib", "json", "tempfile", "requests",
                ],
            },
        }],
    }
    content = (
        "import json\nimport os\nfrom pathlib import Path\n"
        "import sys\nimport tempfile\nimport requests\n"
    )

    errors = _validate_python_contract(content, "test_main.py", architecture)

    assert errors == ["test_main.py 违反架构契约，禁止导入模块 requests"]


def test_test_structure_rejects_nested_tests_and_invalid_pytestconfig_tmp_path():
    from app.agent.orchestrator_files import _validate_python_test_structure

    content = """
import pytest

@pytest.fixture
def tmp_data_file(pytestconfig):
    return pytestconfig.tmp_path / 'data.json'

def test_outer():
    def test_inner(monkeypatch):
        monkeypatch.setattr('todo.DB_FILE_PATH', 'x')
"""

    errors = _validate_python_test_structure(content, "test_main.py")

    assert any("test_inner 必须定义在模块顶层" in error for error in errors)
    assert any("pytestconfig 获取 tmp_path" in error for error in errors)


def test_test_contract_does_not_require_public_api_exports():
    architecture = {
        "file_plan": [{
            "path": "test_main.py",
            "file_type": "test",
            "contract": {"exports": ["test_app"]},
        }],
    }

    errors = _validate_python_contract(
        "def test_create_todo():\n    assert True\n",
        "test_main.py",
        architecture,
    )

    assert errors == []


def test_entry_contract_allows_architecture_selected_fastapi_import():
    architecture = {
        "tech_stack": ["FastAPI", "SQLAlchemy"],
        "file_plan": [{
            "path": "main.py",
            "file_type": "entry",
            "contract": {
                "role": "application_entry",
                "forbidden_imports": ["fastapi", "requests"],
            },
        }],
    }
    content = "from fastapi import FastAPI\nimport requests\napp = FastAPI()\n"

    errors = _validate_python_contract(content, "main.py", architecture)

    assert errors == ["main.py 违反架构契约，禁止导入模块 requests"]


def test_api_contract_allows_framework_from_default_project_spec():
    architecture = {
        "project_spec": {"default": {"framework": "FastAPI"}},
        "file_plan": [{
            "path": "routes.py",
            "file_type": "api",
            "contract": {"forbidden_imports": ["fastapi"]},
        }],
    }

    errors = _validate_python_contract(
        "from fastapi import APIRouter\nrouter = APIRouter()\n",
        "routes.py",
        architecture,
    )

    assert errors == []


def test_database_abstraction_gate_rejects_mixed_sqlite_and_sqlalchemy():
    errors = _validate_python_database_abstraction(
        "import sqlite3\nfrom sqlalchemy import create_engine\n",
        "database.py",
    )

    assert errors == ["database.py 同时使用 sqlite3 和 SQLAlchemy，必须统一为一种数据库抽象"]


def test_database_abstraction_gate_uses_renamed_database_role():
    architecture = {
        "file_plan": [{"path": "persistence.py", "file_type": "database"}]
    }
    errors = _validate_python_database_abstraction(
        "import sqlite3\nfrom sqlalchemy import create_engine\n",
        "persistence.py",
        architecture,
    )

    assert errors == [
        "persistence.py 同时使用 sqlite3 和 SQLAlchemy，必须统一为一种数据库抽象"
    ]


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


def test_python_contract_gate_uses_declared_role_and_forbidden_imports():
    architecture = {
        "file_plan": [{
            "path": "storage_layer.py",
            "contract": {
                "role": "persistence",
                "forbidden_imports": ["web_framework"],
                "database_abstraction": "sqlite3",
            },
        }]
    }
    errors = _validate_python_contract(
        "import web_framework\nimport sqlite3\n\nclass Store:\n    pass\n",
        "storage_layer.py",
        architecture,
    )

    assert "storage_layer.py 违反架构契约，禁止导入模块 web_framework" in errors


def test_python_contract_gate_rejects_missing_declared_exports():
    architecture = {
        "file_plan": [{
            "path": "database.py",
            "contract": {
                "role": "database",
                "exports": ["Base", "engine", "SessionLocal", "get_db()"],
                "database_abstraction": "sqlalchemy",
            },
        }]
    }

    errors = _validate_python_contract(
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import declarative_base, sessionmaker\n"
        "Base = declarative_base()\n"
        "engine = create_engine('sqlite:///todos.db')\n"
        "SessionLocal = sessionmaker(bind=engine)\n",
        "database.py",
        architecture,
    )

    assert errors == ["database.py 未导出架构契约要求的公共符号 get_db"]


def test_python_contract_gate_accepts_declared_function_export():
    architecture = {
        "file_plan": [{
            "path": "database.py",
            "contract": {"exports": ["get_db()", "database session factory"]},
        }]
    }

    errors = _validate_python_contract(
        "def get_db():\n    yield object()\n",
        "database.py",
        architecture,
    )

    assert errors == []


def test_shared_sqlalchemy_base_repair_reuses_database_base():
    content = (
        "from sqlalchemy.ext.declarative import declarative_base\n"
        "Base = declarative_base()\n\n"
        "class Todo(Base):\n"
        "    pass\n"
    )

    repaired = _repair_python_shared_base(
        content,
        "models.py",
        {"database.py": "from sqlalchemy.ext.declarative import declarative_base\nBase = declarative_base()\n"},
    )

    assert repaired.startswith("from database import Base\n")
    assert "declarative_base" not in repaired


def test_shared_sqlalchemy_base_repair_uses_renamed_roles():
    architecture = {
        "file_plan": [
            {"path": "persistence.py", "file_type": "database"},
            {"path": "entities.py", "file_type": "model"},
        ]
    }
    repaired = _repair_python_shared_base(
        "from sqlalchemy.orm import declarative_base\n"
        "Base = declarative_base()\n"
        "class Todo(Base):\n"
        "    pass\n",
        "entities.py",
        {"persistence.py": "Base = declarative_base()\n"},
        architecture,
    )

    assert repaired.startswith("from persistence import Base\n")
    assert "declarative_base" not in repaired


def test_sqlalchemy_metadata_owner_repair_uses_database_base():
    content = (
        "from models import Todo\n"
        "from database import engine\n\n"
        "Todo.Base.metadata.create_all(bind=engine)\n"
    )

    repaired = _repair_python_sqlalchemy_metadata_owner(
        content,
        "main.py",
        {"database.py": "Base = declarative_base()\nengine = object()\n"},
    )

    assert repaired.startswith("from database import Base\n")
    assert "Base.metadata.create_all(bind=engine)" in repaired
    assert "Todo.Base" not in repaired
    assert _validate_python_sqlalchemy_metadata_owner(repaired, "main.py") == []


def test_sqlalchemy_metadata_owner_repair_uses_renamed_database_role():
    architecture = {
        "file_plan": [
            {"path": "persistence.py", "file_type": "database"},
            {"path": "app_entry.py", "file_type": "entry"},
        ]
    }
    repaired = _repair_python_sqlalchemy_metadata_owner(
        "Todo.Base.metadata.create_all(bind=engine)\n",
        "app_entry.py",
        {"persistence.py": "Base = declarative_base()\nengine = object()\n"},
        architecture,
    )

    assert repaired.startswith("from persistence import Base\n")
    assert "Base.metadata.create_all(bind=engine)" in repaired


def test_sqlalchemy_metadata_owner_gate_rejects_model_base_reference():
    errors = _validate_python_sqlalchemy_metadata_owner(
        "Todo.Base.metadata.create_all(bind=engine)\n",
        "main.py",
    )

    assert errors == [
        "main.py 必须通过共享 Base.metadata.create_all 初始化 SQLAlchemy 元数据"
    ]


def test_sqlalchemy_metadata_owner_gate_allows_module_base_reference():
    content = "models.Base.metadata.create_all(bind=engine)\n"

    assert _validate_python_sqlalchemy_metadata_owner(content, "main.py") == []
    assert _repair_python_sqlalchemy_metadata_owner(
        content,
        "main.py",
        {"database.py": "Base = declarative_base()\n"},
    ) == content


def test_backend_engineer_prefers_file_plan_type_for_nonstandard_filename():
    constraints = BackendEngineer._build_contract_constraints(
        "storage_layer.py",
        {
            "file_plan": [{
                "path": "storage_layer.py",
                "file_type": "database",
                "contract": {
                    "role": "persistence",
                    "exports": ["open_store"],
                    "database_abstraction": "sqlite3",
                },
            }]
        },
    )

    assert "职责: persistence" in constraints
    assert "必须导出的公共符号: open_store" in constraints


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
    manifest = context.get_artifact_manifest()
    assert manifest["main.py"]["status"] == "generated"
    assert manifest["main.py"]["validation_passed"] is True


@pytest.mark.asyncio
async def test_single_file_generation_routes_empty_extraction_to_fallback(tmp_path, monkeypatch):
    async def extract_content(*_args, **_kwargs):
        return None

    async def direct_generate(*_args, **_kwargs):
        return "def recovered_value():\n    return True\n"

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    monkeypatch.setattr(orchestrator, "_direct_llm_generate_file", direct_generate)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == (
        "def recovered_value():\n    return True"
    )


@pytest.mark.asyncio
async def test_single_file_generation_passes_heartbeat_tracker(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    received_trackers = []

    async def generate_file(*_args, **kwargs):
        received_trackers.append(kwargs.get("heartbeat_tracker"))
        return "def main():\n    return True\n"

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate_file,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    orchestrator.heartbeat_timeout = 42.0
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert len(received_trackers) == 1
    assert received_trackers[0].timeout == 42.0


@pytest.mark.asyncio
async def test_invalid_content_retry_reuses_heartbeat_tracker(tmp_path, monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    received_trackers = []
    responses = iter(["", "def main():\n    return True\n"])

    async def generate_file(*_args, **kwargs):
        received_trackers.append(kwargs.get("heartbeat_tracker"))
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师",
        clear_edits=lambda: None,
        generate_file=generate_file,
    )
    orchestrator = _FilesTestOrchestrator(tmp_path)
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert len(received_trackers) == 2
    assert received_trackers[0] is received_trackers[1]


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
async def test_static_repair_retries_after_invalid_response(tmp_path, monkeypatch):
    invalid_response = "已完成修复，请查收。"

    async def extract_content(content, *_args, **_kwargs):
        return None if content == invalid_response else content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    responses = iter([
        (
            "import sqlite3\n"
            "from sqlalchemy import create_engine\n\n"
            "def connect():\n"
            "    return sqlite3.connect('todos.db')\n"
        ),
        invalid_response,
        (
            "from sqlalchemy import create_engine\n\n"
            "engine = create_engine('sqlite:///todos.db')\n"
        ),
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
        {"path": "database.py", "description": "database"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert len(calls) == 3
    assert "修复响应无效" in calls[2]
    assert "import sqlite3" in calls[2]
    assert (tmp_path / "database.py").read_text(encoding="utf-8") == (
        "from sqlalchemy import create_engine\n\n"
        "engine = create_engine('sqlite:///todos.db')\n"
    )


@pytest.mark.asyncio
async def test_repeated_invalid_static_repair_response_stops_early(tmp_path, monkeypatch):
    invalid_response = "已完成修复，请查收。"

    async def extract_content(content, *_args, **_kwargs):
        return None if content == invalid_response else content

    monkeypatch.setattr(
        "app.agent.orchestrator_files.extract_engineer_content",
        extract_content,
    )
    responses = iter([
        (
            "import sqlite3\n"
            "from sqlalchemy import create_engine\n\n"
            "def connect():\n"
            "    return sqlite3.connect('todos.db')\n"
        ),
        invalid_response,
        invalid_response,
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
        {"path": "database.py", "description": "database"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is False
    assert len(calls) == 3
    assert "修复响应无效" in orchestrator.errors[-1]


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


def test_backend_runtime_constraints_require_real_temporary_file_persistence():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "test_main.py",
        "test",
        "python",
        {
            "file_plan": [
                {"path": "todo.py", "file_type": "service"},
                {"path": "test_main.py", "file_type": "test"},
            ]
        },
    )

    assert "tmp_path 创建真实临时文件" in constraints
    assert "pytest monkeypatch 替换存储路径" in constraints
    assert "禁止 patch 或 mock builtins.open" in constraints
    assert "禁止用 unittest.mock.patch 或 MagicMock 替代" in constraints
    assert "连续 CRUD 操作必须读写同一个真实临时文件" in constraints
    assert "导入模块（例如 import todo）并使用 monkeypatch.setattr" in constraints
    assert "禁止实例化 pytest.MonkeyPatch" in constraints
    assert "禁止手动保存和恢复被 patch 的符号" in constraints
    assert "每个操作后重新调用 list_todos()" in constraints


def test_backend_runtime_constraints_define_module_level_crud_contract():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "repository.py",
        "repository",
        "python",
        {
            "framework": "FastAPI",
            "file_plan": [{
                "path": "repository.py",
                "file_type": "repository",
                "contract": {
                    "exports": [
                        "create_todo",
                        "get_todos",
                        "get_todo",
                        "update_todo",
                        "delete_todo",
                    ]
                },
            }],
        },
    )

    assert "架构契约要求当前模块直接导出公共符号" in constraints
    assert "create_todo, get_todos, get_todo, update_todo, delete_todo" in constraints
    assert "必须实现真实持久化操作" in constraints
    assert "只能读取请求 Schema 实际声明的字段" in constraints


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


def test_backend_database_constraints_define_sqlalchemy_foundation_for_model_project():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "database.py",
        "database",
        "python",
        {
            "framework": "FastAPI",
            "file_plan": [{"path": "database.py"}, {"path": "models.py"}],
        },
    )

    assert "当前项目包含模型层；数据库层统一采用 SQLAlchemy" in constraints
    assert "当前模型文件为 models.py" in constraints
    assert "Base = declarative_base()、engine、SessionLocal 和 get_db" in constraints
    assert "禁止创建 Web 应用、声明路由" in constraints


def test_backend_main_constraints_keep_routes_inside_strict_file_set():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "main.py",
        "entry",
        "python",
        {
            "framework": "FastAPI",
            "file_plan": [{"path": "main.py"}, {"path": "database.py"}],
        },
    )

    assert "所有 API 路由必须直接定义在 main.py" in constraints
    assert "禁止导入未声明的路由模块" in constraints
    assert "必须从 database.py 显式导入" in constraints
    assert "GET、POST 均使用 /api/v1/todos" in constraints


def test_backend_runtime_constraints_use_renamed_architecture_paths():
    architecture = {
        "framework": "FastAPI",
        "file_plan": [
            {"path": "persistence.py", "file_type": "database"},
            {"path": "entities.py", "file_type": "model"},
            {"path": "repository.py", "file_type": "repository"},
            {"path": "app_entry.py", "file_type": "entry"},
            {"path": "api_test.py", "file_type": "test"},
        ],
    }

    model_constraints = BackendEngineer._build_runtime_consistency_constraints(
        "entities.py", "model", "python", architecture
    )
    entry_constraints = BackendEngineer._build_runtime_consistency_constraints(
        "app_entry.py", "entry", "python", architecture
    )
    test_constraints = BackendEngineer._build_runtime_consistency_constraints(
        "api_test.py", "test", "python", architecture
    )

    assert "from persistence import Base" in model_constraints
    assert "所有 API 路由必须直接定义在 app_entry.py" in entry_constraints
    assert "必须从 persistence.py 显式导入" in entry_constraints
    assert "复用已生成 persistence.py" in test_constraints


def test_backend_runtime_constraints_require_models_to_share_database_base():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "models.py",
        "model",
        "python",
        {"framework": "FastAPI"},
    )

    assert "from database import Base" in constraints
    assert "禁止在 models.py 中再次调用 declarative_base()" in constraints
    assert "主键必须使用自增 Integer" in constraints
    assert "时间列存在时必须提供 datetime 默认值" in constraints


def test_backend_schema_constraints_match_generated_models():
    constraints = BackendEngineer._build_runtime_consistency_constraints(
        "schemas.py",
        "types",
        "python",
        {"framework": "FastAPI"},
    )

    assert "请求 Schema 只声明客户端可提交字段" in constraints
    assert "逐项匹配依赖源码中的 ORM 模型列" in constraints
    assert "从 ORM 属性读取数据" in constraints


@pytest.mark.asyncio
async def test_backend_model_prompt_follows_sqlite_database_abstraction(tmp_path, monkeypatch):
    prompts = []
    call_kwargs = []

    async def call_llm_with_tools(prompt, *_args, **_kwargs):
        prompts.append(prompt)
        call_kwargs.append(_kwargs)
        return "class Todo:\n    pass\n"

    engineer = BackendEngineer("测试工程师", "test-model")
    monkeypatch.setattr(engineer, "call_llm_with_tools", call_llm_with_tools)

    await engineer.generate_file(
        "models.py",
        "model",
        {"architecture": {"language": "python"}},
        dep_context=(
            "## 依赖文件: database.py\n"
            "```python\nimport sqlite3\n\n"
            "def get_db():\n    return sqlite3.connect('todos.db')\n```\n"
        ),
        project_path=str(tmp_path),
    )

    assert "已生成的 database.py 使用原生 sqlite3" in prompts[0]
    assert "禁止导入 SQLAlchemy" in prompts[0]
    assert call_kwargs[0]["react_mode"] == "simple"


@pytest.mark.asyncio
async def test_backend_model_prompt_requires_reusing_sqlalchemy_database_base(tmp_path, monkeypatch):
    prompts = []

    async def call_llm_with_tools(prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return "from database import Base\n"

    engineer = BackendEngineer("测试工程师", "test-model")
    monkeypatch.setattr(engineer, "call_llm_with_tools", call_llm_with_tools)

    await engineer.generate_file(
        "models.py",
        "model",
        {"architecture": {"language": "python"}},
        dep_context=(
            "## 依赖文件: database.py\n"
            "```python\nfrom sqlalchemy.orm import declarative_base\n"
            "Base = declarative_base()\n```\n"
        ),
        project_path=str(tmp_path),
    )

    assert "已生成的 database.py 已导出 SQLAlchemy Base" in prompts[0]
    assert "必须直接使用 `from database import Base`" in prompts[0]
    assert "禁止导入或调用 declarative_base()" in prompts[0]


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


def test_project_symbol_repair_relocates_import_to_unique_definition():
    repaired = _repair_python_project_symbol_imports(
        "from crud import create_todo, get_db\n",
        ["crud.py 未导出符号 get_db，请使用其真实接口"],
        {
            "crud.py": "def create_todo():\n    return None\n",
            "database.py": "def get_db():\n    yield object()\n",
        },
    )

    assert "from crud import create_todo" in repaired
    assert "from database import get_db" in repaired
    assert "from crud import create_todo, get_db" not in repaired


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


def test_python_import_gate_resolves_unique_short_project_module_alias():
    errors = _validate_python_project_imports(
        "from models import TodoModel\n",
        "src/main.py",
        {"src/models/todo_model.py": "class TodoModel:\n    pass\n"},
        ["src/main.py", "src/models/todo_model.py"],
    )

    assert errors == []


def test_database_may_defer_unique_model_import_until_model_layer():
    errors = _validate_python_project_imports(
        "from models import TodoItem\n",
        "src/database.py",
        {},
        ["src/database.py", "src/models.py"],
        {"file_plan": [
            {"path": "src/database.py", "file_type": "database"},
            {"path": "src/models.py", "file_type": "model"},
        ]},
    )

    assert errors == []


def test_python_import_gate_rejects_missing_external_symbol():
    errors = _validate_python_project_imports(
        "from typing import Session\n",
        "crud.py",
        {},
        ["crud.py"],
    )

    assert errors == ["模块 typing 未导出符号 Session，请使用其真实接口"]


def test_python_import_gate_rejects_unavailable_external_submodule():
    errors = _validate_python_project_imports(
        "from sqlalchemy.ext.session import sessionmaker\n",
        "database.py",
        {},
        ["database.py"],
    )

    assert errors == ["模块 sqlalchemy.ext.session 当前运行时不可导入"]


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


def test_extract_strict_paths_from_only_generate_following_expression():
    requirement = "只生成以下 3 个 Python CLI 文件：main.py、todo.py、test_main.py。"

    assert Architect._extract_strict_file_paths(requirement) == {
        "main.py", "todo.py", "test_main.py"
    }

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
    assert result["strict_file_paths"] == ["main.py", "models.py"]


@pytest.mark.asyncio
async def test_expand_file_plan_preserves_frozen_strict_scope():
    architect = object.__new__(Architect)
    architecture = {
        "language": "python",
        "file_plan": [{"path": "main.py"}, {"path": "todo.py"}, {"path": "test_main.py"}],
        "strict_file_paths": ["main.py", "test_main.py", "todo.py"],
    }

    result = await architect.expand_file_plan(
        architecture,
        complexity=None,
        target_file_count=15,
        target_language="python",
    )

    assert result is architecture
    assert [item["path"] for item in result["file_plan"]] == [
        "main.py", "todo.py", "test_main.py"
    ]


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
