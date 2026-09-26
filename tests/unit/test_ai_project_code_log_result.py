"""回归测试：log_generation_result 不得吞掉记录失败。

原实现在 ``finally`` 中 ``break``，会抑制 try 体内抛出的异常，
使外层 ``except`` 永不触发、记录失败被静默忽略。
"""

import pytest

import app.api.v1.AiProjectCode as aipc
import app.db.database as db_module


async def _fake_get_db():
    yield object()


async def _run_log_generation_result():
    await aipc.log_generation_result(
        session_id="s-1",
        user_id=1,
        model_key="m-1",
        requirement="req",
        output_dir="out",
        result={},
        success=True,
        execution_time=0.1,
    )


class TestLogGenerationResult:
    @pytest.mark.asyncio
    async def test_operation_failure_is_logged_not_swallowed(self, monkeypatch):
        async def boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(db_module, "get_db", _fake_get_db)
        monkeypatch.setattr(aipc, "log_tool_execution", boom)
        monkeypatch.setattr(aipc, "update_model_stats", boom)
        monkeypatch.setattr(aipc, "accumulate_knowledge", boom)

        errors = []
        monkeypatch.setattr(aipc.logger, "error", lambda msg, *a, **k: errors.append(msg))

        await _run_log_generation_result()

        assert errors, "记录失败必须被记录，不能被 finally 中的 break 吞掉"
        assert "记录生成结果失败" in errors[0]

    @pytest.mark.asyncio
    async def test_all_operations_run_once_on_success(self, monkeypatch):
        calls = {"tool": 0, "stats": 0, "knowledge": 0}

        async def tool(*args, **kwargs):
            calls["tool"] += 1

        async def stats(*args, **kwargs):
            calls["stats"] += 1

        async def knowledge(*args, **kwargs):
            calls["knowledge"] += 1

        monkeypatch.setattr(db_module, "get_db", _fake_get_db)
        monkeypatch.setattr(aipc, "log_tool_execution", tool)
        monkeypatch.setattr(aipc, "update_model_stats", stats)
        monkeypatch.setattr(aipc, "accumulate_knowledge", knowledge)

        await _run_log_generation_result()

        assert calls == {"tool": 1, "stats": 1, "knowledge": 1}

    @pytest.mark.asyncio
    async def test_failure_stops_subsequent_operations(self, monkeypatch):
        invoked = []

        async def boom(*args, **kwargs):
            invoked.append("tool")
            raise RuntimeError("db down")

        async def should_not_run(*args, **kwargs):
            invoked.append("later")

        monkeypatch.setattr(db_module, "get_db", _fake_get_db)
        monkeypatch.setattr(aipc, "log_tool_execution", boom)
        monkeypatch.setattr(aipc, "update_model_stats", should_not_run)
        monkeypatch.setattr(aipc, "accumulate_knowledge", should_not_run)
        monkeypatch.setattr(aipc.logger, "error", lambda msg, *a, **k: None)

        await _run_log_generation_result()

        assert invoked == ["tool"]
