"""ErrorRecoveryMixin._try_react_auto_fix 的门控与超时（ERR4/ERR5）。

回归的缺陷：
- `self.error_recovery` 是构造出来的对象、恒为真值，真正的开关
  `enable_error_recovery` 被忽略，关掉开关仍会走 ReAct 修复路径；
- 修复路径没有总超时，engine 只做每轮心跳超时，5 轮可阻塞近一小时。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent.orchestrator_generation import error_recovery as er_module
from app.agent.orchestrator_generation.error_recovery import ErrorRecoveryMixin


class _FakeProcess:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def __call__(self, task, context):
        self.calls.append((task, context))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if isinstance(self.outcome, float):
            await asyncio.sleep(self.outcome)
        return SimpleNamespace(success=True)


def _make_mixin(monkeypatch, outcome=None, **attrs):
    """构造一个只带 mixin 所需属性的对象，并替换 ReActAgent/IsolatedTestRunner。"""
    from app.agent import react_agent as react_agent_module
    from app.agent import test_runner as test_runner_module

    process = _FakeProcess(outcome)

    class _FakeReActAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    _FakeReActAgent.process = staticmethod(process)

    class _FakeRunner:
        def __init__(self, output_dir):
            self.output_dir = output_dir

    monkeypatch.setattr(react_agent_module, "ReActAgent", _FakeReActAgent)
    monkeypatch.setattr(react_agent_module, "ReActResult", SimpleNamespace)
    monkeypatch.setattr(test_runner_module, "IsolatedTestRunner", _FakeRunner)

    obj = ErrorRecoveryMixin()
    obj.error_recovery = object()
    obj.reviewer = object()
    obj.model_assignment = SimpleNamespace(backend_model="test-model")
    obj.output_dir = "/tmp/proj"
    obj.enable_error_recovery = True
    for key, value in attrs.items():
        setattr(obj, key, value)

    async def _run_dynamic_tests(runner):
        return {"success": True, "summary": "ok"}

    obj._run_dynamic_tests = _run_dynamic_tests
    return obj, process


@pytest.mark.asyncio
async def test_disabled_flag_skips_react_fix(monkeypatch):
    obj, process = _make_mixin(monkeypatch, enable_error_recovery=False)

    result = await obj._try_react_auto_fix({"failed_tests": ["t"]})

    assert result is None
    assert process.calls == []


@pytest.mark.asyncio
async def test_missing_reviewer_skips_react_fix(monkeypatch):
    obj, process = _make_mixin(monkeypatch, reviewer=None)

    assert await obj._try_react_auto_fix({"failed_tests": ["t"]}) is None
    assert process.calls == []


@pytest.mark.asyncio
async def test_no_failed_tests_skips_react_fix(monkeypatch):
    obj, process = _make_mixin(monkeypatch)

    assert await obj._try_react_auto_fix({"failed_tests": []}) is None
    assert process.calls == []


@pytest.mark.asyncio
async def test_success_path_passes_project_path_and_reruns_tests(monkeypatch):
    obj, process = _make_mixin(monkeypatch)

    result = await obj._try_react_auto_fix({"failed_tests": ["t1", "t2"], "logs_preview": "log"})

    assert result == {"fixed": True, "test_results": {"success": True, "summary": "ok"}}
    # ERR1 的上游修复：context 的 project_path 会被 ReActAgent.process 消费
    assert process.calls[0][1] == {"project_path": "/tmp/proj"}


@pytest.mark.asyncio
async def test_missing_model_assignment_raises(monkeypatch):
    obj, _ = _make_mixin(monkeypatch, model_assignment=None)

    with pytest.raises(RuntimeError, match="model assignment"):
        await obj._try_react_auto_fix({"failed_tests": ["t"]})


@pytest.mark.asyncio
async def test_process_failure_wrapped_in_runtime_error(monkeypatch):
    obj, _ = _make_mixin(monkeypatch, outcome=ValueError("boom"))

    with pytest.raises(RuntimeError, match="react auto-fix failed"):
        await obj._try_react_auto_fix({"failed_tests": ["t"]})


@pytest.mark.asyncio
async def test_total_timeout_bounds_repair_path(monkeypatch):
    obj, _ = _make_mixin(monkeypatch, outcome=1.0)
    monkeypatch.setattr(er_module, "REACT_AUTO_FIX_TIMEOUT", 0.01)

    with pytest.raises(RuntimeError, match="timed out"):
        await obj._try_react_auto_fix({"failed_tests": ["t"]})
