"""Branch coverage for module-level helpers in orchestrator_files.

These tests pin the defensive branches that the large orchestration flows rely
on: syntax-error fallbacks, path inference, AST repairs and git-stash helpers.
"""

import ast
import types

import pytest

from app.agent import orchestrator_files as of


def test_python_defined_exports_reads_annotated_assignment_without_value():
    exports = of._python_defined_exports("x: int\nclass A:\n    pass\n")

    assert exports == {"x", "A"}


def test_structured_diagnostics_marks_database_abstraction_mismatch():
    diagnostics = of._structured_import_diagnostics([
        "database.py 同时使用 sqlite3 和 SQLAlchemy，必须统一为一种数据库抽象"
    ])

    assert diagnostics[0]["type"] == "static_validation_error"
    assert of._structured_import_diagnostics(["禁止混用 sqlite3 和 sqlalchemy"])[0]["type"] == (
        "database_abstraction_mismatch"
    )


def test_sqlalchemy_text_execute_returns_content_on_syntax_error():
    content = "def broken(:\n    db.execute('select 1')\n"

    assert of._repair_python_sqlalchemy_text_execute(content, "main.py") == content


def _route_module(body: str) -> str:
    return (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        f"{body}\n"
    )


def test_fastapi_route_registration_skips_syntax_error():
    content = "app.include_router(def broken(:)\n"

    assert of._repair_python_fastapi_class_route_registration(content, "main.py") == content


def test_fastapi_route_registration_skips_plain_router_argument():
    content = _route_module(
        "router = object()\n"
        "app.include_router(router)\n"
    )

    assert of._repair_python_fastapi_class_route_registration(content, "main.py") == content


def test_fastapi_route_registration_skips_non_route_list_items():
    content = _route_module(
        "app.include_router(FastAPI(prefix='/items', routes=[object()]))\n"
    )

    assert of._repair_python_fastapi_class_route_registration(content, "main.py") == content


def test_fastapi_route_registration_skips_when_handler_missing():
    content = _route_module(
        "app.include_router(FastAPI(routes=[FastAPI.post('/items')]))\n"
    )

    assert of._repair_python_fastapi_class_route_registration(content, "main.py") == content


def test_fastapi_route_registration_rewrites_matching_handlers():
    content = _route_module(
        "def create_item():\n"
        "    return 1\n"
        "def list_items():\n"
        "    return []\n"
        "def get_item():\n"
        "    return {}\n"
        "def update_item():\n"
        "    return {}\n"
        "def delete_item():\n"
        "    return {}\n"
        "app.include_router(FastAPI(prefix='/items', routes=[\n"
        "    FastAPI.post('/items', status_code=201),\n"
        "    FastAPI.get('/items'),\n"
        "    FastAPI.get('/items/{item_id}'),\n"
        "    FastAPI.put('/items/{item_id}'),\n"
        "    FastAPI.delete('/items/{item_id}'),\n"
        "]))\n"
    )

    repaired = of._repair_python_fastapi_class_route_registration(content, "main.py")

    assert "app.add_api_route('/items/items', create_item, methods=[\"POST\"], status_code=201)" in repaired
    assert "app.add_api_route('/items/items', list_items, methods=[\"GET\"])" in repaired
    assert "app.add_api_route('/items/items/{item_id}', get_item, methods=[\"GET\"])" in repaired


def test_invalid_code_marker_returns_non_python_content():
    content = "obj.__code__ = None\n"

    assert of._repair_python_invalid_code_marker(content, "main.js") == content


def test_unmounted_router_skips_syntax_error():
    content = "router = APIRouter(\n"

    assert of._repair_python_unmounted_fastapi_router(content, "main.py") == content


def test_unmounted_router_skips_when_no_named_router():
    content = "router = factory.APIRouter()\n"

    assert of._repair_python_unmounted_fastapi_router(content, "main.py") == content


def test_unmounted_router_appends_include_for_declared_router():
    content = "from fastapi import APIRouter\nrouter = APIRouter()\n"

    repaired = of._repair_python_unmounted_fastapi_router(content, "main.py")

    assert repaired.rstrip().endswith("app.include_router(router)")


