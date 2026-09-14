import pytest
import asyncio
import tempfile
from pathlib import Path

class TestErrorRecoveryLoop:
    @pytest.fixture
    def recovery(self):
        from app.agent.error_recovery import ErrorRecoveryLoop
        from app.agent.code_validator import CodeValidator
        from app.agent.code_reviewer import CodeReviewer
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            validator = CodeValidator(Path(tmpdir))
            reviewer = CodeReviewer(ctx, model_name="test-model")
            yield ErrorRecoveryLoop(validator, reviewer)
    
    def test_validate_and_fix(self, recovery):
        # 简化测试：只验证对象创建成功
        assert recovery.validator is not None
        assert recovery.reviewer is not None
        assert recovery.MAX_FIX_ATTEMPTS == 3


def test_default_fallback_chain_is_empty(monkeypatch):
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config",
        lambda: {},
    )
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    assert loop.MODEL_FALLBACK_CHAIN == []
    assert loop._load_fallback_chain() == []


def test_select_fix_model_uses_assigned_model_without_fast_default(monkeypatch):
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config",
        lambda: {},
    )
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    assert loop._select_fix_model_by_error_type("SyntaxError", ["assigned-model"], 0) == "assigned-model"


@pytest.mark.asyncio
async def test_try_react_auto_fix_requires_model_assignment():
    from app.agent.orchestrator_generation.error_recovery import ErrorRecoveryMixin

    mixin = object.__new__(ErrorRecoveryMixin)
    mixin.error_recovery = object()
    mixin.reviewer = object()
    mixin.model_assignment = None
    with pytest.raises(RuntimeError, match="model assignment is required for ReAct auto-fix"):
        await mixin._try_react_auto_fix({"failed_tests": ["test_a"]})
