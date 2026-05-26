import pytest
import asyncio
import tempfile
from pathlib import Path

class TestCrossValidator:
    @pytest.fixture
    def validator(self):
        from app.agent.cross_validator import CrossValidator
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            yield CrossValidator(ctx)
    
    def test_is_critical_file(self, validator):
        assert validator.is_critical_file("auth.py", "backend") is True
        assert validator.is_critical_file("permission.py", "backend") is True
        assert validator.is_critical_file("payment.py", "backend") is True
        assert validator.is_critical_file("utils.py", "backend") is False
        assert validator.is_critical_file("README.md", "docs") is False
    
    def test_validate_and_select(self, validator):
        version_a = "def hello():\n    return 'A'"
        version_b = "def hello():\n    return 'B'"
        
        result, winner = asyncio.run(validator.validate_and_select(
            file_path="test.py",
            file_type="backend",
            description="test function",
            version_a=version_a,
            model_a="model-a",
            version_b=version_b,
            model_b="model-b",
            judge_model="judge-model"
        ))
        
        assert result in [version_a, version_b]
        assert winner in ["model-a", "model-b"]
