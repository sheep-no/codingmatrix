import asyncio
import json
import subprocess
import types

import pytest

from app.agent import utils


def test_clean_code_block_coerces_coroutine_and_non_string():
    async def coro():
        return "x"

    coroutine = coro()
    try:
        result = utils.clean_code_block(coroutine)
    finally:
        coroutine.close()

    assert isinstance(result, str)
    assert utils.clean_code_block(123) == "123"


def test_clean_code_block_handles_unclosed_think_block():
    assert utils.clean_code_block("<think>never closed\ncode") == ""


@pytest.mark.asyncio
async def test_extract_engineer_content_coerces_coroutine_and_mapping(tmp_path):
    engineer = _Engineer(edited=None)

    async def coro():
        return "x"

    coroutine = coro()
    try:
        result = await utils.extract_engineer_content(coroutine, engineer, tmp_path, "main.py")
    finally:
        coroutine.close()

    assert result is None
    assert await utils.extract_engineer_content({"a": 1}, engineer, tmp_path, "main.py") is None


def test_strip_leading_file_label_without_trailing_newline():
    assert utils.strip_leading_file_label("app/main.py\n", "app/main.py") == ""
    assert utils.strip_leading_file_label("", "app/main.py") == ""


class _Engineer:
    def __init__(self, edited=None):
        self._edited = edited

    def get_edited_files(self):
        return self._edited


@pytest.mark.asyncio
async def test_extract_engineer_content_coerces_non_string(tmp_path):
    engineer = _Engineer(edited=None)
    result = await utils.extract_engineer_content(
        None, engineer, tmp_path, "main.py"
    )
    assert result is None


@pytest.mark.asyncio
async def test_extract_engineer_content_reads_edited_file_and_fixes_imports(
    tmp_path, monkeypatch
):
    (tmp_path / "main.py").write_text("import old\n", encoding="utf-8")
    engineer = _Engineer(edited=["main.py"])
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    result = await utils.extract_engineer_content(
        "ignored",
        engineer,
        tmp_path,
        "main.py",
        fix_imports_fn=lambda content, *_a: "import new\n",
        all_files=["main.py"],
    )

    assert result == "import new\n"
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "import new\n"


@pytest.mark.asyncio
async def test_extract_engineer_content_edited_file_sandbox_failure(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("bad\n", encoding="utf-8")
    engineer = _Engineer(edited=["main.py"])
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (False, "broken"))

    assert await utils.extract_engineer_content("x", engineer, tmp_path, "main.py") is None


@pytest.mark.asyncio
async def test_extract_engineer_content_edited_file_language_failure(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    engineer = _Engineer(edited=["main.py"])
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    async def lang_fail(*_a, **_k):
        return False, "wrong language"

    monkeypatch.setattr(utils, "validate_language_with_llm", lang_fail)

    result = await utils.extract_engineer_content(
        "x", engineer, tmp_path, "main.py", expected_language="Python", llm_caller=lang_fail
    )

    assert result is None


@pytest.mark.asyncio
async def test_extract_engineer_content_edited_missing_file_reported(tmp_path, caplog):
    engineer = _Engineer(edited=["missing.py"])
    result = await utils.extract_engineer_content("x", engineer, tmp_path, "missing.py")

    assert result is None


@pytest.mark.asyncio
async def test_extract_engineer_content_edited_other_file_no_error(tmp_path):
    engineer = _Engineer(edited=["other.py"])
    result = await utils.extract_engineer_content("x", engineer, tmp_path, "main.py")

    assert result is None


@pytest.mark.asyncio
async def test_extract_engineer_content_edit_marker_reads_file(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "_is_edit_marker", lambda *a, **k: True)
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    result = await utils.extract_engineer_content(
        '{"action": "edit"}', engineer, tmp_path, "main.py"
    )

    assert result == "def run():\n    return 1\n"


@pytest.mark.asyncio
async def test_extract_engineer_content_edit_marker_applies_import_fix(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("import old\n", encoding="utf-8")
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "_is_edit_marker", lambda *a, **k: True)
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    result = await utils.extract_engineer_content(
        '{"action": "edit"}',
        engineer,
        tmp_path,
        "main.py",
        fix_imports_fn=lambda content, *_a: content + "# fixed\n",
        all_files=["main.py"],
    )

    assert result == "import old\n# fixed\n"
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "import old\n# fixed\n"


@pytest.mark.asyncio
async def test_extract_engineer_content_edit_marker_missing_file(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "_is_edit_marker", lambda *a, **k: True)

    assert await utils.extract_engineer_content("{}", engineer, tmp_path, "main.py") is None


@pytest.mark.asyncio
async def test_extract_engineer_content_edit_marker_sandbox_failure(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "_is_edit_marker", lambda *a, **k: True)
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (False, "bad"))

    assert await utils.extract_engineer_content(
        '{"action": "edit"}', engineer, tmp_path, "main.py"
    ) is None


