"""signature_extractor 预算、兜底与字段识别的分支补测。"""

from app.agent.signature_extractor import (
    _is_class_field,
    _line_signature,
    extract_signatures,
    get_context_budget,
)


def test_context_budget_tiers():
    assert get_context_budget(1000) == 3000
    assert get_context_budget(32768) == 3000
    assert get_context_budget(40000) == 5000
    assert get_context_budget(65536) == 5000
    assert get_context_budget(100000) == 8000
    assert get_context_budget(1000000) == 15000


def test_line_signature_without_parenthesis_returns_stripped_text():
    assert _line_signature("  const value = 1  ") == "const value = 1"


def test_line_signature_with_unbalanced_parenthesis_is_clipped():
    assert _line_signature("function broken(a, b") == "function broken(a, b"


def test_line_signature_matches_nested_parentheses():
    assert _line_signature("function outer(call(inner)) {}") == "function outer(call(inner))"
    assert _line_signature("function outer(a, b") == "function outer(a, b"


def test_python_syntax_error_falls_back_to_generic_definition_match():
    signatures = extract_signatures("broken.py", "def broken(:\n")
    assert signatures is not None
    assert "def broken" in signatures


def test_python_file_without_signatures_returns_none():
    assert extract_signatures("constants.py", "X = 1\nY = 2\n") is None


def test_jsx_and_tsx_extensions_use_js_ts_patterns():
    jsx = "function Widget() {\n  return null;\n}\n"
    tsx = "function Panel(): void {\n  return;\n}\n"

    jsx_sig = extract_signatures("Widget.jsx", jsx)
    tsx_sig = extract_signatures("Panel.tsx", tsx)

    assert jsx_sig is not None and "function Widget(" in jsx_sig
    assert tsx_sig is not None and "function Panel" in tsx_sig


def test_decorator_inside_js_class_body_is_collected():
    content = (
        "class Service {\n"
        "  @Component\n"
        "  name() {}\n"
        "}\n"
    )
    signatures = extract_signatures("service.js", content)

    assert signatures is not None
    assert "@Component" in signatures
    assert "name()" in signatures


def test_unknown_language_falls_back_to_generic_imports_and_defs():
    content = (
        "// comment\n"
        "import Foo from bar\n"
        "module Thing {\n"
    )
    signatures = extract_signatures("thing.xyz", content)

    assert signatures is not None
    assert "import Foo from bar" in signatures
    assert "module Thing" in signatures


def test_unknown_language_without_recognizable_lines_returns_none():
    assert extract_signatures("empty.xyz", "just some prose\n") is None


def test_generic_fallback_truncates_definition_at_separator():
    signatures = extract_signatures("thing.xyz", "class Foo: pass\n")
    assert signatures is not None
    assert signatures.strip() == "class Foo"


def test_generic_fallback_keeps_definition_without_separator():
    signatures = extract_signatures("thing.xyz", "class Foo\n")
    assert signatures is not None
    assert signatures.strip() == "class Foo"


def test_extract_signatures_swallows_unexpected_errors(monkeypatch):
    import app.agent.signature_extractor as module

    def boom(content):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "_extract_python_signatures", boom)
    assert module.extract_signatures("item.py", "x = 1") is None


def test_python_class_fields_and_methods_via_ast():
    content = (
        "class Item:\n"
        "    amount: float\n"
        "    def total(self) -> float:\n"
        "        return self.amount\n"
        "\n"
        "async def load() -> None:\n"
        "    return None\n"
    )
    signatures = extract_signatures("item.py", content)

    assert signatures is not None
    assert "class Item:" in signatures
    assert "amount: float" in signatures
    assert "def total(self) -> float:" in signatures
    assert "async def load() -> None:" in signatures


def test_is_class_field_rejects_blank_comment_and_control_flow():
    assert _is_class_field("", ".py") is False
    assert _is_class_field("# comment", ".py") is False
    assert _is_class_field("pass", ".py") is False
    assert _is_class_field("return value", ".py") is False
    assert _is_class_field("if condition:", ".py") is False


def test_is_class_field_python_import_def_and_dict_literal_are_not_fields():
    assert _is_class_field("import os", ".py") is False
    assert _is_class_field("def method(self):", ".py") is False
    assert _is_class_field("class Inner:", ".py") is False
    assert _is_class_field("data: dict = {}", ".py") is True
    assert _is_class_field("mapping: dict", ".py") is True
    assert _is_class_field("no_annotation = 1", ".py") is False


def test_is_class_field_python_non_identifier_and_empty_annotation():
    assert _is_class_field(".invalid: int", ".py") is False
    assert _is_class_field("value:", ".py") is False


def test_python_class_member_that_is_neither_annotation_nor_function():
    content = (
        "class Mixed:\n"
        "    alias = int\n"
        "    def method(self):\n"
        "        return 1\n"
    )
    signatures = extract_signatures("mixed.py", content)
    assert signatures is not None
    assert "class Mixed:" in signatures
    assert "def method(self)" in signatures


def test_is_class_field_js_modifiers_and_interface_syntax():
    assert _is_class_field("private name: string;", ".ts") is True
    assert _is_class_field("readonly count = 0;", ".ts") is True
    assert _is_class_field("name: string;", ".ts") is True
    assert _is_class_field("call()", ".ts") is False
    assert _is_class_field(": string;", ".ts") is False


def test_is_class_field_generic_language_rules():
    assert _is_class_field("field: int", ".go") is True
    assert _is_class_field("a_very_long_identifier_name_over_fifty_characters_long: int", ".go") is False
    assert _is_class_field("package main", ".go") is False
