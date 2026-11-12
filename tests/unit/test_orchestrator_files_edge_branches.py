"""Edge-case branches still uncovered by the main orchestrator_files suites."""

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from app.agent import orchestrator_files as of
from app.agent.code_patcher import CrossFilePatchResult, PatchResult
from app.agent.dependency_graph import DependencyGraph


def test_schema_repair_visit_if_without_body_inserts_pass():
    content = (
        "def handler(todo):\n"
        "    if not todo.missing:\n"
        "        pass\n"
        "    return 1\n"
    )
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    # Removing the test leaves the if body empty, forcing the Pass fallback.
    repaired = of._repair_python_schema_field_access(content, errors)
    compile(repaired, "main.py", "exec")


def test_schema_repair_ann_assign_without_value_is_kept():
    content = (
        "def handler(todo):\n"
        "    result: int\n"
        "    return todo.missing\n"
    )
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    repaired = of._repair_python_schema_field_access(content, errors)
    compile(repaired, "main.py", "exec")


def test_schema_repair_function_with_empty_body_after_transform_gets_pass():
    content = (
        "def handler(todo):\n"
        "    value = todo.missing\n"
    )
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    repaired = of._repair_python_schema_field_access(content, errors)
    compile(repaired, "main.py", "exec")
    assert "def handler" in repaired


def test_schema_repair_if_body_emptied_by_removed_assignment_gets_pass():
    content = (
        "def handler(todo):\n"
        "    if True:\n"
        "        value = todo.missing\n"
        "    return 1\n"
    )
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    repaired = of._repair_python_schema_field_access(content, errors)

    compile(repaired, "main.py", "exec")
    assert "missing" not in repaired


def test_python_exports_ignores_attribute_assignment_targets():
    assert of._python_exports("obj.attr = 1\n") == set()


def test_file_matches_role_infers_schema_from_path():
    assert of._file_matches_role("schemas.py", None, {"schema"}) is True


def _entry_arch() -> dict:
    return {
        "file_plan": [
            {"path": "main.py", "file_type": "entry"},
            {"path": "database.py", "file_type": "database"},
        ]
    }


def test_table_initialization_returns_on_broken_entry_with_database_dep():
    content = "def broken(:\n"
    generated = {
        "database.py": (
            "from sqlalchemy.orm import declarative_base\n"
            "Base = declarative_base()\n"
            "engine = object()\n"
        )
    }

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, _entry_arch()
    ) == content


def test_table_initialization_skips_when_database_lacks_engine():
    content = "def main():\n    return 1\n"
    generated = {
        "database.py": (
            "from sqlalchemy.orm import declarative_base\n"
            "Base = declarative_base()\n"
        )
    }

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, _entry_arch()
    ) == content


def test_table_initialization_returns_unchanged_when_create_all_already_bound():
    content = (
        "from database import Base, engine\n"
        "Base.metadata.create_all(bind=engine)\n"
    )
    generated = {
        "database.py": (
            "from sqlalchemy.orm import declarative_base\n"
            "Base = declarative_base()\n"
            "engine = object()\n"
        )
    }

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, _entry_arch()
    ) == content


def test_table_initialization_inserts_after_module_docstring():
    content = '"""Entry module."""\nimport os\n\ndef main():\n    return 1\n'
    generated = {
        "database.py": (
            "from sqlalchemy.orm import declarative_base\n"
            "Base = declarative_base()\n"
            "engine = object()\n"
        )
    }

    repaired = of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, _entry_arch()
    )

    assert repaired.startswith('"""Entry module."""')
    assert "create_all(bind=engine)" in repaired
    compile(repaired, "main.py", "exec")


def test_test_fixtures_return_unchanged_when_ast_unparse_is_identical():
    content = (
        "import pytest\n"
        "from fastapi.testclient import TestClient\n"
        "@pytest.fixture\n"
        "def test_db():\n"
        "    Base.metadata.create_all(bind=engine)\n"
        "    yield\n"
        "@pytest.fixture\n"
        "def test_client(test_db):\n"
        "    with TestClient(app) as client:\n"
        "        yield client\n"
        "def test_x(test_client):\n"
        "    assert test_client\n"
    )

    assert of._repair_python_test_database_fixtures(content, "test_api.py", None) == content


