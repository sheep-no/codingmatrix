"""`app.utils.agent_core` 非生成循环分支覆盖。

补齐会话管理、模型路由、Token 编码、工具注册、代码/项目校验以及文件工具
函数的分支，作为模块整体 95%+ 覆盖率的基础。
"""

import ast
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schema.codeRequest import AgentConfig, ToolDefinition
from app.utils import agent_core
from app.utils.agent_core import (
    CodeValidator,
    ConversationHistoryManager,
    FileModelRouter,
    ProjectFileManager,
    ProjectValidator,
    TokenEncoder,
    ToolRegistry,
    ValidationResult,
    ValidationType,
    _count_keyword_hits,
    _list_relative_files,
    _resolve_project_write_path,
    create_file,
    create_project_file,
    delete_file,
    edit_file,
    extract_markdown_code_block,
    grep_files,
    list_directory,
    list_files,
    project_stats,
    project_tree,
    read_file,
    rename_file,
    search_files,
    validate_file,
    validate_project,
)


def _config(**overrides) -> AgentConfig:
    return AgentConfig(**overrides)


def _result(success: bool, issues=None, warnings=None) -> ValidationResult:
    return ValidationResult(
        file_path="x.py",
        validation_type=ValidationType.SYNTAX_CHECK,
        success=success,
        issues=issues or [],
        warnings=warnings or [],
    )


# ==================== ConversationHistoryManager ====================


@pytest.mark.asyncio
async def test_history_manager_full_lifecycle():
    mgr = ConversationHistoryManager()
    assert await mgr.get_history("s") == []
    assert await mgr.get_output_dir("s") is None
    assert await mgr.has_history("s") is False

    await mgr.add_messages("s", [{"role": "user", "content": "hi"}])
    assert await mgr.has_history("s") is True
    assert (await mgr.get_history("s"))[0]["content"] == "hi"

    await mgr.set_output_dir("s", "/tmp/out")
    assert await mgr.get_output_dir("s") == "/tmp/out"

    await mgr.set_history("s", [{"role": "system", "content": "ctx"}])
    assert (await mgr.get_history("s"))[0]["content"] == "ctx"

    await mgr.clear_history("s")
    assert await mgr.has_history("s") is False
    # 清除不存在的会话不报错
    await mgr.clear_history("s")


@pytest.mark.asyncio
async def test_history_manager_truncates_messages():
    mgr = ConversationHistoryManager()
    mgr.MAX_MESSAGES_PER_SESSION = 2
    await mgr.add_messages("s", [{"i": 1}, {"i": 2}, {"i": 3}])
    assert [m["i"] for m in await mgr.get_history("s")] == [2, 3]

    await mgr.set_history("s", [{"i": 1}, {"i": 2}, {"i": 3}])
    assert [m["i"] for m in await mgr.get_history("s")] == [2, 3]


@pytest.mark.asyncio
async def test_history_manager_cleanup_logs(monkeypatch):
    records = []
    monkeypatch.setattr(agent_core.logger, "info", lambda msg: records.append(msg))
    mgr = ConversationHistoryManager()
    mgr.MAX_ACTIVE_SESSIONS = 1
    await mgr.add_messages("a", [{"role": "user", "content": "1"}])
    await mgr.add_messages("b", [{"role": "user", "content": "1"}])
    assert any("清理" in r for r in records)


# ==================== 关键词 / 路由 / 编码器 ====================


def test_count_keyword_hits_handles_ascii_and_cjk():
    assert _count_keyword_hits(["api", "ui"], "build api") == 1
    assert _count_keyword_hits(["接口"], "实现接口") == 1


def test_file_model_router_without_roles_falls_back(monkeypatch):
    monkeypatch.setattr(
        "app.utils.model_config_io.load_model_config",
        lambda path: {"roles": {}, "models": {}},
    )
    router = FileModelRouter()
    assert router.frontend_model == FileModelRouter._DEFAULT_FRONTEND_MODEL
    assert router.backend_model == FileModelRouter._DEFAULT_BACKEND_MODEL


