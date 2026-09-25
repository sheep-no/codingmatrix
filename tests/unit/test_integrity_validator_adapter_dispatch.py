"""IntegrityValidator 适配器推断回归（IV2：混合项目后端校验不再被前端 JS 切走）。"""

from app.agent.adapters import PythonLanguageAdapter
from app.agent.adapters.javascript import JavaScriptLanguageAdapter
from app.agent.adapters.go import GoLanguageAdapter
from app.agent.integrity_validator import IntegrityValidator


def _mixed_python_js_files():
    return {
        "app/main.py": (
            "from app.missing_module import x\n"
            "@app.get('/api/todo')\n"
            "def get_todo():\n"
            "    return {}\n"
        ),
        "app/__init__.py": "",
        "web/index.js": "fetch('/api/todo');\n",
    }


class TestAdapterDetection:
    def test_mixed_project_prefers_backend_language(self) -> None:
        validator = IntegrityValidator()  # 不传 adapter
        validator.validate(_mixed_python_js_files())

        assert isinstance(validator.language_adapter, PythonLanguageAdapter)

    def test_go_backend_wins_over_frontend_js(self) -> None:
        validator = IntegrityValidator()
        validator.validate({"main.go": "package main\n", "web/index.js": "console.log(1)\n"})

        assert isinstance(validator.language_adapter, GoLanguageAdapter)

    def test_js_only_project_keeps_javascript_adapter(self) -> None:
        validator = IntegrityValidator()
        validator.validate({"web/index.js": "console.log(1)\n"})

        assert isinstance(validator.language_adapter, JavaScriptLanguageAdapter)

    def test_explicit_adapter_is_not_overwritten_by_detection(self) -> None:
        explicit = PythonLanguageAdapter()
        validator = IntegrityValidator(language_adapter=explicit)
        validator.validate(_mixed_python_js_files())

        assert validator.language_adapter is explicit


class TestMixedProjectValidation:
    def test_backend_missing_import_is_reported(self) -> None:
        validator = IntegrityValidator()
        result = validator.validate(_mixed_python_js_files())

        missing = [i for i in result.issues if i.issue_type == "missing_module"]
        assert len(missing) == 1
        assert "app.missing_module" in missing[0].message

    def test_existing_backend_endpoint_is_not_reported_missing(self) -> None:
        validator = IntegrityValidator()
        result = validator.validate(_mixed_python_js_files())

        mismatches = [i for i in result.issues if i.issue_type == "api_mismatch"]
        assert mismatches == []

    def test_absent_backend_endpoint_is_still_reported(self) -> None:
        files = _mixed_python_js_files()
        files["web/index.js"] = "fetch('/api/nope');\n"

        validator = IntegrityValidator()
        result = validator.validate(files)

        mismatches = [i for i in result.issues if i.issue_type == "api_mismatch"]
        assert len(mismatches) == 1
        assert "/api/nope" in mismatches[0].message