def test_sqlalchemy_get_db_skips_syntax_error():
    architecture = {"file_plan": [{"path": "database.py", "file_type": "database"}]}
    content = "SessionLocal = None\ndef broken(:\n"

    assert of._repair_python_sqlalchemy_get_db(content, "database.py", architecture) == content


def test_project_call_keywords_skips_syntax_error():
    content = "def broken(:\n    create_todo(x=1)\n"
    errors = ["调用 create_todo 使用了未声明参数 x，请匹配 a.py 中的真实签名"]

    assert of._repair_python_project_call_keywords(content, errors) == content


def test_project_call_keywords_ignores_unrelated_calls_and_keeps_content():
    content = "def main():\n    other(x=1)\n    create_todo(y=2)\n"
    errors = ["调用 create_todo 使用了未声明参数 x，请匹配 a.py 中的真实签名"]

    assert of._repair_python_project_call_keywords(content, errors) == content


def test_project_call_keywords_keeps_declared_keywords():
    content = "def main():\n    create_todo(y=2)\n"
    errors = ["调用 create_todo 使用了未声明参数 x，请匹配 a.py 中的真实签名"]

    assert of._repair_python_project_call_keywords(content, errors) == content


def test_project_call_keywords_removes_rejected_keyword():
    content = "def main():\n    create_todo(title='a', bogus=1)\n"
    errors = ["调用 create_todo 使用了未声明参数 bogus，请匹配 a.py 中的真实签名"]

    assert "bogus" not in of._repair_python_project_call_keywords(content, errors)


def test_schema_field_repair_skips_syntax_error():
    content = "def broken(:\n    todo.missing\n"
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    assert of._repair_python_schema_field_access(content, errors) == content


def test_schema_field_repair_drops_guards_and_assignments():
    content = (
        "def handler(todo):\n"
        "    if todo.missing:\n"
        "        todo.missing = 1\n"
        "    value = todo.missing\n"
        "    result: int = todo.missing\n"
        "    return 1\n"
    )
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    repaired = of._repair_python_schema_field_access(content, errors)

    assert "missing" not in repaired
    compile(repaired, "main.py", "exec")


def test_schema_field_repair_inserts_pass_for_emptied_body():
    content = (
        "def handler(todo):\n"
        "    if todo.missing:\n"
        "        todo.missing = 1\n"
        "    return 2\n"
    )
    errors = ["main.py 访问 todo.missing，但 schema.py 的 Todo 未定义字段 missing"]

    repaired = of._repair_python_schema_field_access(content, errors)

    compile(repaired, "main.py", "exec")
    assert "missing" not in repaired


def test_project_symbol_imports_skips_non_python_dependency():
    content = "def f():\n    return 1\n"

    assert of._repair_python_project_symbol_imports(content, [], {"README.md": "x"}) == content


def test_project_symbol_imports_skips_invalid_dependency_syntax():
    content = "def f():\n    return 1\n"

    assert of._repair_python_project_symbol_imports(content, [], {"bad.py": "def (:"}) == content


def test_project_symbol_imports_returns_content_when_content_unparsable():
    content = "def broken(:\n    pass\n"
    errors = ["b.py 未导出符号 Foo，请使用其真实接口"]

    assert of._repair_python_project_symbol_imports(
        content, errors, {"a.py": "class Foo:\n    pass\n"}
    ) == content


def test_project_symbol_imports_ignores_import_from_without_module():
    content = "from . import helper\n"
    errors = ["b.py 未导出符号 Foo，请使用其真实接口"]

    repaired = of._repair_python_project_symbol_imports(
        content, errors, {"a.py": "class Foo:\n    pass\n"}
    )

    assert "from . import helper" in repaired


def test_project_symbol_imports_relocates_and_retains_aliases():
    content = "from a import Foo, Bar\n"
    generated = {"a.py": "class Bar:\n    pass\n", "b.py": "class Foo:\n    pass\n"}
    errors = ["a.py 未导出符号 Foo，请使用其真实接口"]

    repaired = of._repair_python_project_symbol_imports(content, errors, generated)

    assert "from b import Foo" in repaired
    assert "from a import Bar" in repaired


