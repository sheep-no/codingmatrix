"""BackendEngineer 约束构建与生成分支。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.backend_engineer import BackendEngineer


def _engineer():
    return BackendEngineer(
        role_name="backend",
        model_name="test-model",
        task_type="generate",
    )


@pytest.mark.asyncio
async def test_system_prompt_prefers_skill_registry(monkeypatch):
    monkeypatch.setattr(
        "app.services.skill_registry.get_skill",
        lambda name: "custom backend prompt",
    )
    assert _engineer().SYSTEM_PROMPT == "custom backend prompt"


@pytest.mark.asyncio
async def test_system_prompt_falls_back_when_loader_returns_none(monkeypatch):
    def _missing(_name):
        raise RuntimeError("registry down")

    monkeypatch.setattr("app.services.skill_registry.get_skill", _missing)
    monkeypatch.setattr("app.agent.backend_engineer.load_backend_engineer_prompt", lambda: None)
    prompt = _engineer().SYSTEM_PROMPT
    assert "世界级后端工程师" in prompt


@pytest.mark.asyncio
async def test_system_prompt_returns_loaded_prompt(monkeypatch):
    def _missing(_name):
        return None

    monkeypatch.setattr("app.services.skill_registry.get_skill", _missing)
    monkeypatch.setattr("app.agent.backend_engineer.load_backend_engineer_prompt", lambda: "loaded prompt")
    assert _engineer().SYSTEM_PROMPT == "loaded prompt"


@pytest.mark.parametrize(
    "path, expected",
    [
        ("app/repository/user_repo.py", "repository"),
        ("app/dao/orders.py", "repository"),
        ("app/crud.py", "repository"),
        ("app/crud/user.py", "repository"),
        ("app/schemas/user.py", "schema"),
        ("app/dto/user.py", "schema"),
        ("app/database/engine.py", "database"),
        ("app/db.py", "database"),
        ("app/config.py", "config"),
        ("app/settings.py", "config"),
        ("app/middleware/auth.py", "middleware"),
        ("app/utils/helpers.py", "utils"),
        ("app/main.py", "entry"),
        ("app/index.py", "entry"),
        ("README.md", "unknown"),
    ],
)
def test_infer_file_type_additional_mappings(path, expected):
    assert BackendEngineer._infer_file_type_from_path(path) == expected


def test_spec_constraints_empty_spec_returns_empty():
    assert BackendEngineer._build_spec_constraints("api", {}) == ""


def test_spec_constraints_covers_framework_storage_and_terminology():
    spec = {
        "framework": "FastAPI",
        "storage": {"type": "localStorage", "filename": "data.json"},
        "terminology": {"todo": "task"},
    }

    text = BackendEngineer._build_spec_constraints("api", spec)

    assert "FastAPI" in text
    assert "localStorage" in text
    assert "data.json" in text
    assert "todo -> task" in text


def test_spec_constraints_with_plain_storage_without_filename():
    text = BackendEngineer._build_spec_constraints("api", {"storage": {"type": "sqlite"}})
    assert "sqlite" in text
    assert "存储文件" not in text


def test_file_scope_constraints_empty_plan_returns_empty():
    assert BackendEngineer._build_file_scope_constraints("app/main.py", {}) == ""


def test_file_scope_constraints_include_import_style():
    architecture = {"file_plan": [{"path": "app/main.py"}, {"path": "app/models.py"}, {"bad": "x"}]}
    nested = BackendEngineer._build_file_scope_constraints("app/api/users.py", architecture)
    flat = BackendEngineer._build_file_scope_constraints("models.py", architecture)

    assert "相对导入" in nested
    assert "app/main.py" in nested
    assert "顶层绝对导入" in flat


def test_get_file_contract_handles_backslashes_and_non_dict_contract():
    architecture = {
        "file_plan": [
            {"path": "app\\api\\users.py", "contract": {"role": "api"}},
            {"path": "app/service.py", "contract": "bad"},
            {"path": "app/other.py", "contract": {"role": "x"}},
        ]
    }

    assert BackendEngineer._get_file_contract("app/api/users.py", architecture) == {"role": "api"}
    assert BackendEngineer._get_file_contract("app/service.py", architecture) == {}
    assert BackendEngineer._get_file_contract("app/missing.py", architecture) == {}


def test_contract_constraints_without_contract_returns_empty():
    assert BackendEngineer._build_contract_constraints("app/main.py", {"file_plan": []}) == ""


def test_contract_constraints_renders_scalar_and_list_fields():
    architecture = {
        "file_plan": [{
            "path": "app/repository/user.py",
            "contract": {
                "role": "repository",
                "runtime": "async",
                "database_abstraction": "sqlalchemy",
                "exports": "get_user",
                "required_imports": ["from app.db import SessionLocal"],
                "forbidden_imports": "sqlite3",
                "shared_symbols": ["User"],
                "notes": "keep it stable",
            },
        }]
    }

    text = BackendEngineer._build_contract_constraints("app/repository/user.py", architecture)

    assert "职责: repository" in text
    assert "运行时: async" in text
    assert "数据库抽象: sqlalchemy" in text
    assert "必须导出的公共符号: get_user" in text
    assert "禁止导入: sqlite3" in text
    assert "补充约束: keep it stable" in text


def test_contract_constraints_uses_symbol_table_signatures_routes_and_storage():
    architecture = {
        "file_plan": [{"path": "app/api/users.py", "contract": {}}],
        "symbol_table": {
            "files": {
                "app/api/users.py": {
                    "signatures": {"list_users": "def list_users() -> list[User]"},
                    "routes": ["GET /users"],
                }
            },
            "storage": {"backend": "sqlite"},
            "auth": {"scheme": "jwt"},
        },
    }

    text = BackendEngineer._build_contract_constraints("app/api/users.py", architecture)

    assert "必须按冻结签名实现" in text
    assert "GET /users" in text
    assert "唯一存储后端: sqlite" in text
    assert "鉴权方案: jwt" in text


def test_contract_constraints_uses_provides_when_no_signatures():
    architecture = {
        "file_plan": [{"path": "app/service/user.py", "contract": {}}],
        "symbol_table": {
            "files": {
                "app/service/user.py": {
                    "provides": "create_user",
                    "routes": "POST /users",
                }
            },
            "storage": "not-a-dict",
            "auth": "not-a-dict",
        },
    }

    text = BackendEngineer._build_contract_constraints("app/service/user.py", architecture)

    assert "必须实现的公共符号: create_user" in text
    assert "POST /users" in text


def test_contract_constraints_ignores_malformed_symbol_table_entries():
    architecture = {
        "file_plan": [{"path": "app/api/users.py", "contract": {}}],
        "symbol_table": {
            "files": {"app/api/users.py": "not-a-dict"},
            "storage": {},
        },
    }

    assert BackendEngineer._build_contract_constraints("app/api/users.py", architecture) == ""


def test_runtime_constraints_skip_non_python_projects():
    assert BackendEngineer._build_runtime_consistency_constraints(
        "go/main.go", "entry", "go", {"file_plan": []}
    ) == ""


@pytest.mark.parametrize(
    "file_type",
    ["repository", "model", "schema", "database", "entry", "test"],
)
def test_runtime_constraints_include_sections_per_file_type(file_type):
    architecture = {
        "framework": "fastapi",
        "file_plan": [
            {"path": "database.py", "file_type": "database"},
            {"path": "models.py", "file_type": "model"},
            {"path": "app/repository.py", "file_type": "repository", "contract": {"exports": ["create"]}},
            {"path": "test_main.py", "file_type": "test"},
        ],
        "project_spec": {"framework": "fastapi"},
    }

    text = BackendEngineer._build_runtime_consistency_constraints(
        "app/repository.py", file_type, "python", architecture
    )

    assert "Python 运行时一致性" in text


def test_runtime_constraints_repository_without_contract_exports():
    architecture = {"file_plan": [{"path": "app/repository.py"}]}
    text = BackendEngineer._build_runtime_consistency_constraints(
        "app/repository.py", "repository", "python", architecture
    )
    assert "仓储公共函数" not in text


def test_runtime_constraints_model_uses_declared_database_path():
    architecture = {
        "file_plan": [
            {"path": "app/db/session.py", "file_type": "database"},
            {"path": "app/models/user.py", "file_type": "model"},
        ]
    }
    text = BackendEngineer._build_runtime_consistency_constraints(
        "app/models/user.py", "model", "python", architecture
    )
    assert "from app.db.session import Base" in text


def test_runtime_constraints_entry_without_route_modules_and_with_database():
    architecture = {
        "file_plan": [
            {"path": "main.py", "file_type": "entry"},
            {"path": "database.py", "file_type": "database"},
        ]
    }
    text = BackendEngineer._build_runtime_consistency_constraints(
        "main.py", "entry", "python", architecture
    )
    assert "所有 API 路由必须直接定义在 main.py" in text
    assert "必须从 database.py 显式导入" in text


def test_runtime_constraints_entry_with_repository_and_route_modules():
    architecture = {
        "file_plan": [
            {"path": "main.py", "file_type": "entry"},
            {"path": "repository.py", "file_type": "repository"},
            {"path": "routes/users.py", "file_type": "api"},
        ]
    }
    text = BackendEngineer._build_runtime_consistency_constraints(
        "main.py", "entry", "python", architecture
    )
    assert "必须显式导入架构声明的仓储文件" in text
    assert "所有 API 路由必须直接定义在 main.py" not in text


def test_runtime_constraints_framework_falls_back_to_project_spec():
    architecture = {
        "project_spec": {"framework": "fastapi"},
        "file_plan": [
            {"path": "database.py", "file_type": "database"},
            {"path": "models.py", "file_type": "model"},
        ],
    }
    text = BackendEngineer._build_runtime_consistency_constraints(
        "database.py", "database", "python", architecture
    )
    assert "SQLAlchemy" in text


def test_runtime_constraints_test_file_uses_httpx_rules():
    architecture = {"framework": "fastapi", "file_plan": [{"path": "test_main.py", "file_type": "test"}]}
    text = BackendEngineer._build_runtime_consistency_constraints(
        "test_main.py", "test", "python", architecture
    )
    assert "ASGITransport" in text


def test_dependency_import_constraints_without_dependencies():
    text = BackendEngineer._build_dependency_import_constraints("")
    assert "禁止导入任何其他项目文件" in text


def test_dependency_import_constraints_lists_dependencies():
    dep = "## 依赖文件: app/database.py\ncode\n## 依赖文件: app/models.py\ncode"
    text = BackendEngineer._build_dependency_import_constraints(dep)
    assert "app/database.py" in text
    assert "app/models.py" in text


def test_interface_constraints_without_signatures_returns_empty():
    assert BackendEngineer._build_interface_constraints("no dependencies here") == ""


def test_interface_constraints_extracts_signatures():
    dep = "## 依赖文件: app/models.py\nclass User:\n    pass\ndef get_user() -> User:\n    pass\n"
    text = BackendEngineer._build_interface_constraints(dep)
    assert "app/models.py" in text
    assert "class User" in text
    assert "def get_user" in text


@pytest.mark.asyncio
async def test_generate_file_returns_scaffold_and_skips_llm(monkeypatch):
    engineer = _engineer()
    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.scaffold_file",
        lambda file_path, file_type, architecture: "scaffold content",
    )
    engineer.call_llm = AsyncMock(return_value="llm content")

    result = await engineer.generate_file(
        "app/api/users.py",
        "users api",
        {"architecture": {"language": "python"}},
    )

    assert result == "scaffold content"
    engineer.call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_generate_file_react_path_preverifies_symbols(monkeypatch):
    engineer = _engineer()
    engineer.call_llm_with_tools = AsyncMock(return_value="generated")
    engineer.call_llm = AsyncMock(return_value="plain")
    read_symbols = MagicMock(return_value={"success": True})
    tools = {
        "read_symbols": {"fn": read_symbols},
        "read_file": {"fn": MagicMock()},
        "write_file": {"fn": MagicMock()},
    }
    monkeypatch.setattr("app.agent.tools.SPECIALIST_TOOLS", tools)

    result = await engineer.generate_file(
        "app/api/users.py",
        "users",
        {"architecture": {"language": "python"}, "requirement": "build"},
        dep_context="## 依赖文件: app/models.py\ncode",
        project_path="/tmp/project",
    )

    assert result == "generated"
    read_symbols.assert_called_once()
    kwargs = engineer.call_llm_with_tools.await_args.kwargs
    assert kwargs["preverified_tool_names"] == {"read_symbols"}
    assert kwargs["required_tool_names"] == set()
    assert "write_file" not in kwargs["tools"]


@pytest.mark.asyncio
async def test_generate_file_react_path_requires_tool_when_preverification_fails(monkeypatch):
    engineer = _engineer()
    engineer.call_llm_with_tools = AsyncMock(return_value="generated")
    tools = {"read_symbols": {"fn": MagicMock(side_effect=RuntimeError("boom"))}}
    monkeypatch.setattr("app.agent.tools.SPECIALIST_TOOLS", tools)

    await engineer.generate_file(
        "app/api/users.py",
        "users",
        {"architecture": {"language": "python"}},
        dep_context="## 依赖文件: app/models.py\ncode",
        project_path="/tmp/project",
    )

    kwargs = engineer.call_llm_with_tools.await_args.kwargs
    assert kwargs["required_tool_names"] == {"read_symbols"}
    assert kwargs["preverified_tool_names"] == set()


@pytest.mark.asyncio
async def test_generate_file_uses_plain_llm_without_project_path():
    engineer = _engineer()
    engineer.call_llm = AsyncMock(return_value="plain")
    engineer.call_llm_with_tools = AsyncMock(return_value="tool")

    result = await engineer.generate_file(
        "app/api/users.py", "users", {"architecture": {"language": "python"}}
    )

    assert result == "plain"
    engineer.call_llm_with_tools.assert_not_called()


@pytest.mark.asyncio
async def test_generate_file_uses_plain_llm_with_frozen_contract():
    engineer = _engineer()
    engineer.call_llm = AsyncMock(return_value="plain")
    engineer.call_llm_with_tools = AsyncMock(return_value="tool")

    result = await engineer.generate_file(
        "app/api/users.py",
        "users",
        {
            "architecture": {"language": "python"},
            "generation_contract": {"frozen": True},
            "requirement": "build",
        },
        project_path="/tmp/project",
    )

    assert result == "plain"
    engineer.call_llm_with_tools.assert_not_called()


@pytest.mark.asyncio
async def test_generate_file_modification_path_and_heartbeat(monkeypatch):
    engineer = _engineer()
    captured = {}

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "modified"

    engineer.call_llm = _capture
    tracker = MagicMock()

    result = await engineer.generate_file(
        "app/api/users.py",
        "users",
        {
            "architecture": {"language": "python"},
            "project_spec": {
                "api": {
                    "framework": "FastAPI",
                    "storage": {"type": "sqlite"},
                    "terminology": {"user": "account"},
                }
            },
            "original_content": "old code",
            "modification_reason": "fix bug",
        },
        is_existing_file=True,
        spec_context="spec body",
        dep_context="## 依赖文件: app/models.py\ncode",
        heartbeat_tracker=tracker,
    )

    assert result == "modified"
    assert tracker.touch.call_count == 2
    assert "fix bug" in captured["prompt"]
    assert "old code" in captured["prompt"]
    assert "spec body" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_file_infers_file_type_and_adds_framework_guard(monkeypatch):
    engineer = _engineer()
    captured = {}
    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.scaffold_file",
        lambda file_path, file_type, architecture: None,
    )

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "generated"

    engineer.call_llm = _capture

    await engineer.generate_file(
        "app/api/users.py",
        "users api",
        {"architecture": {"language": "python", "file_plan": []}, "requirement": "build"},
    )

    assert "框架选择约束" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_file_model_with_sqlite_database_dependency():
    engineer = _engineer()
    captured = {}

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "generated"

    engineer.call_llm = _capture

    await engineer.generate_file(
        "models.py",
        "models",
        {"architecture": {"language": "python", "file_plan": []}},
        dep_context="## 依赖文件: database.py\nimport sqlite3\n",
    )

    assert "必须继续使用原生 sqlite3" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_file_model_with_sqlalchemy_base_dependency():
    engineer = _engineer()
    captured = {}

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "generated"

    engineer.call_llm = _capture

    await engineer.generate_file(
        "models.py",
        "models",
        {"architecture": {"language": "python", "file_plan": []}},
        dep_context="## 依赖文件: database.py\nBase = declarative_base()\n",
    )

    assert "已导出 SQLAlchemy Base" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_file_init_file_exploration_prompt():
    engineer = _engineer()
    captured = {}

    async def _capture(prompt, system_prompt):
        captured["prompt"] = prompt
        return "generated"

    engineer.call_llm = _capture

    await engineer.generate_file(
        "app/utils/__init__.py",
        "package entry",
        {"architecture": {"language": "python", "file_plan": []}},
    )

    assert "这是一个包入口文件" in captured["prompt"]


@pytest.mark.asyncio
async def test_analyze_without_project_context_or_project_path(monkeypatch):
    engineer = _engineer()
    engineer.call_llm = AsyncMock(return_value="analysis")

    result = await engineer.analyze("what?", "")

    assert result == "analysis"


@pytest.mark.asyncio
async def test_analyze_swallows_list_files_failure(monkeypatch):
    engineer = _engineer()
    engineer.call_llm = AsyncMock(return_value="analysis")
    tools = {"list_files": {"fn": MagicMock(side_effect=RuntimeError("boom"))}}
    monkeypatch.setattr("app.agent.tools.SPECIALIST_TOOLS", tools)
    tracker = MagicMock()

    result = await engineer.analyze(
        "what?",
        "/tmp/project",
        project_context={"architecture": {"language": "python"}},
        heartbeat_tracker=tracker,
    )

    assert result == "analysis"
    assert tracker.touch.call_count == 2