def test_test_fixtures_ignore_unrelated_decorator_and_non_engine_fixture():
    content = (
        "import pytest\n"
        "from fastapi.testclient import TestClient\n"
        "@marker\n"
        "def helper():\n"
        "    return 1\n"
        "@pytest.fixture\n"
        "def list_db():\n"
        "    Base.metadata.create_all(bind=engine)\n"
        "    yield\n"
        "def test_x():\n"
        "    assert TestClient\n"
    )

    repaired = of._repair_python_test_database_fixtures(content, "test_api.py", None)

    compile(repaired, "test_api.py", "exec")


def test_framework_roots_scans_project_spec_sections():
    architecture = {
        "project_spec": {
            "backend": {"framework": "Flask"},
            "frontend": "vue",
            "notes": None,
        }
    }

    assert "flask" in of._declared_python_framework_roots(architecture)


def test_framework_roots_skips_non_dict_project_spec():
    assert of._declared_python_framework_roots({"project_spec": "fastapi"}) == set()


def test_metadata_owner_repair_keeps_existing_base_import():
    content = (
        "from database import Base\n"
        "class Todo(Base):\n"
        "    pass\n"
        "Todo.Base.metadata.create_all()\n"
    )
    generated = {
        "database.py": "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"
    }

    repaired = of._repair_python_sqlalchemy_metadata_owner(
        content, "models.py", generated
    )

    assert repaired.count("import Base") == 1
    assert "Todo.Base.metadata" not in repaired


def test_project_imports_defers_model_import_for_database_module():
    architecture = {
        "file_plan": [
            {"path": "database.py", "file_type": "database"},
            {"path": "models.py", "file_type": "model"},
        ]
    }
    content = "from models import Todo\n\ndef run():\n    return Todo\n"

    errors = of._validate_python_project_imports(
        content, "database.py", {}, ["database.py", "models.py"], architecture
    )

    assert not any("尚未生成" in error for error in errors)


def test_project_imports_reports_syntax_error_in_generated_dependency(monkeypatch):
    content = "from utils import foo\n\ndef run():\n    return foo\n"

    real_exports = of._python_exports

    def exports(source):
        if source == "def (:":
            raise SyntaxError("bad")
        return real_exports(source)

    monkeypatch.setattr(of, "_python_exports", exports)

    assert of._validate_python_project_imports(
        content, "main.py", {"utils.py": "def (:"}, ["main.py", "utils.py"]
    ) == []


def test_project_imports_star_import_untracked(monkeypatch):
    content = "from utils import *\n"

    assert of._validate_python_project_imports(
        content, "main.py", {"utils.py": "foo = 1\n"}, ["main.py", "utils.py"]
    ) == []


def test_project_imports_accepts_generated_project_module_and_builtin():
    content = "import os\nimport utils\n\ndef run():\n    return utils.foo()\n"

    assert of._validate_python_project_imports(
        content, "main.py", {"utils.py": "def foo():\n    return 1\n"}, ["main.py", "utils.py"]
    ) == []


def test_project_imports_skips_non_function_export():
    content = "from utils import foo\n\ndef run():\n    return foo()\n"

    assert of._validate_python_project_imports(
        content, "main.py", {"utils.py": "foo = lambda: 1\n"}, ["main.py", "utils.py"]
    ) == []


def test_sync_async_repair_skips_await_on_non_name_call():
    content = "def main():\n    return await obj.fetch()\n"

    assert of._repair_python_sync_async_calls(content, {}) == content


def test_validate_test_structure_accepts_simple_test_module():
    assert of._validate_python_test_structure("def test_x():\n    pass\n", "test_main.py") == []


def test_project_symbol_imports_drops_fully_relocated_import():
    content = "from a import Foo\n\ndef use():\n    return Foo\n"
    errors = ["a.py 未导出符号 Foo，请使用其真实接口"]

    repaired = of._repair_python_project_symbol_imports(
        content, errors, {"a.py": "Bar = 1\n", "b.py": "class Foo:\n    pass\n"}
    )

    assert "from a import Foo" not in repaired
    assert "from b import Foo" in repaired