def test_project_symbol_imports_does_not_duplicate_existing_import():
    content = "from a import Foo\n\ndef use():\n    return Foo\n"
    errors = ["名称 Foo 在模块全局作用域中未定义或导入"]

    repaired = of._repair_python_project_symbol_imports(
        content, errors, {"a.py": "class Foo:\n    pass\n"}
    )

    assert repaired == content


def test_validate_implementation_skips_package_init():
    assert of._validate_python_implementation("", "pkg/__init__.py") == []


def test_validate_implementation_skips_syntax_error():
    assert of._validate_python_implementation("def (:", "main.py") == []


def test_validate_test_structure_skips_non_test_file():
    assert of._validate_python_test_structure("def (:", "main.py") == []


def test_validate_test_structure_skips_syntax_error():
    assert of._validate_python_test_structure("def (:", "test_main.py") == []


def test_validate_database_abstraction_skips_syntax_error():
    architecture = {"file_plan": [{"path": "database.py", "file_type": "database"}]}

    assert of._validate_python_database_abstraction(
        "def (:", "database.py", architecture
    ) == []


def test_file_matches_role_infers_from_path_without_architecture():
    assert of._file_matches_role("database.py", None, {"database"}) is True
    assert of._file_matches_role("models.py", None, {"model"}) is True
    assert of._file_matches_role("crud.py", None, {"repository"}) is True
    assert of._file_matches_role("main.py", None, {"entry"}) is True
    assert of._file_matches_role("unknown.xyz", None, {"entry"}) is False


def test_architecture_path_for_role_ignores_non_dict_plan_items():
    architecture = {"file_plan": ["junk", {"path": "db.py", "file_type": "database"}]}

    assert of._architecture_path_for_role(architecture, "database") == "db.py"


def _table_init_architecture(path: str = "main.py", role: str = "entry") -> dict:
    return {"file_plan": [{"path": path, "file_type": role}]}


def test_table_initialization_skips_single_file_syntax_error():
    content = (
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import declarative_base\n"
        "Base = declarative_base()\n"
        "engine = create_engine('sqlite:///x.db')\n"
        "def broken(:\n"
    )

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", {}, _table_init_architecture()
    ) == content


def test_table_initialization_keeps_existing_single_file_create_all():
    content = (
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import declarative_base\n"
        "Base = declarative_base()\n"
        "engine = create_engine('sqlite:///x.db')\n"
        "Base.metadata.create_all(bind=engine)\n"
    )

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", {}, _table_init_architecture()
    ) == content


def test_table_initialization_skips_syntax_error_with_database_dependency():
    content = "def broken(:\n    pass\n"
    generated = {"database.py": "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\nengine = object()\n"}

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, _table_init_architecture()
    ) == content


def test_table_initialization_skips_missing_database_exports():
    content = "def main():\n    return 1\n"
    generated = {"database.py": "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"}

    assert of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, _table_init_architecture()
    ) == content


def test_table_initialization_adds_bind_and_imports():
    content = (
        "from database import Base\n"
        "def main():\n"
        "    Base.metadata.create_all()\n"
    )
    generated = {
        "database.py": (
            "from sqlalchemy.orm import declarative_base\n"
            "Base = declarative_base()\n"
            "engine = object()\n"
        )
    }
    architecture = {
        "file_plan": [
            {"path": "main.py", "file_type": "entry"},
            {"path": "database.py", "file_type": "database"},
        ]
    }

    repaired = of._repair_python_sqlalchemy_table_initialization(
        content, "main.py", generated, architecture
    )

    assert "bind=engine" in repaired
    compile(repaired, "main.py", "exec")


def test_table_initialization_returns_unchanged_when_already_initialized():
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
        content, "main.py", generated, _table_init_architecture()
    ) == content


def test_test_fixtures_skip_syntax_error():
    content = "def test_x(:\n    create_all\nTestClient\n"

    assert of._repair_python_test_database_fixtures(content, "test_api.py", None) == content


def test_test_fixtures_return_unchanged_without_setup_fixture():
    content = (
        "import pytest\n"
        "from fastapi.testclient import TestClient\n"
        "@pytest.fixture\n"
        "def helper():\n"
        "    return create_all\n"
        "\n"
        "def test_x():\n"
        "    assert TestClient\n"
    )

    assert of._repair_python_test_database_fixtures(content, "test_api.py", None) == content


