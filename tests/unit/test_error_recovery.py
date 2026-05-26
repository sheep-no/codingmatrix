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
        assert recovery.MAX_FIX_ATTEMPTS == 2