def test_fix_absolute_imports_ignores_non_python_project_files():
    content = "from src.utils.helpers import greet\n"

    repaired = of._fix_absolute_imports(
        content, "src/utils/api.py", ["src/utils/api.py", "README.md", "src/utils/helpers.py"]
    )

    assert "from .helpers import greet" in repaired


def test_fix_absolute_imports_keeps_import_when_target_not_in_package():
    content = "from src.utils.missing import greet\n"

    assert of._fix_absolute_imports(
        content, "src/utils/api.py", ["src/utils/api.py", "src/utils/helpers.py"]
    ) == content


def test_sqlalchemy_text_execute_keeps_existing_text_import():
    content = "from sqlalchemy import text\n\ndef read(db):\n    return db.execute('select 1')\n"

    repaired = of._repair_python_sqlalchemy_text_execute(content, "main.py")

    assert repaired.count("from sqlalchemy import text") == 1
    assert "text('select 1')" in repaired


def test_sqlalchemy_datetime_defaults_keeps_existing_func_import():
    content = "from sqlalchemy import func\n\ncreated = DateTime.utcnow()\n"

    repaired = of._repair_python_sqlalchemy_datetime_defaults(content, "models.py")

    assert repaired.count("from sqlalchemy import func") == 1
    assert "func.now()" in repaired


def test_sqlalchemy_get_db_keeps_existing_sessionmaker_import():
    architecture = {"file_plan": [{"path": "database.py", "file_type": "database"}]}
    content = (
        "from sqlalchemy.orm import sessionmaker\n"
        "SessionLocal = None\n"
    )

    repaired = of._repair_python_sqlalchemy_get_db(content, "database.py", architecture)

    assert repaired.count("from sqlalchemy.orm import sessionmaker") == 1
    assert "def get_db():" in repaired


def test_fastapi_route_registration_skips_unsupported_keywords():
    content = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "def list_item():\n"
        "    return []\n"
        "app.include_router(FastAPI(prefix='/items', routes=[\n"
        "    FastAPI.get('/items', summary='List all', tags=['x']),\n"
        "]))\n"
    )

    repaired = of._repair_python_fastapi_class_route_registration(content, "main.py")

    assert "app.add_api_route('/items/items', list_item, methods=[\"GET\"], summary='List all')" in repaired


def test_fastapi_route_registration_skips_keyword_without_segment(monkeypatch):
    content = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "def list_item():\n"
        "    return []\n"
        "app.include_router(FastAPI(prefix='/items', routes=[\n"
        "    FastAPI.get('/items', summary='List all'),\n"
        "]))\n"
    )
    real_get_source_segment = of.ast.get_source_segment

    def get_source_segment(source, node, *args, **kwargs):
        if getattr(node, "value", None) == "List all":
            return None
        return real_get_source_segment(source, node, *args, **kwargs)

    monkeypatch.setattr(of.ast, "get_source_segment", get_source_segment)

    repaired = of._repair_python_fastapi_class_route_registration(content, "main.py")

    assert "app.add_api_route('/items/items', list_item, methods=[\"GET\"])" in repaired


def test_database_fixture_repair_keeps_unrelated_fixture():
    content = (
        "import pytest\n"
        "from fastapi.testclient import TestClient\n"
        "from sqlalchemy import create_engine\n"
        "from database import Base\n\n"
        "@pytest.fixture\n"
        "def engine():\n"
        "    engine = create_engine('sqlite://')\n"
        "    Base.metadata.create_all(bind=engine)\n"
        "    return engine\n\n"
        "@pytest.fixture\n"
        "def client(tmp_path):\n"
        "    return TestClient(object())\n\n"
        "def test_list(client):\n"
        "    assert client.get('/todos').status_code == 200\n"
    )

    repaired = of._repair_python_test_database_fixtures(
        content, "test_main.py", {"file_plan": [{"path": "test_main.py", "file_type": "test"}]}
    )

    compile(repaired, "test_main.py", "exec")
    assert "def client(" in repaired
    assert "return TestClient(object())" in repaired


