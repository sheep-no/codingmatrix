"""CodeValidator 全项目校验的阻塞 I/O 必须离开事件循环。

`validate_cross_file_consistency`（rglob 全项目 + 读取并 AST 解析每个 .py）
与 `run_full_validation` 的缓存键计算（读取全项目内容后哈希）都是纯阻塞操作，
若直接在协程里执行会占住事件循环，使 `asyncio.gather` 的并发校验退化为串行。
这里用线程 id 断言两者都在工作线程中执行。
"""

import threading

import pytest

from app.agent.code_validator import CodeValidator


def _make_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (project / "helper.py").write_text("VALUE = 2\n", encoding="utf-8")
    return project


@pytest.mark.asyncio
async def test_cross_file_consistency_runs_off_event_loop(tmp_path):
    project = _make_project(tmp_path)
    main_thread = threading.get_ident()
    seen = {}

    class RecordingValidator(CodeValidator):
        def _validate_cross_file_consistency_sync(self):
            seen["thread"] = threading.get_ident()
            return super()._validate_cross_file_consistency_sync()

    ok, errors = await RecordingValidator(project).validate_cross_file_consistency()

    assert seen.get("thread") is not None, "同步实现未被调用"
    assert seen["thread"] != main_thread, "跨文件校验仍在事件循环线程执行"
    assert ok is True
    assert errors == []


@pytest.mark.asyncio
async def test_run_full_validation_hashes_project_off_event_loop(tmp_path):
    project = _make_project(tmp_path)
    main_thread = threading.get_ident()
    seen = {}

    class RecordingValidator(CodeValidator):
        @classmethod
        def _project_content_hash(cls, files):
            seen["thread"] = threading.get_ident()
            seen["count"] = len(files)
            return super()._project_content_hash(files)

    result = await RecordingValidator(project).run_full_validation()

    assert seen.get("thread") is not None, "项目内容哈希未被执行"
    assert seen["thread"] != main_thread, "项目内容哈希仍在事件循环线程执行"
    assert seen["count"] >= 2
    assert result["validated_files"] >= 2
    assert result["cache_hit"] is False


@pytest.mark.asyncio
async def test_run_full_validation_cache_hit_still_works(tmp_path):
    project = _make_project(tmp_path)
    validator = CodeValidator(project)

    first = await validator.run_full_validation()
    second = await validator.run_full_validation()

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