def test_declared_framework_roots_handles_non_dict_architecture():
    assert of._declared_python_framework_roots(None) == set()
    assert of._declared_python_framework_roots({"framework": "FastAPI"}) == {"fastapi"}


def test_python_contract_skips_syntax_error():
    architecture = {
        "file_plan": [{"path": "main.py", "file_type": "entry", "contract": {"role": "entry"}}]
    }

    assert of._validate_python_contract("def (:", "main.py", architecture) == []


def test_python_contract_accepts_string_forbidden_and_export_fields():
    architecture = {
        "file_plan": [{
            "path": "main.py",
            "file_type": "entry",
            "contract": {"role": "entry", "forbidden_imports": "sqlite3", "exports": "run"},
        }]
    }
    content = "import sqlite3\ndef run():\n    return 1\n"

    errors = of._validate_python_contract(content, "main.py", architecture)

    assert any("禁止导入模块 sqlite3" in error for error in errors)


def test_python_contract_skips_non_string_declared_exports():
    architecture = {
        "file_plan": [{
            "path": "main.py",
            "file_type": "config",
            "contract": {"role": "config", "exports": [123, "run"]},
        }]
    }
    content = "def run():\n    return 1\n"

    assert of._validate_python_contract(content, "main.py", architecture) == []


def test_python_contract_enforces_declared_database_abstraction():
    architecture = {
        "file_plan": [{
            "path": "database.py",
            "file_type": "database",
            "contract": {"role": "database", "database_abstraction": "sqlalchemy"},
        }]
    }
    content = "import sqlite3\n"

    errors = of._validate_python_contract(content, "database.py", architecture)

    assert any("未遵守架构契约声明的数据库抽象 sqlalchemy" in error for error in errors)


def test_pydantic_base_alias_is_replaced():
    content = "BasePydantic = type('BasePydantic', (Base,),)\n"

    assert of._repair_python_pydantic_base_alias(content, "schemas.py").strip() == (
        "BasePydantic = BaseModel"
    )


def _model_architecture(path: str = "models.py") -> dict:
    return {
        "file_plan": [
            {"path": "database.py", "file_type": "database"},
            {"path": path, "file_type": "model"},
        ]
    }


def test_shared_base_repair_returns_when_no_duplicate_base():
    generated = {"database.py": "Base = declarative_base()\n"}
    content = "from sqlalchemy import Column\nclass Todo:\n    pass\n"

    assert of._repair_python_shared_base(
        content, "models.py", generated, _model_architecture()
    ) == content


def test_shared_base_repair_returns_when_pattern_does_not_match():
    generated = {"database.py": "Base = declarative_base()\n"}
    content = "value = declarative_base\n"

    assert of._repair_python_shared_base(
        content, "models.py", generated, _model_architecture()
    ) == content


def test_invalid_metadata_owners_skips_non_python_and_syntax_error():
    assert of._invalid_sqlalchemy_metadata_owners("x", "main.js") == []
    assert of._invalid_sqlalchemy_metadata_owners("def (:", "main.py") == []


def test_schema_field_validation_skips_non_python_and_syntax_errors():
    generated = {"schemas.py": "class TodoCreate:\n    title: str\n"}
    errors = ["main.py 访问 todo.title，但 schemas.py 的 TodoCreate 未定义字段 title"]

    assert of._validate_python_schema_field_access("x", "main.js", generated) == []
    assert of._validate_python_schema_field_access("def (:", "main.py", generated) == []
    assert of._validate_python_schema_field_access(
        "def handler(todo: TodoCreate):\n    return todo.title\n",
        "main.py",
        {"README.md": "x", "bad.py": "def (:"},
    ) == []


def test_schema_field_validation_dedupes_repeated_attribute():
    content = (
        "def first(todo: TodoCreate):\n"
        "    return todo.missing\n"
        "def second(todo: TodoCreate):\n"
        "    return todo.missing\n"
    )
    generated = {"schemas.py": "class TodoCreate:\n    title: str\n"}

    errors = of._validate_python_schema_field_access(content, "main.py", generated)

    assert len(errors) == 1