def test_file_model_router_resolves_roles(monkeypatch):
    monkeypatch.setattr(
        "app.utils.model_config_io.load_model_config",
        lambda path: {
            "roles": {"frontend": "f", "backend": "b", "fallback": "x"},
            "models": {"f": {"name": "front-name"}, "b": {"name": ""}},
        },
    )
    router = FileModelRouter()
    assert router.frontend_model == "front-name"
    # name 为空时回退 role id
    assert router.backend_model == "b"
    assert router.fallback_model == "x"


def test_file_model_router_load_failure_uses_defaults(monkeypatch):
    def boom(path):
        raise RuntimeError("bad yaml")

    monkeypatch.setattr("app.utils.model_config_io.load_model_config", boom)
    router = FileModelRouter()
    assert router.frontend_model == FileModelRouter._DEFAULT_FRONTEND_MODEL


@pytest.mark.parametrize(
    "model,expected",
    [
        ("deepseek-chat", "cl100k_base"),
        ("qwen-plus", "cl100k_base"),
        ("plain-model", "cl100k_base"),
    ],
)
def test_token_encoder_encodings(model, expected):
    encoder = TokenEncoder(model)
    assert encoder._encoder.name == expected
    assert encoder.encode("hello")
    assert encoder.count_tokens("hello") >= 1


def test_token_encoder_gpt_model(monkeypatch):
    fake = SimpleNamespace(name="fake")
    monkeypatch.setattr(agent_core.tiktoken, "encoding_for_model", lambda name: fake)
    encoder = TokenEncoder("gpt-4o")
    assert encoder._encoder is fake


# ==================== ToolRegistry / markdown 提取 ====================


def test_tool_registry_rejects_unannotated_param():
    def bad(x):
        return x

    with pytest.raises(ValueError):
        ToolRegistry.register("bad_tool", "bad")(bad)


def test_tool_registry_schema_skips_broken_tool(monkeypatch):
    def broken_schema():
        raise RuntimeError("no schema")

    ToolRegistry._tool["broken_tool"] = ToolDefinition(
        name="broken_tool",
        func=lambda: None,
        description="broken",
        parameters=SimpleNamespace(schema=broken_schema),
    )
    try:
        schemas = ToolRegistry.get_schema()
        assert all(s["function"]["name"] != "broken_tool" for s in schemas)
    finally:
        ToolRegistry._tool.pop("broken_tool", None)

    assert ToolRegistry.get("broken_tool") is None


class _SelfTool:
    @ToolRegistry.register("self_tool", "带 self 参数")
    def method(self, value: int = 1) -> int:
        return value


def test_tool_registry_skips_self_param():
    tool = ToolRegistry.get("self_tool")
    assert tool is not None
    assert tool.parameters(**{}).dict() == {"value": 1}


def test_extract_markdown_code_block():
    assert extract_markdown_code_block("```python\nx = 1\n```") == "x = 1"
    assert extract_markdown_code_block("plain text") == "plain text"


# ==================== CodeValidator ====================


@pytest.mark.asyncio
async def test_validate_python_file_missing(tmp_path):
    validator = CodeValidator(tmp_path, _config())
    result = await validator.validate_python_file(tmp_path / "missing.py")
    assert result.success is False
    assert "文件不存在" in result.issues


@pytest.mark.asyncio
async def test_validate_python_file_skips_non_python(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config())
    result = await validator.validate_python_file(target)
    assert result.success is True
    assert "非Python文件" in result.issues[0]


@pytest.mark.asyncio
async def test_validate_python_file_merges_results(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config())

    async def fake(name):
        return _result(True, warnings=[f"{name}-warn"])

    monkeypatch.setattr(validator, "_validate_syntax", lambda p: fake("syntax"))
    monkeypatch.setattr(validator, "_validate_imports", lambda p: fake("import"))
    monkeypatch.setattr(validator, "_validate_runtime", lambda p: fake("runtime"))
    monkeypatch.setattr(validator, "_validate_security", lambda p: fake("security"))

    result = await validator.validate_python_file(target)
    assert result.success is True
    assert len(result.warnings) == 4
    assert "syntax_check" in result.details


