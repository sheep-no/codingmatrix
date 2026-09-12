from app.agent.languages import get_language_adapter, get_language_capabilities
from app.agent.framework_profiles import DEFAULT_PROFILES
from app.agent.language_detector import LanguageDetector


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


def test_spring_boot_is_detected_as_java():
    result = LanguageDetector.detect("Create a CRUD API with Spring Boot and SQLite.")

    assert result.language == "java"
    assert result.backend_language == "java"


def test_explicit_language_wins_over_appended_context():
    result = LanguageDetector.detect(
        "Use java and spring-boot for this API."
        "\n\n[Available Skills]\nUse Python with FastAPI and Django."
    )

    assert result.language == "java"


def test_language_framework_prefix_wins_over_appended_context():
    result = LanguageDetector.detect(
        "Repair the existing java spring-boot CRUD project."
        "\n\n[Available Skills]\nUse Python with FastAPI and Django."
    )

    assert result.language == "java"


def test_negated_python_falls_back_to_go():
    result = LanguageDetector.detect("不要用 Python，用 Go 写一个 hello 程序")

    assert result.language == "go"


def test_java_spring_boot_profile_exposes_toolchain_commands():
    profile = DEFAULT_PROFILES.require("java", "spring-boot")

    assert profile.build_command == ("mvn", "-q", "-DskipTests", "package")
    assert profile.test_command == ("mvn", "-q", "test")


def test_go_adapter_exposes_imports_symbols_and_capabilities():
    adapter = get_language_adapter("go")
    imports = adapter.parse_imports('import (\n    "fmt"\n    "example.com/app/internal/store"\n)')
    definitions = adapter.extract_definitions("type Todo struct {}\nfunc ListTodos() []Todo {")
    capabilities = get_language_capabilities("go")

    assert [item.module for item in imports] == ["fmt", "example.com/app/internal/store"]
    assert set(definitions) == {"Todo", "ListTodos"}
    assert capabilities.extensions == (".go",)
    assert capabilities.supports_compile


def test_rust_adapter_exposes_modules_symbols_and_capabilities():
    adapter = get_language_adapter("rust")
    imports = adapter.parse_imports("use crate::store::TodoStore;\nmod routes;")
    definitions = adapter.extract_definitions("pub struct Todo {}\npub fn list_todos() {")
    capabilities = get_language_capabilities("rust")

    assert [item.module for item in imports] == ["crate::store::TodoStore", "routes"]
    assert set(definitions) == {"Todo", "list_todos"}
    assert capabilities.extensions == (".rs",)
    assert capabilities.supports_tests


def test_go_adapter_resolves_internal_packages_and_preserves_aliases():
    adapter = get_language_adapter("go")
    imports = adapter.parse_imports(
        'import (\n    store "example.com/demo/internal/store"\n    _ "example.com/demo/pkg/metrics"\n    "fmt"\n)'
    )

    assert [item.alias for item in imports] == ["store", "_", None]
    assert adapter.resolve_import_to_file(imports[0], "cmd/api/main.go") == [
        "internal/store/store.go", "internal/store.go",
    ]
    assert adapter.resolve_import_to_file(imports[2], "cmd/api/main.go") == []


def test_rust_adapter_resolves_crate_self_super_and_symbol_paths():
    adapter = get_language_adapter("rust")
    imports = adapter.parse_imports(
        "use crate::store::TodoStore;\nuse self::models;\nuse super::errors;\nmod routes;"
    )

    assert adapter.resolve_import_to_file(imports[0], "src/api/mod.rs") == [
        "src/store.rs", "src/store/mod.rs",
    ]
    assert adapter.resolve_import_to_file(imports[1], "src/api/mod.rs") == [
        "src/api/models.rs", "src/api/models/mod.rs",
    ]
    assert adapter.resolve_import_to_file(imports[2], "src/api/routes.rs") == [
        "src/errors.rs", "src/errors/mod.rs",
    ]
    assert adapter.resolve_import_to_file(imports[3], "src/api/mod.rs") == [
        "src/api/routes.rs", "src/api/routes/mod.rs",
    ]
