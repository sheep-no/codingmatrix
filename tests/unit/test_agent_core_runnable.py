"""`agent_core.ProjectValidator.run_full_validation` 的 runnable 汇总测试。

原实现只用文件验证的 issues 决定 runnable，依赖缺失与无入口点都被忽略，
导致「可运行」谎报。修复后缺少依赖、依赖检查失败、入口点问题都计入错误，
结构问题（如缺 README）只作为警告。
"""
import pytest

from app.utils.agent_core import ProjectValidator


def _validator(**checks):
    """构造一个只带桩检查方法的 ProjectValidator 实例，绕过 __init__ 的 pip 探测。"""
    pv = object.__new__(ProjectValidator)
    defaults = {
        "file_validations": [],
        "dependency_check": {"has_requirements": True, "missing": []},
        "structure_check": {"structure_issues": []},
        "entrypoint_check": {"entrypoint_found": True, "issues": []},
    }
    defaults.update(checks)

    async def _files(callback=None):
        return defaults["file_validations"]

    async def _deps(callback=None):
        return defaults["dependency_check"]

    async def _structure(callback=None):
        return defaults["structure_check"]

    async def _entry(callback=None):
        return defaults["entrypoint_check"]

    pv._validate_all_files = _files
    pv._check_dependencies = _deps
    pv._check_project_structure = _structure
    pv._check_entrypoint = _entry
    return pv


@pytest.mark.asyncio
async def test_all_clean_is_runnable():
    result = await _validator().run_full_validation()
    assert result["runnable"] is True


@pytest.mark.asyncio
async def test_missing_dependency_blocks_runnable():
    result = await _validator(
        dependency_check={"has_requirements": True, "missing": ["flask==3.0"]},
    ).run_full_validation()
    assert result["runnable"] is False
    assert any("flask==3.0" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_missing_entrypoint_blocks_runnable():
    result = await _validator(
        entrypoint_check={"entrypoint_found": False, "issues": ["未找到项目入口点文件"]},
    ).run_full_validation()
    assert result["runnable"] is False
    assert "未找到项目入口点文件" in result["errors"]


@pytest.mark.asyncio
async def test_structure_issue_is_warning_only():
    result = await _validator(
        structure_check={"structure_issues": ["缺少README文档"]},
    ).run_full_validation()
    assert result["runnable"] is True
    assert "缺少README文档" in result["warnings"]
