from app.agent.adapters import JavaScriptLanguageAdapter
from app.agent.integrity_validator import IntegrityValidator


REACT_PROJECT = {
    "src/App.tsx": "export default function App() { return null }\n",
    "src/components/Button.tsx": "export function Button() { return null }\n",
    "src/hooks/useAuth.ts": "export function useAuth() { return null }\n",
    "src/api/client.ts": "export const client = {}\n",
}


def test_javascript_adapter_does_not_require_directory_index_files() -> None:
    adapter = JavaScriptLanguageAdapter()

    assert adapter.validate_package_structure("src", REACT_PROJECT) == []
    assert adapter.validate_package_structure("src/components", REACT_PROJECT) == []
    assert adapter.get_required_package_files("src/components") == []


def test_integrity_validation_accepts_standard_react_layout() -> None:
    result = IntegrityValidator(language_adapter=JavaScriptLanguageAdapter()).validate(
        REACT_PROJECT
    )

    assert result.passed
    assert result.issues == []
    assert result.missing_files == []


def test_integrity_validation_generates_no_index_barrel_fixes() -> None:
    validator = IntegrityValidator(language_adapter=JavaScriptLanguageAdapter())
    result = validator.validate(REACT_PROJECT)

    assert validator.generate_fixes(result, REACT_PROJECT) == {}


def test_integrity_validation_still_requires_python_package_init() -> None:
    from app.agent.adapters import PythonLanguageAdapter

    files = {
        "app/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n",
        "app/routers/users.py": "from fastapi import APIRouter\n\nrouter = APIRouter()\n",
    }
    result = IntegrityValidator(language_adapter=PythonLanguageAdapter()).validate(files)

    assert not result.passed
    assert set(result.missing_files) == {"app/__init__.py", "app/routers/__init__.py"}