def test_project_import_gate_allows_deferred_model_import_from_database():
    errors = of._validate_python_project_imports(
        "from models import Todo\n",
        "database.py",
        {},
        ["database.py", "models.py"],
        {
            "file_plan": [
                {"path": "database.py", "file_type": "database"},
                {"path": "models.py", "file_type": "model"},
            ]
        },
    )

    assert errors == []


def test_project_import_gate_continues_after_deferred_alias():
    errors = of._validate_python_project_imports(
        "import models, os\n",
        "database.py",
        {},
        ["database.py", "models.py"],
        {
            "file_plan": [
                {"path": "database.py", "file_type": "database"},
                {"path": "models.py", "file_type": "model"},
            ]
        },
    )

    assert errors == []


class _Orchestrator(of.FilesMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.dependency_graph_obj = None
        self.cross_file_patcher = None
        self.feedback_learner = None
        self.cancel_event = None
        self._generated_contents = {}
        self.callback = None
        self.api_key_token = None
        self.require_approval = False
        self.enable_validation = False
        self.enable_review = False
        self.enable_error_recovery = False
        self.validator = None
        self.reviewer = None
        self.error_recovery = None
        self.api_contract_checker = None
        self.model_assignment = None
        self.progress = []
        self._call_llm_for_patch = AsyncMock()

    def _select_engineer(self, _file_path):
        async def generate_file(*_args, **_kwargs):
            return "def main():\n    return 1\n"

        return types.SimpleNamespace(
            name="测试工程师", clear_edits=lambda: None, generate_file=generate_file
        )

    def _select_model_for_file(self, _file_path):
        return "test-model"

    def _is_frontend_file(self, _file_path):
        return False

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))

    def _report_thinking(self, *_args, **_kwargs):
        return None

    def _report_file_event(self, *_args, **_kwargs):
        return None

    def _report_warning(self, **_kwargs):
        return None

    async def _wait_for_approval(self, _file_path):
        return True


@pytest.fixture
def extract_passthrough(monkeypatch):
    async def extract_content(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr(of, "extract_engineer_content", extract_content)


@pytest.mark.asyncio
async def test_small_project_rollback_without_stash_skips_pop(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    stash_calls = []
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: False)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: stash_calls.append("pop"))

    async def generate(*_args, **_kwargs):
        return {"path": "new.py", "success": False}

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    with pytest.raises(RuntimeError):
        await orchestrator._generate_files_small_project(
            [{"path": "new.py", "description": "d"}],
            {"architecture": {"language": "python"}},
            1,
        )

    assert stash_calls == []


@pytest.mark.asyncio
async def test_small_project_ignores_boolean_false_result(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)

    async def generate(*_args, **_kwargs):
        return False

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_small_project(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert orchestrator.generated_files == []


@pytest.mark.asyncio
async def test_small_project_backs_up_existing_files(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    (tmp_path / "main.py").write_text("old\n", encoding="utf-8")
    captured = {}

    def stash_push(_dir, files, _message):
        captured["files"] = files
        return True

    monkeypatch.setattr(of, "_git_stash_push", stash_push)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)

    async def generate(file_info, *_args, **_kwargs):
        return {"path": file_info["path"], "success": True}

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_small_project(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert captured["files"] == ["main.py"]


@pytest.mark.asyncio
async def test_small_project_none_result_triggers_rollback(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: True)

    async def generate(file_info, *_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)
    plan = [{"path": "skip.py", "description": "d"}, {"path": "main.py", "description": "d"}]

    with pytest.raises(RuntimeError, match="small project file generation failed"):
        await orchestrator._generate_files_small_project(
            plan, {"architecture": {"language": "python"}}, len(plan)
        )

    assert any("返回空内容" in error for error in orchestrator.errors)


@pytest.mark.asyncio
async def test_dep_layers_rollback_without_stash(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["skip.py"]]

    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: False)
    monkeypatch.setattr(of, "_git_stash_pop", lambda *a, **k: pytest.fail("should not pop"))

    async def generate(file_info, *_args, **_kwargs):
        (tmp_path / file_info["path"]).write_text("x", encoding="utf-8")
        return {"path": file_info["path"], "success": False}

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    with pytest.raises(RuntimeError):
        await orchestrator._generate_files_by_dep_layers(
            [{"path": "skip.py", "description": "d"}],
            {"architecture": {"language": "python"}},
            1,
            _Graph(),
        )

    assert not (tmp_path / "skip.py").exists()


@pytest.mark.asyncio
async def test_dep_layers_skips_falsey_results_when_successful(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["main.py"]]

    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)

    async def generate(*_args, **_kwargs):
        return {"path": "main.py", "success": True}

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)
    monkeypatch.setattr(
        of, "_git_stash_push", lambda *a, **k: True
    )

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        _Graph(),
    )

    assert orchestrator.generated_files == [{"path": "main.py", "success": True}]