@pytest.mark.asyncio
async def test_validate_syntax_syntax_error(tmp_path):
    target = tmp_path / "bad.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config())
    result = await validator._validate_syntax(target)
    assert result.success is False
    assert result.issues[0].startswith("语法错误")


@pytest.mark.asyncio
async def test_validate_syntax_ast_analysis_failure(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config())

    def boom(tree):
        raise RuntimeError("ast fail")

    monkeypatch.setattr(validator, "_check_unused_imports", boom)
    result = await validator._validate_syntax(target)
    assert result.success is True
    assert any("AST分析失败" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_validate_syntax_read_failure(tmp_path, monkeypatch):
    validator = CodeValidator(tmp_path, _config())

    async def boom(path):
        raise OSError("denied")

    monkeypatch.setattr(agent_core, "_read_text_async", boom)
    result = await validator._validate_syntax(tmp_path / "a.py")
    assert result.success is False
    assert "语法验证失败" in result.issues[0]


@pytest.mark.asyncio
async def test_validate_imports_reports_unimportable(tmp_path):
    target = tmp_path / "a.py"
    target.write_text(
        "import totally_missing_module_xyz\nfrom another_missing_xyz import thing\n",
        encoding="utf-8",
    )
    validator = CodeValidator(tmp_path, _config())
    result = await validator._validate_imports(target)
    assert result.success is False
    assert len(result.issues) == 2
    assert "totally_missing_module_xyz" in result.details["imports_checked"]


@pytest.mark.asyncio
async def test_validate_imports_parse_failure(tmp_path):
    target = tmp_path / "a.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config())
    result = await validator._validate_imports(target)
    assert result.success is False
    assert "导入验证失败" in result.issues[0]


@pytest.mark.asyncio
async def test_validate_runtime_disabled(tmp_path):
    validator = CodeValidator(tmp_path, _config(enable_runtime_validation=False))
    result = await validator._validate_runtime(tmp_path / "a.py")
    assert result.success is True
    assert "运行时验证已禁用" in result.warnings[0]


@pytest.mark.asyncio
async def test_validate_runtime_success_with_stdout(tmp_path):
    target = tmp_path / "ok.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config(enable_runtime_validation=True))
    result = await validator._validate_runtime(target)
    assert result.success is True
    assert any("hello" in w for w in result.warnings)
    assert result.details["returncode"] == 0


@pytest.mark.asyncio
async def test_validate_runtime_nonzero_exit(tmp_path):
    target = tmp_path / "fail.py"
    target.write_text("raise SystemExit(3)\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config(enable_runtime_validation=True))
    result = await validator._validate_runtime(target)
    assert result.success is False
    assert result.issues[0].startswith("运行时错误")


@pytest.mark.asyncio
async def test_validate_runtime_timeout(tmp_path, monkeypatch):
    target = tmp_path / "slow.py"
    target.write_text("print('x')\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, _config(enable_runtime_validation=True))

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(agent_core.asyncio, "wait_for", fake_wait_for)
    result = await validator._validate_runtime(target)
    assert result.success is False
    assert "执行超时" in result.issues[0]


@pytest.mark.asyncio
async def test_validate_runtime_copy_failure(tmp_path):
    validator = CodeValidator(tmp_path, _config(enable_runtime_validation=True))
    result = await validator._validate_runtime(tmp_path / "gone.py")
    assert result.success is False
    assert "运行时验证失败" in result.issues[0]


@pytest.mark.asyncio
async def test_validate_security_reports_sensitive_patterns(tmp_path):
    target = tmp_path / "secret.py"
    target.write_text(
        "password = 'p@ss'\napi_key = 'k'\ntoken = 't'\nsecret = 's'\n",
        encoding="utf-8",
    )
    validator = CodeValidator(tmp_path, _config())
    result = await validator._validate_security(target)
    assert result.details["security_checks_performed"] == 4


@pytest.mark.asyncio
async def test_validate_security_read_failure(tmp_path, monkeypatch):
    validator = CodeValidator(tmp_path, _config())

    async def boom(path):
        raise OSError("denied")

    monkeypatch.setattr(agent_core, "_read_text_async", boom)
    result = await validator._validate_security(tmp_path / "a.py")
    assert result.success is True
    assert "安全验证失败" in result.warnings[0]


def test_is_importable_variants(monkeypatch):
    validator = CodeValidator(Path("."), _config())
    assert validator._is_importable("os") is True
    monkeypatch.setattr(
        agent_core.importlib.util, "find_spec", lambda name: None
    )
    assert validator._is_importable("missing_xyz") is False

    def boom(name):
        raise ValueError("weird name")

    monkeypatch.setattr(agent_core.importlib.util, "find_spec", boom)
    assert validator._is_importable("bad..name") is False


def test_installed_package_lookup(monkeypatch):
    validator = object.__new__(CodeValidator)
    validator._standard_lib_modules = set()
    validator._installed_packages = {"some_pkg"}
    assert validator._is_importable("some-pkg") is True


def test_standard_library_lookup_failure(monkeypatch):
    validator = object.__new__(CodeValidator)
    monkeypatch.setattr(sys, "stdlib_module_names", None)
    assert validator._get_standard_library_modules() == set()


def test_unused_imports_and_undefined_variables():
    validator = object.__new__(CodeValidator)
    tree = ast.parse("import os\nprint(undefined_name)\n")
    assert any("未使用的导入: os" in i for i in validator._check_unused_imports(tree))
    assert any("undefined_name" in i for i in validator._check_undefined_variables(tree))


def test_syntax_warnings_constant_compare():
    validator = object.__new__(CodeValidator)
    warnings = validator._check_syntax_warnings(ast.parse("if 1 == 1:\n    pass\n"))
    assert "常量比较可能总是True或False" in warnings


# ==================== ProjectValidator ====================


@pytest.mark.asyncio
async def test_project_validator_full_validation_callback_and_error(tmp_path, monkeypatch):
    validator = ProjectValidator(tmp_path, _config(max_concurrent_validations=1))
    events = []

    async def fake_files(callback=None):
        return [{"issues": ["e1"], "warnings": ["w1"]}]

    async def fake_deps(callback=None):
        return {"missing": ["dep"], "error": "dep-error"}

    async def fake_structure(callback=None):
        return {"structure_issues": ["s1"]}

    async def fake_entry(callback=None):
        return {"issues": ["entry"]}

    monkeypatch.setattr(validator, "_validate_all_files", fake_files)
    monkeypatch.setattr(validator, "_check_dependencies", fake_deps)
    monkeypatch.setattr(validator, "_check_project_structure", fake_structure)
    monkeypatch.setattr(validator, "_check_entrypoint", fake_entry)

    result = await validator.run_full_validation(callback=events.append)
    assert result["runnable"] is False
    assert "缺少依赖: dep" in result["errors"]
    assert "依赖检查失败: dep-error" in result["errors"]
    assert "s1" in result["warnings"]
    assert json.loads(events[-1])["type"] == "validation_complete"


@pytest.mark.asyncio
async def test_project_validator_full_validation_exception(tmp_path, monkeypatch):
    validator = ProjectValidator(tmp_path, _config())

    async def boom(callback=None):
        raise RuntimeError("explode")

    monkeypatch.setattr(validator, "_validate_all_files", boom)
    result = await validator.run_full_validation()
    assert result["runnable"] is False
    assert "验证过程异常: explode" in result["errors"][0]


@pytest.mark.asyncio
async def test_validate_all_files_handles_empty_and_batches(tmp_path, monkeypatch):
    validator = ProjectValidator(tmp_path, _config(max_concurrent_validations=1))
    events = []
    assert await validator._validate_all_files(callback=events.append) == []

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")

    async def fake_validate(path):
        return _result(True)

    monkeypatch.setattr(validator.code_validator, "validate_python_file", fake_validate)
    results = await validator._validate_all_files(callback=events.append)
    assert len(results) == 2
    assert any("批量文件验证完成" in json.loads(e)["message"] for e in events)
    # 无回调路径
    assert len(await validator._validate_all_files()) == 2


@pytest.mark.asyncio
async def test_validate_single_file_callbacks_success_and_failure(tmp_path):
    validator = ProjectValidator(tmp_path, _config())
    events = []

    async def ok_validate(path):
        return _result(True)

    validator.code_validator.validate_python_file = ok_validate
    result = await validator._validate_single_file(
        tmp_path / "a.py", 0, 1, callback=events.append
    )
    assert result["success"] is True
    assert json.loads(events[0])["type"] == "validation_progress"
    # 无回调路径
    assert (
        await validator._validate_single_file(tmp_path / "a.py", 0, 1)
    )["success"] is True

    async def bad_validate(path):
        return _result(False, issues=["bad"])

    validator.code_validator.validate_python_file = bad_validate
    events.clear()
    result = await validator._validate_single_file(
        tmp_path / "a.py", 0, 1, callback=events.append
    )
    assert result["success"] is False
    assert any("文件验证失败" in json.loads(e)["message"] for e in events)


@pytest.mark.asyncio
async def test_check_dependencies_missing_file_callback(tmp_path):
    validator = ProjectValidator(tmp_path, _config())
    events = []
    result = await validator._check_dependencies(callback=events.append)
    assert result["has_requirements"] is False
    assert json.loads(events[0])["type"] == "validation_progress"
    assert (await validator._check_dependencies())["has_requirements"] is False


@pytest.mark.asyncio
async def test_check_dependencies_installed_missing_and_error(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text(
        "# comment\nflask==3.0\nrequests>=2\n\nmissing-pkg<=1\n", encoding="utf-8"
    )
    validator = ProjectValidator(tmp_path, _config())
    validator.code_validator._installed_packages = {"flask", "requests"}
    events = []
    result = await validator._check_dependencies(callback=events.append)
    assert result["installed"] == ["flask==3.0", "requests>=2"]
    assert result["missing"] == ["missing-pkg<=1"]
    assert json.loads(events[-1])["type"] == "validation_progress"

    async def boom(path, encoding="utf-8"):
        raise OSError("read fail")

    monkeypatch.setattr(agent_core, "_read_text_async", boom)
    result = await validator._check_dependencies()
    assert result["error"] == "read fail"


@pytest.mark.asyncio
async def test_check_project_structure_all_present(tmp_path):
    for name in ["README.md", "main.py", "setup.py"]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    validator = ProjectValidator(tmp_path, _config())
    events = []
    result = await validator._check_project_structure(callback=events.append)
    assert result["has_readme"] is True
    assert result["has_main"] is True
    assert result["has_setup"] is True
    assert result["has_tests"] is True
    assert result["structure_issues"] == []
    assert json.loads(events[-1])["type"] == "validation_progress"


@pytest.mark.asyncio
async def test_check_project_structure_missing(tmp_path):
    validator = ProjectValidator(tmp_path, _config())
    result = await validator._check_project_structure()
    assert "缺少README文档" in result["structure_issues"]
    assert "未找到主程序文件" in result["structure_issues"]


@pytest.mark.asyncio
async def test_check_entrypoint_variants(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text(
        'if __name__ == "__main__":\n    print("x")\n', encoding="utf-8"
    )
    validator = ProjectValidator(tmp_path, _config())
    events = []
    result = await validator._check_entrypoint(callback=events.append)
    assert result["executable"] is True
    assert result["entrypoint_file"] == "main.py"
    assert json.loads(events[-1])["type"] == "validation_progress"

    (tmp_path / "main.py").unlink()
    (tmp_path / "app.py").write_text("print('x')\n", encoding="utf-8")
    result = await validator._check_entrypoint()
    assert result["entrypoint_file"] == "app.py"
    assert result["executable"] is False

    (tmp_path / "app.py").unlink()
    result = await validator._check_entrypoint()
    assert result["entrypoint_found"] is False
    assert "未找到项目入口点文件" in result["issues"]

    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")

    async def boom(path, encoding="utf-8"):
        raise OSError("denied")

    monkeypatch.setattr(agent_core, "_read_text_async", boom)
    result = await validator._check_entrypoint()
    assert any("检查入口点失败" in i for i in result["issues"])


@pytest.mark.asyncio
async def test_validation_callbacks_swallow_errors(tmp_path, monkeypatch):
    validator = ProjectValidator(tmp_path, _config())
    errors = []
    monkeypatch.setattr(agent_core.logger, "error", lambda msg: errors.append(msg))

    def bad_callback(msg):
        raise RuntimeError("client gone")

    await validator._send_progress_callback(bad_callback, "msg", {})
    await validator._send_validation_callback(
        bad_callback, {"runnable": True, "errors": [], "warnings": []}
    )
    assert len(errors) == 2

    # 无回调时直接返回
    await validator._send_progress_callback(None, "msg", {})
    await validator._send_validation_callback(
        None, {"runnable": True, "errors": [], "warnings": []}
    )


# ==================== create_project_file / list_directory ====================


@pytest.mark.asyncio
async def test_create_project_file_skips_existing_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "projects" / "demo" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("old", encoding="utf-8")

    result = await create_project_file(
        "projects/demo/main.py", "new", output_dir="./projects/demo", session_id="s1"
    )
    assert result["status"] == "skipped"
    assert target.read_text(encoding="utf-8") == "old"
    assert "s1" not in agent_core._file_locks


@pytest.mark.asyncio
async def test_create_project_file_overwrite_and_markdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await create_project_file(
        "projects/demo/main.py",
        "```python\nprint('new')\n```",
        overwrite=True,
        output_dir="./projects/demo",
    )
    assert result["status"] == "success"
    assert (tmp_path / "projects/demo/main.py").read_text(encoding="utf-8") == "print('new')"


@pytest.mark.asyncio
async def test_list_directory_tree_and_error(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x", encoding="utf-8")
    (root / "b.txt").write_text("y", encoding="utf-8")
    output = await list_directory(str(root))
    assert "pkg/" in output
    assert "a.py" in output
    assert "b.txt" in output

    def boom(self):
        raise OSError("iter fail")

    monkeypatch.setattr(Path, "iterdir", boom)
    output = await list_directory(str(root))
    assert output.startswith("列出目录失败")


# ==================== validate_file / validate_project 工具 ====================


@pytest.mark.asyncio
async def test_validate_file_tool_missing_and_success(tmp_path):
    missing = await validate_file(str(tmp_path / "missing.py"))
    assert missing["status"] == "error"

    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = await validate_file(str(target))
    assert result["status"] == "success"
    assert result["valid"] is True


@pytest.mark.asyncio
async def test_validate_file_tool_exception(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")

    async def boom(self, path):
        raise RuntimeError("validator broke")

    monkeypatch.setattr(CodeValidator, "validate_python_file", boom)
    result = await validate_file(str(target))
    assert result["status"] == "error"
    assert "validator broke" in result["message"]


@pytest.mark.asyncio
async def test_validate_project_tool_success_and_exception(tmp_path, monkeypatch):
    async def fake_validate(self, callback=None):
        return {
            "runnable": True,
            "errors": [],
            "warnings": ["w"],
            "file_validations": [],
            "dependency_check": {},
            "structure_check": {},
        }

    monkeypatch.setattr(ProjectValidator, "run_full_validation", fake_validate)
    result = await validate_project(str(tmp_path))
    assert result["status"] == "success"
    assert result["runnable"] is True

    async def boom(self, callback=None):
        raise RuntimeError("project broke")

    monkeypatch.setattr(ProjectValidator, "run_full_validation", boom)
    result = await validate_project(str(tmp_path))
    assert result["status"] == "error"


# ==================== 同步文件工具 ====================


@pytest.fixture()
def project(tmp_path, monkeypatch):
    # FileOperator 默认把 /tmp 列为受保护路径；pytest 的临时目录位于 /tmp，
    # 这里解除该限制以便在隔离目录中验证文件工具。
    monkeypatch.setattr(
        agent_core.FileOperator,
        "PROTECTED_PATHS",
        agent_core.FileOperator.PROTECTED_PATHS - {"/tmp"},
    )
    monkeypatch.chdir(tmp_path)
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "main.py").write_text("import os\nprint('hello')\n", encoding="utf-8")
    return "demo"


def test_project_file_manager_validation(project, tmp_path, monkeypatch):
    monkeypatch.setattr(
        agent_core.FileOperator,
        "PROTECTED_PATHS",
        agent_core.FileOperator.PROTECTED_PATHS - {"/tmp"},
    )
    assert ProjectFileManager(project).project_path == project
    with pytest.raises(FileNotFoundError):
        ProjectFileManager("missing")
    with pytest.raises(PermissionError):
        ProjectFileManager("../escape")
    assert _resolve_project_write_path("projects/demo/main.py") == (
        tmp_path / "projects" / "demo" / "main.py"
    ).resolve()


def test_sync_file_tools_success(project):
    names = {e["name"] for e in list_files(project)["entries"]}
    assert "main.py" in names
    assert project_tree(project)["project"] == project
    assert project_stats(project)["project"] == project

    assert create_file(project, "new.py", content="x = 1\n")["success"] is True
    assert read_file(project, "new.py")["content"] == "x = 1\n"
    assert edit_file(project, "new.py", "y = 2\n")["success"] is True
    assert (Path("projects/demo/new.py")).read_text(encoding="utf-8") == "y = 2\n"

    assert grep_files(project, "hello")["matched_files"] == 1
    assert search_files(project, "hello")["matches_found"] == 1

    assert rename_file(project, "new.py", "renamed.py")["success"] is True
    assert delete_file(project, "renamed.py")["deleted"] is True


def test_sync_file_tools_error_paths(project):
    assert "error" in read_file(project, "missing.py")
    assert "error" in edit_file(project, "bad.bin", "x")
    assert "error" in create_file(project, "main.py")
    assert "error" in rename_file(project, "main.py", "main.py")
    assert "error" in delete_file(project, "missing.py")
    assert "error" in search_files(project, "[")
    # 文件类型过滤不匹配时返回空结果而非错误
    filtered = grep_files(project, "hello", file_types=".nope")
    assert filtered["matched_files"] == 0


def test_sync_file_tools_guard_error_paths(project, monkeypatch):
    from app.utils.file_operator import PathSecurityError

    def raise_path_security(*args, **kwargs):
        raise PathSecurityError("blocked")

    for method in ["grep", "tree", "stats"]:
        monkeypatch.setattr(agent_core.FileOperator, method, raise_path_security)
    assert "error" in grep_files(project, "hello")
    assert "error" in project_tree(project)
    assert "error" in project_stats(project)

    def raise_not_a_dir(*args, **kwargs):
        raise NotADirectoryError("not dir")

    monkeypatch.setattr(agent_core.FileOperator, "list_dir", raise_not_a_dir)
    assert "error" in list_files(project)


def test_project_file_manager_resolve_path(project):
    manager = ProjectFileManager(project)
    assert manager._resolve_path("main.py").name == "main.py"
    assert ProjectFileManager().project_path is None


def test_list_relative_files_skips_directories(tmp_path):
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "f.py").write_text("x", encoding="utf-8")
    assert _list_relative_files(tmp_path / "dir") == ["f.py"]


# ==================== 补充边界分支 ====================


def test_cached_installed_packages_failure(monkeypatch):
    from app.utils.agent_core import _cached_installed_packages

    _cached_installed_packages.cache_clear()

    def boom(cmd, **kwargs):
        raise OSError("pip missing")

    monkeypatch.setattr(agent_core.subprocess, "run", boom)
    assert _cached_installed_packages() == frozenset()
    _cached_installed_packages.cache_clear()


@pytest.mark.asyncio
async def test_set_history_on_fresh_session_and_within_limit():
    mgr = ConversationHistoryManager()
    await mgr.set_history("fresh", [{"role": "user", "content": "x"}])
    assert (await mgr.get_history("fresh"))[0]["content"] == "x"

    mgr2 = ConversationHistoryManager()
    mgr2.MAX_MESSAGES_PER_SESSION = 5
    await mgr2.set_history("s", [{"i": 1}])
    assert [m["i"] for m in await mgr2.get_history("s")] == [1]


def test_file_model_router_frontend_and_unknown():
    router = FileModelRouter()
    router.frontend_model = "FRONT"
    router.backend_model = "BACK"
    assert router.get_model_for_file("app.vue") == "FRONT"
    assert router.get_model_for_file("notes.unknownext") == "FRONT"
    assert router.get_model_for_file("service.py") == "BACK"


@pytest.mark.asyncio
async def test_imports_importable_paths(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text(
        "import os\nfrom json import loads\nimport sys\nfrom pathlib import Path\nfrom . import sibling\n",
        encoding="utf-8",
    )
    validator = CodeValidator(tmp_path, _config())
    # 走 _is_importable 返回 True 的分支，并确保 not in stdlib 的嵌套判定也被执行
    monkeypatch.setattr(validator, "_is_importable", lambda name: name != "sys")
    result = await validator._validate_imports(target)
    assert result.success is True


def test_security_eval_without_args_and_non_literal():
    validator = object.__new__(CodeValidator)

    async def run(source):
        return await validator._validate_security(_write_tmp(source))

    with_args = asyncio.run(run("eval(code)\n"))
    assert not any("直接执行字符串代码" in w for w in with_args.warnings)
    no_args = asyncio.run(run("exec()\n"))
    assert not any("直接执行字符串代码" in w for w in no_args.warnings)


def _write_tmp(source: str) -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    handle.write(source)
    handle.close()
    return Path(handle.name)


def test_unused_imports_from_and_assign_variants():
    validator = object.__new__(CodeValidator)
    tree = ast.parse(
        "from os import path as p\nimport sys\nx: int = 1\nx = 2\n"
    )
    issues = validator._check_unused_imports(tree)
    assert any("未使用的导入: p" in i for i in issues)
    assert validator._check_undefined_variables(ast.parse("def f(a):\n    return a + b\n"))


def test_undefined_variables_assignment_targets():
    validator = object.__new__(CodeValidator)
    # 属性赋值（ast.Attribute）不走 Name 分支，Name 作为 Store 也不应报未定义
    tree = ast.parse("obj.attr = 1\nvalue = missing\n")
    issues = validator._check_undefined_variables(tree)
    assert any("missing" in i for i in issues)
    assert not any("attr" in i for i in issues)


def test_syntax_warnings_compare_variants():
    validator = object.__new__(CodeValidator)
    # 左侧不是常量
    assert "常量比较可能总是True或False" not in validator._check_syntax_warnings(
        ast.parse("x = 1\nif x == 1:\n    pass\n")
    )
    # 左侧常量，右侧非常量
    assert "常量比较可能总是True或False" not in validator._check_syntax_warnings(
        ast.parse("x = 1\nif 1 == x:\n    pass\n")
    )


def test_syntax_warnings_loop_with_attribute_target():
    validator = object.__new__(CodeValidator)
    warnings = validator._check_syntax_warnings(
        ast.parse("for obj.attr in range(3):\n    pass\n")
    )
    assert not any("循环变量" in w for w in warnings)
