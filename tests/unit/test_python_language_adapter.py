from app.agent.adapters import PythonLanguageAdapter
from app.agent.integrity_validator import IntegrityValidator


PYTHON_APP_WITH_ASSETS = {
    "app/__init__.py": "",
    "app/main.py": "def run():\n    pass\n",
    "static/css/site.css": "body { color: red }\n",
    "templates/index.html": "<html></html>\n",
    "docs/README.md": "# docs\n",
}


def test_python_adapter_skips_entry_files_for_resource_directories() -> None:
    adapter = PythonLanguageAdapter()

    assert adapter.validate_package_structure("static", PYTHON_APP_WITH_ASSETS) == []
    assert adapter.validate_package_structure("static/css", PYTHON_APP_WITH_ASSETS) == []
    assert adapter.validate_package_structure("templates", PYTHON_APP_WITH_ASSETS) == []
    assert adapter.validate_package_structure("docs", PYTHON_APP_WITH_ASSETS) == []


def test_integrity_validation_accepts_python_app_with_resource_directories() -> None:
    result = IntegrityValidator(language_adapter=PythonLanguageAdapter()).validate(
        PYTHON_APP_WITH_ASSETS
    )

    assert result.passed
    assert result.issues == []
    assert result.missing_files == []


def test_python_adapter_still_requires_entry_for_source_packages() -> None:
    adapter = PythonLanguageAdapter()
    files = {"app/api/routes.py": "def route():\n    pass\n"}

    assert adapter.validate_package_structure("app", files) == ["app/__init__.py"]
    assert adapter.validate_package_structure("app/api", files) == ["app/api/__init__.py"]
    assert adapter.validate_package_structure("app/api", {"app/api/__init__.py": ""}) == []


def test_integrity_validation_generates_no_init_for_resource_directories() -> None:
    validator = IntegrityValidator(language_adapter=PythonLanguageAdapter())
    result = validator.validate(PYTHON_APP_WITH_ASSETS)

    assert validator.generate_fixes(result, PYTHON_APP_WITH_ASSETS) == {}