@pytest.mark.asyncio
async def test_extract_engineer_content_edit_marker_language_failure(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "_is_edit_marker", lambda *a, **k: True)
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    async def lang_fail(*_a, **_k):
        return False, "wrong"

    monkeypatch.setattr(utils, "validate_language_with_llm", lang_fail)

    assert await utils.extract_engineer_content(
        '{"action": "edit"}',
        engineer,
        tmp_path,
        "main.py",
        expected_language="Python",
        llm_caller=lang_fail,
    ) is None


@pytest.mark.asyncio
async def test_extract_engineer_content_plain_invalid_returns_none(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (False, "bad"))

    assert await utils.extract_engineer_content(
        "def run():\n    return 1\n", engineer, tmp_path, "main.py"
    ) is None


@pytest.mark.asyncio
async def test_extract_engineer_content_plain_placeholder_returns_none(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr(utils, "is_placeholder_content", lambda *a, **k: (True, "stub"))

    assert await utils.extract_engineer_content(
        "def run():\n    return 1\n", engineer, tmp_path, "main.py"
    ) is None


@pytest.mark.asyncio
async def test_extract_engineer_content_plain_sandbox_failure(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr(utils, "is_placeholder_content", lambda *a, **k: (False, ""))
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (False, "bad"))

    assert await utils.extract_engineer_content(
        "def run():\n    return 1\n", engineer, tmp_path, "main.py"
    ) is None


@pytest.mark.asyncio
async def test_extract_engineer_content_plain_language_failure(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr(utils, "is_placeholder_content", lambda *a, **k: (False, ""))
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    async def lang_fail(*_a, **_k):
        return False, "bad"

    monkeypatch.setattr(utils, "validate_language_with_llm", lang_fail)

    assert await utils.extract_engineer_content(
        "def run():\n    return 1\n",
        engineer,
        tmp_path,
        "main.py",
        expected_language="Python",
        llm_caller=lang_fail,
    ) is None


@pytest.mark.asyncio
async def test_extract_engineer_content_extracts_metadata_and_applies_fix(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "try_extract_from_metadata", lambda *a, **k: "extracted")
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr(utils, "is_placeholder_content", lambda *a, **k: (False, ""))
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    result = await utils.extract_engineer_content(
        "raw",
        engineer,
        tmp_path,
        "main.py",
        fix_imports_fn=lambda content, *_a: content + "fixed\n",
        all_files=["main.py"],
    )

    assert result == "extractedfixed\n"


@pytest.mark.asyncio
async def test_extract_engineer_content_plain_import_fix_unchanged(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr(utils, "is_placeholder_content", lambda *a, **k: (False, ""))
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    def identity(content, *_a):
        return content

    result = await utils.extract_engineer_content(
        "def run():\n    return 1\n",
        engineer,
        tmp_path,
        "main.py",
        fix_imports_fn=identity,
        all_files=["main.py"],
    )

    assert result == "def run():\n    return 1"


@pytest.mark.asyncio
async def test_extract_engineer_content_plain_without_import_fix(tmp_path, monkeypatch):
    engineer = _Engineer(edited=None)
    monkeypatch.setattr(utils, "is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr(utils, "is_placeholder_content", lambda *a, **k: (False, ""))
    monkeypatch.setattr(utils, "validate_file_in_sandbox", lambda *a, **k: (True, ""))

    result = await utils.extract_engineer_content(
        "def run():\n    return 1\n", engineer, tmp_path, "main.py"
    )

    assert result == "def run():\n    return 1"


def test_is_edit_marker_rejects_non_dict_and_invalid_json():
    assert utils._is_edit_marker('["a"]', "main.py") is False
    assert utils._is_edit_marker("{not json}", "main.py") is False
    assert utils._is_edit_marker("plain", "main.py") is False


def test_is_edit_marker_non_dict_json_payload(monkeypatch):
    monkeypatch.setattr(utils.json, "loads", lambda _content: ["not", "a", "dict"])

    assert utils._is_edit_marker('{"ignored": true}', "main.py") is False


def test_try_extract_from_metadata_handles_empty_and_non_dict():
    assert utils.try_extract_from_metadata("main.py", "") is None
    assert utils.try_extract_from_metadata("main.py", "not json") is None
    assert utils.try_extract_from_metadata("main.py", '["a"]') is None
    assert utils.try_extract_from_metadata("main.py", "{not json}") is None
    assert utils.try_extract_from_metadata("main.py", '{"other": "x"}') is None


def test_try_extract_from_metadata_non_dict_json_payload(monkeypatch):
    monkeypatch.setattr(utils.json, "loads", lambda _content: ["not", "a", "dict"])

    assert utils.try_extract_from_metadata("main.py", '{"ignored": true}') is None


def test_try_extract_from_metadata_json_wrapper_requires_marker():
    assert utils.try_extract_from_metadata("config.json", '{"content": "' + "x" * 60 + '"}') is None
    assert utils.try_extract_from_metadata(
        "config.json", '{"status": "ok", "content": "' + "x" * 60 + '"}'
    ) == "x" * 60


def test_is_valid_code_content_invalid_json_array_and_metadata():
    valid, reason = utils.is_valid_code_content("main.py", '["a", "b"]')
    assert valid is False
    assert reason == "内容是 JSON 数组而非代码"

    valid, reason = utils.is_valid_code_content("main.py", '{"status": "ok"}')
    assert valid is False
    assert reason == "内容是 JSON 元数据而非代码"


def test_is_valid_code_content_empty_regular_file():
    valid, reason = utils.is_valid_code_content("main.py", "")
    assert valid is False
    assert reason == "内容为空"


def test_is_valid_code_content_json_object_without_metadata_keys():
    valid, _ = utils.is_valid_code_content("app.rb", '{"foo": 1}')
    assert valid is True


def test_is_valid_code_content_invalid_json_payloads_are_tolerated():
    valid, _ = utils.is_valid_code_content("main.py", "{not json}")
    assert valid is True

    valid, _ = utils.is_valid_code_content("main.py", "[not json]")
    assert valid is True


def test_validate_syntax_for_extension_invalid_json():
    valid, reason = utils.validate_syntax_for_extension("config.json", "{bad}")
    assert valid is False
    assert reason.startswith("JSON 格式错误")


def test_validate_syntax_for_extension_invalid_python():
    valid, reason = utils.validate_syntax_for_extension("main.py", "def broken(:\n")
    assert valid is False
    assert reason.startswith("Python 语法错误")


def test_is_valid_code_content_invalid_json_object_payload_tolerated():
    valid, _ = utils.is_valid_code_content("main.py", '{"status": bad}')
    assert valid is True


def test_sandbox_validators_return_empty_scripts_for_unsupported_files():
    assert utils.GoSandboxValidator().build_validation_script({"main.py": "x"}) == ""
    assert utils.RustSandboxValidator().build_validation_script({"main.py": "x"}) == ""


def test_rust_sandbox_builds_script_for_rust_files():
    script = utils.RustSandboxValidator().build_validation_script({"main.rs": "fn main() {}"})

    assert "rustc" in script
    assert "main.rs" in script


def test_sandbox_validator_builds_script_and_registers_extensions():
    class _Custom(utils.SandboxValidator):
        extensions = [".custom"]

        def build_validation_script(self, files, level="import"):
            return "SCRIPT"

    validator = _Custom()
    utils.register_sandbox_validator(validator)
    try:
        assert utils._EXTENSION_VALIDATORS[".custom"] is validator
        assert validator.filter_files({"a.custom": "x", "b.py": "y"}) == {"a.custom": "x"}
    finally:
        utils._EXTENSION_VALIDATORS.pop(".custom", None)
        if validator in utils._VALIDATOR_INSTANCES:
            utils._VALIDATOR_INSTANCES.remove(validator)


def test_sandbox_validator_base_raises():
    with pytest.raises(NotImplementedError):
        utils.SandboxValidator().build_validation_script({})


def test_decide_level_without_context_and_unknown_trigger():
    assert utils._decide_level(None) == "syntax"
    assert utils._decide_level({"trigger": "unknown"}) == "syntax"


def test_decide_level_uses_hardcoded_rule():
    assert utils._decide_level({"trigger": "project_complete"}) == "run"


def test_decide_level_uses_valid_user_config():
    assert utils._decide_level(
        {"trigger": "unknown", "config": {"on_unknown": "import"}}
    ) == "import"


def test_decide_level_ignores_invalid_user_config():
    assert utils._decide_level(
        {"trigger": "unknown", "config": {"on_unknown": "bogus"}}
    ) == "syntax"


def test_shared_syntax_errors_empty_vue_script_is_valid():
    assert utils._shared_syntax_errors("App.vue", "<template></template>") == []


def test_shared_syntax_errors_css_and_html():
    assert utils._shared_syntax_errors("style.css", ".a { color: red; }") == []
    assert utils._shared_syntax_errors("index.html", "<html><body>x</body></html>") == []


def test_shared_syntax_errors_unknown_extension():
    assert utils._shared_syntax_errors("main.rb", "puts 1") == []


def test_validate_in_sandbox_empty_files_returns_true():
    assert utils.validate_in_sandbox("", {}) == (True, [])


def test_validate_in_sandbox_auto_level_uses_decider(monkeypatch):
    monkeypatch.setattr(utils, "_decide_level", lambda context: "run")
    assert utils.validate_in_sandbox("", {"main.py": "x = 1"}, level="auto") == (True, [])


def test_validate_in_sandbox_compiler_path_success(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/bwrap")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="OK", stderr=""),
    )

    passed, errors = utils.validate_in_sandbox(
        "", {"main.go": "package main\n"}, level="syntax"
    )

    assert passed is True
    assert errors == []


def test_validate_in_sandbox_compiler_path_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/bwrap")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="boom\n"),
    )

    passed, errors = utils.validate_in_sandbox(
        "", {"main.go": "package main\n"}, level="syntax"
    )

    assert passed is False
    assert errors == ["boom"]


def test_validate_in_sandbox_compiler_timeout(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/bwrap")

    def raise_timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="bwrap", timeout=60)

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    assert utils.validate_in_sandbox("", {"main.go": "package main\n"}, level="syntax") == (True, [])


def test_validate_in_sandbox_compiler_exception(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/bwrap")

    def boom(*_a, **_k):
        raise OSError("no exec")

    monkeypatch.setattr(subprocess, "run", boom)

    assert utils.validate_in_sandbox("", {"main.go": "package main\n"}, level="syntax") == (True, [])


def test_validate_in_sandbox_skips_empty_validator_script(monkeypatch):
    class _Empty(utils.SandboxValidator):
        extensions = [".empty"]

        def build_validation_script(self, files, level="import"):
            return ""

    monkeypatch.setitem(utils._EXTENSION_VALIDATORS, ".empty", _Empty())

    assert utils.validate_in_sandbox("", {"main.empty": "x"}, level="syntax") == (True, [])


def test_validate_file_in_sandbox_reports_first_error(monkeypatch):
    monkeypatch.setattr(utils, "validate_in_sandbox", lambda *a, **k: (False, ["first", "second"]))

    assert utils.validate_file_in_sandbox("main.py", "x") == (False, "first")


def test_validate_file_in_sandbox_success(monkeypatch):
    monkeypatch.setattr(utils, "validate_in_sandbox", lambda *a, **k: (True, []))

    assert utils.validate_file_in_sandbox("main.py", "x") == (True, "")


def test_validate_file_in_sandbox_failure_without_errors(monkeypatch):
    monkeypatch.setattr(utils, "validate_in_sandbox", lambda *a, **k: (False, []))

    assert utils.validate_file_in_sandbox("main.py", "x") == (False, "验证失败")


def test_validate_project_in_sandbox_delegates_to_import_level():
    assert utils.validate_project_in_sandbox("", {"main.py": "x"}) == (True, [])


@pytest.mark.asyncio
async def test_validate_language_short_content_and_heuristic():
    assert await utils.validate_language_with_llm("main.py", "x", "Python", lambda p: None) == (True, "")

    called = []

    async def llm(prompt):
        called.append(prompt)
        return "x"

    result = await utils.validate_language_with_llm(
        "main.py", "def run():\n    return 1\n", "Python", llm
    )
    assert result == (True, "")
    assert called == []


@pytest.mark.asyncio
async def test_validate_language_non_matching_heuristic_does_not_call_llm():
    called = []

    async def llm(prompt):
        called.append(prompt)
        return "x"

    result = await utils.validate_language_with_llm(
        "app.py",
        "print('hello world this is not python markers')\n",
        "Python",
        llm,
    )

    assert result == (True, "")
    assert called == []


@pytest.mark.asyncio
async def test_validate_language_without_expected_language_or_caller():
    assert await utils.validate_language_with_llm("main.py", "", "", None) == (True, "")


def test_heuristic_language_match_documentation_and_js():
    assert utils._heuristic_language_match("readme.md", "anything", "Markdown") is True
    assert utils._heuristic_language_match("app.js", "const x = 1;", "JavaScript") is True
    assert utils._heuristic_language_match("app.rb", "puts 1", "Ruby") is False


def test_has_effective_code_after_ignores_comments_and_punctuation():
    assert utils._has_effective_code_after("x\n# comment\n)", 1) is False
    assert utils._has_effective_code_after("x\ny = 1\n", 1) is True


def test_placeholder_truncation_filters_blank_and_docstring_lines():
    content = '"""placeholder"""\n\n# comment\n\npass\n'
    is_ph, reason = utils.is_placeholder_content(content, "app.py")

    assert is_ph is True
    assert "占位符代码" in reason


def test_placeholder_rejects_tool_call_leak_in_middle():
    content = "x = 1\n" + '{"tool": "search"}' + "\n"
    assert utils.is_placeholder_content(content, "app.py")[0] is True


def test_reusable_existing_file_content_rejects_placeholder():
    reusable, reason = utils.reusable_existing_file_content("app.py", "# TODO: implement\n")

    assert reusable is False
    assert reason


def test_placeholder_rejects_each_truncation_pattern():
    for tail in ("未展示完整", "后续代码与", "需替换为真实实现", "omitted for brevity"):
        is_ph, _ = utils.is_placeholder_content(f"def a():\n    return 1\n# {tail}\n", "app.py")
        assert is_ph is True


def test_placeholder_rejects_docstring_placeholders():
    for content in (
        '"""placeholder"""\n',
        "'''TODO'''\n",
        "# FIXME\n",
        "# placeholder\n",
        "raise NotImplementedError\n",
        "// TODO: implement\n",
        "// FIXME\n",
        "// Placeholder\n",
        "/* placeholder */\n",
        "/* TODO */\n",
        'console.log("placeholder")\n',
        'console.log("TODO")\n',
        'console.log("FIXME")\n',
        'throw new Error("Not implemented")\n',
        'throw new Error("TODO")\n',
        "// Package initialization\n",
        '"""Package initialization"""\n',
        "https://example.com\n",
    ):
        assert utils.is_placeholder_content(content, "app/x.py")[0] is True


def test_placeholder_accepts_dotfile_and_empty_package_entry():
    assert utils.is_placeholder_content("", ".gitkeep")[0] is False
    assert utils.is_placeholder_content("", "app/__init__.py")[0] is False


def test_compact_project_context_handles_non_dict_architecture_and_contract():
    compact = utils.compact_project_context_for_file(
        "main.py",
        {
            "architecture": "nope",
            "requirement": None,
        },
    )
    payload = json.loads(compact)
    assert payload["language"] is None
    assert payload["this_file"]["path"] == "main.py"


def test_compact_project_context_skips_non_dict_plan_items():
    compact = utils.compact_project_context_for_file(
        "main.py",
        {"architecture": {"file_plan": ["not-a-dict", {"path": "main.py"}]}},
    )
    payload = json.loads(compact)
    assert payload["this_file"]["path"] == "main.py"


def test_compact_project_context_includes_symbol_table_and_signatures():
    compact = utils.compact_project_context_for_file(
        "main.py",
        {
            "architecture": {
                "language": "python",
                "file_plan": [{"path": "main.py", "contract": "bad"}],
                "symbol_table": {
                    "storage": {"type": "sqlite"},
                    "auth": {"type": "jwt"},
                    "route_prefix": "/api",
                    "files": {"main.py": {"must_implement": True}},
                },
            },
            "generated_signatures": {"utils.py": "def foo()"},
        },
    )
    payload = json.loads(compact)
    assert payload["symbol_table"]["storage"] == {"type": "sqlite"}
    assert payload["frozen_facts"]["route_prefix"] == "/api"
    assert payload["already_generated"] == {"utils.py": "def foo()"}


def test_compact_project_context_partial_symbol_table_and_generation_contract():
    compact = utils.compact_project_context_for_file(
        "main.py",
        {
            "architecture": {
                "language": "python",
                "file_plan": [{"path": "main.py"}],
                "symbol_table": {"storage": {"type": "sqlite"}},
            },
            "generation_contract": {
                "original_content": "old content",
                "modification_reason": "why",
            },
        },
    )
    payload = json.loads(compact)
    assert payload["generation_contract"]["original_content"] == "old content"
    assert payload["symbol_table"] == {"storage": {"type": "sqlite"}}
    assert payload["is_modification"] is True
    assert payload["modification_reason"] == "why"


def test_compact_project_context_symbol_table_without_frozen_keys():
    compact = utils.compact_project_context_for_file(
        "main.py",
        {
            "architecture": {
                "file_plan": [{"path": "main.py"}],
                "symbol_table": {"files": {}},
            },
        },
    )
    payload = json.loads(compact)
    assert "frozen_facts" not in payload
    assert "must_implement" not in payload["this_file"]


def test_write_file_atomic_rejects_placeholder(tmp_path):
    assert utils.write_file_atomic(tmp_path, "main.py", "pass\n") is False
    assert not (tmp_path / "main.py").exists()


def test_write_file_atomic_writes_successfully(tmp_path):
    assert utils.write_file_atomic(tmp_path, "pkg/main.py", "def run():\n    return 1\n") is True
    assert (tmp_path / "pkg/main.py").exists()


def test_write_file_atomic_skips_placeholder_check(tmp_path):
    assert utils.write_file_atomic(tmp_path, "main.py", "pass\n", skip_placeholder_check=True) is True


def test_write_file_atomic_cleans_up_on_failure(tmp_path, monkeypatch):
    def boom(self, *_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("pathlib.Path.rename", boom)

    assert utils.write_file_atomic(tmp_path, "main.py", "def run():\n    return 1\n") is False
    leftovers = list(tmp_path.glob("main.py.tmp.*"))
    assert leftovers == []


def test_write_file_atomic_failure_before_temp_file_created(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("cannot open")

    monkeypatch.setattr("builtins.open", boom)

    assert utils.write_file_atomic(tmp_path, "main.py", "def run():\n    return 1\n") is False
    assert list(tmp_path.glob("main.py.tmp.*")) == []


def test_validate_content_quality_short_content_and_python_frontend():
    assert utils.validate_content_quality("main.py", "x") == ""
    warning = utils.validate_content_quality(
        "static/js/main.py", "def run():\n    return 1\n"
    )
    assert "前端资源目录" in warning


def test_validate_content_quality_normal_python_passes():
    assert utils.validate_content_quality(
        "app/main.py", "def run():\n    return 1\n"
    ) == ""


def test_validate_content_quality_css_prose_skips_comments():
    content = "/* 很长的中文注释用来解释样式 */\n" * 4 + ".a { color: red; }\n"
    assert utils.validate_content_quality("style.css", content) == ""


def test_cleanup_temp_files_removes_leftovers(tmp_path):
    leftover = tmp_path / "main.py.tmp.12345678"
    leftover.write_text("x", encoding="utf-8")

    utils.cleanup_temp_files(tmp_path, "main.py")

    assert not leftover.exists()


@pytest.mark.parametrize(
    ("file_path", "expected"),
    [
        ("requirements.txt", "TOML/INI"),
        ("package.json", "JSON"),
        ("go.mod", "TOML/XML"),
        ("Dockerfile", "Dockerfile"),
        ("README.md", "Markdown"),
        (".gitignore", "Config"),
        ("main.py", "Python"),
        ("unknown.xyz", "Python"),
        ("unknown.xyz", ""),
    ],
)
def test_get_expected_language_for_file(file_path, expected):
    project_language = "python" if file_path == "unknown.xyz" and expected else ""
    assert utils.get_expected_language_for_file(file_path, project_language) == expected
