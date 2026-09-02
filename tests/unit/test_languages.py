from app.agent.languages import get_language_adapter, get_language_capabilities
from app.agent.framework_profiles import DEFAULT_PROFILES


def test_python_adapter_exposes_imports_and_symbols():
    adapter = get_language_adapter("python")
    imports = adapter.parse_imports("from app.models import User\n")
    definitions = adapter.extract_definitions("class User:\n    pass\n")

    assert imports[0].module == "app.models"
    assert imports[0].symbols == ["User"]
    assert definitions["User"].symbol_type == "class"


def test_typescript_alias_exposes_compile_and_test_capabilities():
    adapter = get_language_adapter("ts")
    capabilities = get_language_capabilities("typescript")

    assert adapter.language in {"javascript", "typescript"}
    assert capabilities.supports_compile
    assert capabilities.supports_tests
    assert ".ts" in capabilities.extensions


def test_builtin_profiles_cover_minimum_crud_stacks():
    for language, framework in (
        ("python", "fastapi"), ("python", "flask"),
        ("typescript", "express"), ("typescript", "nestjs"),
    ):
        profile = DEFAULT_PROFILES.require(language, framework)
        assert profile.install_command and profile.test_command and profile.start_command