@pytest.mark.asyncio
async def test_dep_layers_ignores_boolean_false_result_and_backs_up_existing(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    (tmp_path / "main.py").write_text("old\n", encoding="utf-8")

    class _Graph:
        def get_generation_layers(self):
            return [["main.py"]]

    captured = {}

    def stash_push(_dir, files, _message):
        captured["files"] = files
        return True

    monkeypatch.setattr(of, "_git_stash_push", stash_push)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)

    async def generate(*_args, **_kwargs):
        return False

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        _Graph(),
    )

    assert captured["files"] == ["main.py"]
    assert orchestrator.generated_files == []


@pytest.mark.asyncio
async def test_dep_layers_swallows_read_errors(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)

    class _Graph:
        def get_generation_layers(self):
            return [["main.py"]]

    monkeypatch.setattr(of, "_git_stash_push", lambda *a, **k: True)
    monkeypatch.setattr(of, "_git_stash_drop", lambda *a, **k: True)

    async def generate(*_args, **_kwargs):
        (tmp_path / "main.py").write_text("x", encoding="utf-8")
        return {"path": "main.py", "success": True}

    monkeypatch.setattr(orchestrator, "_generate_single_file", generate)
    real_read_text = of.Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == "main.py":
            raise OSError("locked")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(of.Path, "read_text", read_text)

    await orchestrator._generate_files_by_dep_layers(
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
        _Graph(),
    )

    assert "main.py" not in orchestrator._generated_contents


