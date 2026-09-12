from app.agent.adapters import LanguageAdapterRegistry, PythonLanguageAdapter
from app.agent.adapters.boilerplate import scaffold_for_language


def test_python_scaffold_requirements_and_fastapi_entry():
    architecture = {
        "language": "python",
        "requirement": "工单系统 CRUD",
        "project_spec": {
            "default": {"framework": "FastAPI", "storage": {"type": "sqlite"}}
        },
        "file_plan": [
            {"path": "main.py", "file_type": "entry", "description": "入口"},
            {"path": "app/controllers/ticket_controller.py", "file_type": "api"},
            {"path": "tests/test_ticket.py", "file_type": "test"},
        ],
    }

    requirements = scaffold_for_language("python", "requirements.txt", "config", architecture)
    entry = scaffold_for_language("python", "main.py", "entry", architecture)
    readme = scaffold_for_language("python", "README.md", "docs", architecture)

    assert "fastapi" in requirements
    assert "sqlalchemy" in requirements
    assert "pytest" in requirements
    assert "include_router" in entry
    assert "ticket_controller" in entry
    assert "工单系统 CRUD" in readme


def test_registry_scaffold_file_uses_architecture_language():
    architecture = {
        "language": "javascript",
        "requirement": "Express API",
        "project_spec": {"default": {"framework": "Express"}},
        "file_plan": [{"path": "src/index.js", "file_type": "entry"}],
    }
    package_json = LanguageAdapterRegistry.scaffold_file(
        "package.json", "config", architecture
    )
    assert '"express"' in package_json
    adapter = PythonLanguageAdapter()
    assert adapter.scaffold_boilerplate("README.md", "docs", architecture).startswith("# Express API")


def test_python_entry_without_framework_is_not_scaffolded():
    content = scaffold_for_language(
        "python",
        "main.py",
        "entry",
        {"language": "python", "file_plan": [{"path": "main.py", "file_type": "entry"}]},
    )
    assert content is None


def test_python_config_module_is_not_scaffolded():
    content = scaffold_for_language(
        "python",
        "app/config.py",
        "config",
        {"language": "python", "project_spec": {"default": {"framework": "FastAPI"}}},
    )
    assert content is None


def test_python_entry_uses_canonical_file_plan_only():
    architecture = {
        "language": "python",
        "project_spec": {"default": {"framework": "FastAPI"}},
        "file_plan": [
            {"path": "main.py", "file_type": "entry"},
            {"path": "app/controllers/ticket_controller.py", "file_type": "api"},
        ],
        "files": [
            {"path": "src/routers/audit_router.py", "file_type": "api"},
        ],
    }
    entry = scaffold_for_language("python", "main.py", "entry", architecture)
    assert "app.controllers.ticket_controller" in entry
    assert "src.routers" not in entry


def test_python_scaffold_database_and_jwt_requirements():
    architecture = {
        "language": "python",
        "requirement": "工单系统",
        "project_spec": {
            "default": {
                "framework": "FastAPI",
                "storage": {"type": "sqlite", "filename": "tickets.db", "backend": "sqlalchemy"},
                "auth": {"scheme": "jwt_hs256"},
            }
        },
        "file_plan": [
            {"path": "app/database.py", "file_type": "database"},
            {"path": "tests/test_app.py", "file_type": "test"},
        ],
    }
    database = scaffold_for_language("python", "app/database.py", "database", architecture)
    requirements = scaffold_for_language("python", "requirements.txt", "config", architecture)
    readme = scaffold_for_language("python", "README.md", "docs", architecture)
    assert "declarative_base" in database
    assert "tickets.db" in database
    assert "sqlalchemy" in requirements
    assert "python-jose[cryptography]" in requirements
    assert "## Test" in readme


def test_python_test_without_frozen_routes_is_not_scaffolded():
    content = scaffold_for_language(
        "python",
        "tests/test_foo.py",
        "test",
        {"language": "python", "file_plan": [{"path": "tests/test_foo.py", "file_type": "test"}]},
    )
    assert content is None


def test_python_scaffold_frozen_ticket_tests():
    architecture = {
        "language": "python",
        "used_compact_eight_file_plan": True,
        "symbol_table": {
            "route_prefix": "",
            "files": {
                "tests/test_app.py": {
                    "routes": [
                        "POST /register",
                        "POST /login",
                        "POST /tickets",
                        "GET /tickets",
                        "POST /tickets/{ticket_id}/assign",
                        "POST /tickets/{ticket_id}/transition",
                        "POST /tickets/{ticket_id}/close",
                    ]
                }
            },
        },
        "file_plan": [{"path": "tests/test_app.py", "file_type": "test"}],
    }
    tests = scaffold_for_language("python", "tests/test_app.py", "test", architecture)
    assert tests is not None
    assert 'client.post("/register"' in tests
    assert 'client.post("/login"' in tests
    assert 'client.get("/tickets")' in tests
    assert "/tickets/" in tests
    assert "/api/v1" not in tests
    assert "def test_auth_failure" in tests
    assert "def test_unauthorized_access" in tests
    assert "def test_illegal_state_transition" in tests
    assert "def test_close_ticket" in tests


def test_compact_plan_scaffolds_test_app_without_symbol_table():
    tests = scaffold_for_language(
        "python",
        "tests/test_app.py",
        "test",
        {"language": "python", "used_compact_eight_file_plan": True},
    )
    assert tests is not None
    assert "def test_auth_failure" in tests
    assert "/api/v1" not in tests
