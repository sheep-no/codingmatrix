from app.agent.adapters import JavaLanguageAdapter
import asyncio

from app.agent.cross_validator import CrossValidator
from app.agent.integrity_validator import IntegrityValidator


def test_java_adapter_parses_imports_and_symbols() -> None:
    adapter = JavaLanguageAdapter()
    content = """
package com.example;
import com.example.Todo;
import java.util.List;
public class TodoController {
    public Todo getTodo() { return null; }
}
"""

    imports = adapter.parse_imports(content)
    definitions = adapter.extract_definitions(content)

    assert [item.module for item in imports] == ["com.example.Todo", "java.util.List"]
    assert adapter.resolve_import_to_file(imports[0], "src/main/java/com/example/TodoController.java") == [
        "src/main/java/com/example/Todo.java",
        "src/test/java/com/example/Todo.java",
        "com/example/Todo.java",
    ]
    assert adapter.resolve_import_to_file(imports[1], "TodoController.java") == []
    assert definitions["TodoController"].symbol_type == "class"
    assert definitions["getTodo"].symbol_type == "function"


def test_java_adapter_maps_java_files() -> None:
    adapter = JavaLanguageAdapter()

    assert adapter.infer_file_type("src/main/java/com/example/Todo.java") == "source"
    assert adapter.is_project_module("com.example.Todo")
    assert not adapter.is_project_module("org.springframework.web.bind.annotation.GetMapping")
    assert adapter.is_known_external_module("org.springframework.web.bind.annotation.GetMapping")
    assert adapter.is_known_external_module("java.util.List")
    assert not adapter.is_known_external_module("com.example.Todo")


def test_java_adapter_treats_mockito_static_imports_as_external() -> None:
    adapter = JavaLanguageAdapter()
    content = """
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.when;
"""

    imports = adapter.parse_imports(content)

    assert [item.module for item in imports] == [
        "org.mockito.ArgumentMatchers.anyString",
        "org.mockito.ArgumentMatchers.any",
        "org.mockito.ArgumentMatchers.anyLong",
        "org.mockito.Mockito.when",
    ]
    assert all(not adapter.is_project_module(item.module) for item in imports)
    assert all(adapter.resolve_import_to_file(item, "TodoControllerTest.java") == [] for item in imports)


def test_java_cross_validator_skips_generic_symbol_scanning() -> None:
    files = {
        "pom.xml": "<project><properties /></project>",
        "src/test/java/com/example/TodoTest.java": """
package com.example;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
class TodoTest { void test() { when(service.find(anyString())).thenReturn(null); } }
""",
    }

    issues = asyncio.run(
        CrossValidator(None, language_adapter=JavaLanguageAdapter())
        .validate_cross_file_consistency(files, {})
    )

    assert issues == []


def test_java_adapter_resolves_maven_source_layout_for_integrity_validation() -> None:
    adapter = JavaLanguageAdapter()
    files = {
        "src/main/java/com/example/Todo.java": "package com.example; public class Todo {}",
        "src/main/java/com/example/TodoController.java": (
            "package com.example;\n"
            "import com.example.Todo;\n"
            "import org.springframework.web.bind.annotation.RestController;\n"
            "public class TodoController { Todo todo; }"
        ),
    }

    result = IntegrityValidator(language_adapter=adapter).validate(files)

    assert result.passed
    assert result.issues == []