def test_metadata_owner_repair_skips_invalid_database_source():
    content = "class Todo(Base):\n    pass\nTodo.Base.metadata.create_all()\n"

    assert of._repair_python_sqlalchemy_metadata_owner(
        content, "models.py", {"database.py": "def (:"}, _model_architecture()
    ) == content


def test_project_imports_skips_non_python_file():
    assert of._validate_python_project_imports("x", "main.js", {}, []) == []


def test_project_imports_reports_syntax_error():
    errors = of._validate_python_project_imports("def (:", "main.py", {}, [])

    assert errors and errors[0].startswith("Python 语法错误")


def test_project_imports_collects_global_assignments_from_children():
    content = (
        "def set_value():\n"
        "    global counter\n"
        "    counter = 1\n"
        "def read_value():\n"
        "    return counter\n"
    )

    assert of._validate_python_project_imports(content, "main.py", {}, []) == []


def test_project_imports_skips_invalid_generated_dependency_when_checking_base():
    content = "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"
    generated = {"bad.py": "def (:"}

    assert of._validate_python_project_imports(content, "main.py", generated, ["main.py", "bad.py"]) == []


def test_project_imports_rejects_ungenerated_project_module():
    errors = of._validate_python_project_imports(
        "import utils\n", "main.py", {}, ["main.py", "utils.py"]
    )

    assert any("尚未生成" in error for error in errors)


def test_project_imports_handles_find_spec_failures(monkeypatch):
    def boom(_name):
        raise ImportError("nope")

    monkeypatch.setattr(of.importlib.util, "find_spec", boom)

    import_errors = of._validate_python_project_imports("import unknown_mod\n", "main.py", {}, ["main.py"])
    from_errors = of._validate_python_project_imports(
        "from unknown_mod import thing\n", "main.py", {}, ["main.py"]
    )

    assert any("不在项目文件集合中" in error for error in import_errors)
    assert any("不在项目文件集合中" in error for error in from_errors)


def test_project_imports_rejects_unavailable_submodule(monkeypatch):
    def find_spec(name):
        return object() if name == "fakepkg" else None

    monkeypatch.setattr(of.importlib.util, "find_spec", find_spec)

    errors = of._validate_python_project_imports(
        "import fakepkg.missing\n", "main.py", {}, ["main.py"]
    )

    assert any("当前运行时不可导入" in error for error in errors)


def test_project_imports_rejects_unimportable_module():
    errors = of._validate_python_project_imports(
        "from xml.missing_thing import a\n", "main.py", {}, ["main.py"]
    )

    assert any("当前运行时不可导入" in error for error in errors)


def test_project_imports_skips_invalid_generated_module_exports(monkeypatch):
    content = "from utils import foo\n\ndef run():\n    return foo()\n"
    monkeypatch.setattr(of, "_python_exports", lambda _source: {"foo"})

    assert of._validate_python_project_imports(
        content, "main.py", {"utils.py": "def (:"}, ["main.py", "utils.py"]
    ) == []


def test_project_imports_skips_non_function_definition():
    content = "from utils import foo\n\ndef run():\n    return foo\n"

    assert of._validate_python_project_imports(
        content, "main.py", {"utils.py": "foo = 1\n"}, ["main.py", "utils.py"]
    ) == []


def test_project_imports_reports_missing_and_unexpected_arguments():
    content = "from utils import foo\n\ndef run():\n    return foo(1, extra=2)\n"
    generated = {"utils.py": "def foo(a, b):\n    return a + b\n"}

    errors = of._validate_python_project_imports(
        content, "main.py", generated, ["main.py", "utils.py"]
    )

    assert any("缺少必需参数 b" in error for error in errors)
    assert any("使用了未声明参数 extra" in error for error in errors)


def test_sync_async_repair_skips_syntax_errors():
    assert of._repair_python_sync_async_calls("def (:", {}) == "def (:"
    content = "from utils import run\n\ndef main():\n    return run()\n"
    assert of._repair_python_sync_async_calls(content, {"README.md": "x"}) == content
    assert of._repair_python_sync_async_calls(content, {"utils.py": "def (:"}) == content


