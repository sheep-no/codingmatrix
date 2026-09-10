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
        "file_plan": [{"path": "src/index.js", "file_type": "entry"}],
    }
    package_json = LanguageAdapterRegistry.scaffold_file(
        "package.json", "config", architecture
    )
    assert '"express"' in package_json
    adapter = PythonLanguageAdapter()
    assert adapter.scaffold_boilerplate("README.md", "docs", architecture).startswith("# Express API")


def test_python_config_module_is_not_scaffolded():
    content = scaffold_for_language(
        "python",
        "app/config.py",
        "config",
        {"language": "python", "project_spec": {"default": {"framework": "FastAPI"}}},
    )
    assert content is None