@pytest.mark.asyncio
async def test_single_file_correction_awaits_coroutine_response(
    tmp_path, monkeypatch, extract_passthrough
):
    orchestrator = _Orchestrator(tmp_path)
    responses = iter([
        "from utils import missing\n\ndef run():\n    return missing()\n",
        _async_value("from utils import foo\n\ndef run():\n    return foo()\n"),
    ])

    async def fake_generate(*_args, **_kwargs):
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师", clear_edits=lambda: None, generate_file=fake_generate
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("utils.py")
    graph.add_dependency("main.py", "utils.py")
    orchestrator.dependency_graph_obj = graph

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        2,
        {"utils.py": "def foo():\n    return 1\n"},
    )

    assert result["success"] is True


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_single_file_correction_revalidates_after_repair(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    responses = iter([
        "from utils import missing\n\ndef run():\n    return missing()\n",
        "from utils import foo\n\ndef run():\n    return foo()\n",
    ])

    async def fake_generate(*_args, **_kwargs):
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师", clear_edits=lambda: None, generate_file=fake_generate
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("utils.py")
    graph.add_dependency("main.py", "utils.py")
    orchestrator.dependency_graph_obj = graph

    real_symbol_repair = of._repair_python_project_symbol_imports
    calls = {"n": 0}

    def symbol_repair(content, errors, generated):
        calls["n"] += 1
        if calls["n"] <= 2:
            return real_symbol_repair(content, errors, generated)
        return content + "\n# settled\n"

    monkeypatch.setattr(of, "_repair_python_project_symbol_imports", symbol_repair)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        2,
        {"utils.py": "def foo():\n    return 1\n"},
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_post_correction_repair_triggers_revalidation(
    tmp_path, monkeypatch, extract_passthrough
):
    orchestrator = _Orchestrator(tmp_path)
    responses = iter([
        "from utils import missing\n\ndef run():\n    return missing()\n",
        "from utils import missing\n\ndef run():\n    return missing()\n",
    ])

    async def fake_generate(*_args, **_kwargs):
        return next(responses)

    engineer = types.SimpleNamespace(
        name="测试工程师", clear_edits=lambda: None, generate_file=fake_generate
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)
    graph = DependencyGraph()
    graph.add_file("main.py")
    graph.add_file("utils.py")
    graph.add_dependency("main.py", "utils.py")
    orchestrator.dependency_graph_obj = graph

    real_symbol_repair = of._repair_python_project_symbol_imports
    calls = {"n": 0}

    def symbol_repair(content, errors, generated):
        calls["n"] += 1
        repaired = real_symbol_repair(content, errors, generated)
        if calls["n"] >= 2:
            return repaired + "\n# post-correction repair\n"
        return repaired

    monkeypatch.setattr(of, "_repair_python_project_symbol_imports", symbol_repair)

    with pytest.raises(RuntimeError, match="跨文件导入不一致"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            2,
            {"utils.py": "def foo():\n    return 1\n"},
        )

    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_single_file_llm_caller_requires_detection_model(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.model_assignment = None

    async def extract_content(_content, _engineer, _output_dir, _file_path, **kwargs):
        await kwargs["llm_caller"]("is it python?")
        return "def main():\n    return 1\n"

    monkeypatch.setattr(of, "extract_engineer_content", extract_content)

    with pytest.raises(RuntimeError, match="model assignment is required for language detection"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            1,
        )


@pytest.mark.asyncio
async def test_single_file_llm_caller_uses_assigned_backend_model(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.model_assignment = types.SimpleNamespace(backend_model="backend-x")
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return "YES"

    monkeypatch.setattr(of, "call_llm", fake_call_llm)

    async def extract_content(_content, _engineer, _output_dir, _file_path, **kwargs):
        await kwargs["llm_caller"]("is it python?")
        return "def main():\n    return 1\n"

    monkeypatch.setattr(of, "extract_engineer_content", extract_content)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True
    assert captured["model"] == "backend-x"


@pytest.mark.asyncio
async def test_single_file_awaits_twice_when_first_await_returns_coroutine(
    tmp_path, monkeypatch, extract_passthrough
):
    orchestrator = _Orchestrator(tmp_path)

    async def inner():
        return "def main():\n    return 1\n"

    def generate(*_args, **_kwargs):
        async def middle():
            return inner()

        async def outer():
            return middle()

        return outer()

    engineer = types.SimpleNamespace(
        name="测试工程师", clear_edits=lambda: None, generate_file=generate
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_correction_exhausts_three_rounds(
    tmp_path, monkeypatch, extract_passthrough
):
    orchestrator = _Orchestrator(tmp_path)
    counter = {"n": 0}

    async def fake_generate(*_args, **_kwargs):
        counter["n"] += 1
        return (
            "def handle():\n"
            f"    return missing_{counter['n']}()\n"
        )

    engineer = types.SimpleNamespace(
        name="测试工程师", clear_edits=lambda: None, generate_file=fake_generate
    )
    monkeypatch.setattr(orchestrator, "_select_engineer", lambda _path: engineer)

    with pytest.raises(RuntimeError, match="跨文件导入不一致"):
        await orchestrator._generate_single_file(
            {"path": "main.py", "description": "entry"},
            {"architecture": {"language": "python"}},
            3,
        )

    assert counter["n"] == 4


@pytest.mark.asyncio
async def test_single_file_approval_granted_continues(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.require_approval = True

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_validation_success_continues_to_write(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_validation = True

    async def ok_validate(**_kwargs):
        return True, "def main():\n    return 1\n"

    monkeypatch.setattr(orchestrator, "_validate_and_review_file", ok_validate)

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_committer_without_completion_event_list(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.artifact_completion_events = None

    class _Committer:
        def commit(self, file_path, content, model_name):
            (tmp_path / file_path).write_text(content, encoding="utf-8")
            return types.SimpleNamespace(success=True, completion_event=object())

    orchestrator.artifact_committer = _Committer()

    result = await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_file_fix_history_non_matching_attempt_ignored(tmp_path, monkeypatch, extract_passthrough):
    orchestrator = _Orchestrator(tmp_path)
    recorded = []

    class _Learner:
        async def get_prevention_prompt(self, **_kwargs):
            return ""

        def record_fix(self, **kwargs):
            recorded.append(kwargs)

    orchestrator.feedback_learner = _Learner()
    orchestrator.error_recovery = types.SimpleNamespace(
        fix_history=[
            types.SimpleNamespace(
                file_path=str(tmp_path / "other.py"),
                error_message="x",
                fix_applied=True,
            )
        ]
    )

    await orchestrator._generate_single_file(
        {"path": "main.py", "description": "entry"},
        {"architecture": {"language": "python"}},
        1,
    )

    assert recorded == []


def test_normalize_file_path_keeps_dotted_parent(tmp_path):
    orchestrator = _Orchestrator(tmp_path)

    assert orchestrator._normalize_file_path("src.v2/py") == "src.v2/py"


@pytest.mark.asyncio
async def test_validate_and_review_medium_review_keeps_success(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_review = True
    orchestrator.reviewer = types.SimpleNamespace(
        review_code=AsyncMock(return_value={
            "needs_fix": False,
            "risk_level": "low",
            "issues": [],
        })
    )

    success, _content = await orchestrator._validate_and_review_file(
        "main.py", "def main():\n    return 1\n", "entry"
    )

    assert success is True


@pytest.mark.asyncio
async def test_validate_and_review_temp_file_unlink_failure_is_ignored(tmp_path, monkeypatch):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.enable_validation = True

    class _Validator:
        def get_cached_validation_by_key(self, _key):
            return None

        async def validate_single_file(self, _path):
            return {"is_valid": True}

        def store_validation(self, *_args):
            return None

    orchestrator.validator = _Validator()

    original_unlink = of.Path.unlink

    def failing_unlink(self, *args, **kwargs):
        raise OSError("busy")

    monkeypatch.setattr(of.Path, "unlink", failing_unlink)

    success, _content = await orchestrator._validate_and_review_file(
        "main.py", "def main():\n    return 1\n", "entry"
    )

    assert success is True


@pytest.mark.asyncio
async def test_patches_incremental_ignores_files_without_cross_dependencies(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    orchestrator.dependency_graph_obj = types.SimpleNamespace(
        get_affected_files=lambda _path: []
    )
    orchestrator.cross_file_patcher = types.SimpleNamespace(
        generate_cross_file_patches=AsyncMock()
    )

    async def generate(file_info, *_args, **_kwargs):
        return {"path": file_info["path"], "success": True}

    orchestrator._generate_single_file = generate

    await orchestrator._apply_patches_incremental(
        "change",
        [{"path": "main.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert orchestrator.generated_files == [{"path": "main.py", "success": True}]


@pytest.mark.asyncio
async def test_patches_incremental_reads_existing_dependency_contents(tmp_path):
    orchestrator = _Orchestrator(tmp_path)
    (tmp_path / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    captured = {}

    async def generate_cross_file_patches(**kwargs):
        captured.update(kwargs)
        return CrossFilePatchResult(
            primary_file="main.py",
            primary_result=PatchResult(
                success=True, file_path="main.py", original_content="",
                patched_content="", diff="", errors=[], warnings=[],
            ),
            dependency_chain={"main.py": ["helper.py"]},
        )

    orchestrator.dependency_graph_obj = types.SimpleNamespace(
        get_affected_files=lambda _path: ["helper.py"]
    )
    orchestrator.cross_file_patcher = types.SimpleNamespace(
        generate_cross_file_patches=generate_cross_file_patches
    )

    await orchestrator._apply_patches_incremental(
        "change",
        [{"path": "helper.py", "description": "d"}],
        {"architecture": {"language": "python"}},
        1,
    )

    assert captured["file_contents"]["helper.py"].startswith("def helper")