def test_is_edit_marker_handles_all_shapes():
    assert of._is_edit_marker("") is False
    assert of._is_edit_marker('{"action": "edited"}') is True
    assert of._is_edit_marker("[1, 2]") is False
    assert of._is_edit_marker("not json") is False


def test_git_stash_push_returns_true_without_files(tmp_path):
    assert of._git_stash_push(str(tmp_path), []) is True


def test_git_stash_push_reports_success_and_failure(monkeypatch, tmp_path):
    calls = {}

    def run_ok(*_args, **_kwargs):
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(of.subprocess, "run", run_ok)
    assert of._git_stash_push(str(tmp_path), ["a.py"]) is True

    def run_fail(*_args, **_kwargs):
        return types.SimpleNamespace(returncode=1, stderr=" boom ")

    monkeypatch.setattr(of.subprocess, "run", run_fail)
    assert of._git_stash_push(str(tmp_path), ["a.py"]) is False

    def run_raise(*_args, **_kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(of.subprocess, "run", run_raise)
    assert of._git_stash_push(str(tmp_path), ["a.py"]) is False


def test_git_stash_pop_reports_success_and_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        of.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )
    assert of._git_stash_pop(str(tmp_path)) is True

    monkeypatch.setattr(
        of.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stderr="fail"),
    )
    assert of._git_stash_pop(str(tmp_path)) is False

    def run_raise(*_args, **_kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(of.subprocess, "run", run_raise)
    assert of._git_stash_pop(str(tmp_path)) is False


def test_git_stash_drop_reports_success_and_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        of.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )
    assert of._git_stash_drop(str(tmp_path)) is True

    monkeypatch.setattr(
        of.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stderr=""),
    )
    assert of._git_stash_drop(str(tmp_path)) is False

    def run_raise(*_args, **_kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(of.subprocess, "run", run_raise)
    assert of._git_stash_drop(str(tmp_path)) is False


def test_fix_absolute_imports_returns_non_python_content():
    content = "from src.utils import greet\n"

    assert of._fix_absolute_imports(content, "main.js", ["src/utils.py"]) == content


def test_fix_absolute_imports_normalizes_flat_relative_imports():
    content = "from . import main\nfrom . import missing\n"

    repaired = of._fix_absolute_imports(content, "runner.py", ["runner.py", "main.py"])

    assert "import main" in repaired
    assert "from . import missing" in repaired


def test_fix_absolute_imports_normalizes_flat_prefixed_imports():
    content = "from pkg.main import run\nfrom pkg.other import thing\n"

    repaired = of._fix_absolute_imports(content, "runner.py", ["runner.py", "main.py"])

    assert "from main import run" in repaired
    assert "from pkg.other import thing" in repaired


def test_fix_absolute_imports_rewrites_same_package_imports():
    content = "from src.utils.helpers import greet\nimport os\n"

    repaired = of._fix_absolute_imports(
        content, "src/utils/api.py", ["src/utils/api.py", "src/utils/helpers.py"]
    )

    assert "from .helpers import greet" in repaired
    assert "import os" in repaired


def test_fix_absolute_imports_keeps_imports_outside_current_package():
    content = "from src.other.helpers import greet\n"

    assert of._fix_absolute_imports(
        content, "src/utils/api.py", ["src/utils/api.py", "src/other/helpers.py"]
    ) == content


def test_format_review_issues_renders_non_dict_values():
    assert of._format_review_issues(["ok", 7]) == "ok; 7"
    assert of._format_review_issues({"message": "m"}) == "{'message': 'm'}"
    assert of._format_review_issues(None) == ""


def test_clean_code_block_delegates_to_utils():
    assert "def main" in of.FilesMixin._clean_code_block(None, "```python\ndef main():\n    pass\n```")


def test_select_engineer_for_model_routes_frontend_models():
    orchestrator = types.SimpleNamespace(frontend_engineer="fe", backend_engineer="be")

    assert of.FilesMixin._select_engineer_for_model(
        orchestrator, of.DEFAULT_FAST_MODEL
    ) == "fe"
    assert of.FilesMixin._select_engineer_for_model(orchestrator, "other-model") == "be"
