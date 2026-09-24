"""ErrorRecoveryLoop 回归：ERL3 临时文件泄漏、ERL4 成本未记录、ERL6 修复写盘、ERL7 死代码。"""

import json
from pathlib import Path

import pytest


def _loop(**kwargs):
    from app.agent.error_recovery import ErrorRecoveryLoop

    return ErrorRecoveryLoop(validator=kwargs.pop("validator", object()), reviewer=object(), **kwargs)


class TestQualityTempFileCleanup:
    """ERL3: validate_single_file 抛异常时不得残留 .temp_quality_*"""

    async def test_temp_file_removed_on_exception(self, tmp_path):
        from app.agent.error_recovery import ErrorRecoveryLoop

        class BoomValidator:
            async def validate_single_file(self, file_path):
                raise RuntimeError("校验器崩溃")

        loop = ErrorRecoveryLoop(validator=BoomValidator(), reviewer=object())
        target = tmp_path / "main.py"
        target.write_text("print(1)\n", encoding="utf-8")

        score = await loop._evaluate_code_quality("print(1)\n", target)

        assert score == 0.5
        assert list(tmp_path.glob(".temp_quality_*")) == []


class TestCostRecording:
    """ERL4: 修复循环的 call_llm 消耗需计入 cost_tracker"""

    def test_records_usage_when_tracker_present(self):
        calls = []

        class FakeTracker:
            def add_usage(self, model, prompt_tokens, completion_tokens, cost_usd=0.0):
                calls.append((model, prompt_tokens, completion_tokens, cost_usd))

        loop = _loop(cost_tracker=FakeTracker())
        loop._record_llm_cost(
            {"usage": {"prompt_tokens": 1000, "completion_tokens": 2000}},
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        )

        assert len(calls) == 1
        model, pt, ct, cost = calls[0]
        assert (pt, ct) == (1000, 2000)
        # 单价 1.0/4.0（每百万）→ 1000*1 + 2000*4 = 9000 / 1e6
        assert cost == pytest.approx(0.009)

    def test_noop_without_tracker(self):
        loop = _loop()
        loop._record_llm_cost({"usage": {"prompt_tokens": 1, "completion_tokens": 1}}, "m")

    def test_skips_when_usage_missing(self):
        calls = []

        class FakeTracker:
            def add_usage(self, *args, **kwargs):
                calls.append(args)

        loop = _loop(cost_tracker=FakeTracker())
        loop._record_llm_cost({"choices": []}, "m")
        loop._record_llm_cost("not-a-dict", "m")
        assert calls == []


class _Result:
    def __init__(self, success):
        self.success = success
        self.failed_tests = []
        self.logs = ""


class _Runner:
    def __init__(self, success=False):
        self._success = success
        self.calls = 0

    async def run_tests(self):
        self.calls += 1
        return _Result(self._success)


class TestFixFromTestLogsWrite:
    """ERL6: 修复内容需先校验再原子写，坏内容不得覆盖源文件"""

    async def _run(self, monkeypatch, tmp_path, content):
        from app.agent import error_recovery as er_mod

        async def fake_call_llm(**kwargs):
            return {
                "choices": [{"message": {"content": json.dumps([
                    {"file_path": "app/service.py", "content": content}
                ])}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }

        monkeypatch.setattr(er_mod, "call_llm", fake_call_llm)
        loop = er_mod.ErrorRecoveryLoop(object(), object())
        loop.MODEL_FALLBACK_CHAIN = ["model-x"]
        target = tmp_path / "app" / "service.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original = 1\n", encoding="utf-8")

        runner = _Runner(success=True)
        result = await loop.fix_from_test_logs(
            runner, ["test_service::test_x"], "log", tmp_path
        )
        return loop, target, result, runner

    async def test_invalid_content_not_written(self, monkeypatch, tmp_path):
        content = json.dumps({"status": "ok", "message": "done"})
        loop, target, result, runner = await self._run(monkeypatch, tmp_path, content)

        assert target.read_text(encoding="utf-8") == "original = 1\n"
        assert loop.fix_history == []
        # 无有效修复写入 → 仍需重跑测试确认，但源文件未被污染
        assert result["success"] is True

    async def test_valid_content_written_via_atomic(self, monkeypatch, tmp_path):
        content = "def fixed():\n    return 42\n"
        loop, target, result, runner = await self._run(monkeypatch, tmp_path, content)

        assert target.read_text(encoding="utf-8") == content
        assert len(loop.fix_history) == 1
        assert loop.fix_history[0].fix_applied is True
        # 原子写不留下临时文件
        assert list((tmp_path / "app").glob("*.tmp.*")) == []


def test_infer_source_files_dead_code_removed():
    """ERL7: 零消费的 _infer_source_files 已删除"""
    loop = _loop()
    assert not hasattr(loop, "_infer_source_files")
