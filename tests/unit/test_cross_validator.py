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
        # priority=1 自动触发
        assert validator.is_critical_file("auth.py", "backend", priority=1) is True
        # priority<=2 且命中模式
        assert validator.is_critical_file("permission.py", "backend", priority=2) is True
        assert validator.is_critical_file("payment.py", "backend", priority=2) is True
        # priority>2 即使命中模式也不触发
        assert validator.is_critical_file("auth.py", "backend", priority=3) is False
        # 不命中模式
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


def test_select_llm_fix_issues_caps_and_prioritizes_imports():
    from app.agent.cross_validator import select_llm_fix_issues

    issues = [
        {"type": "symbol_not_found", "file": f"f{i}.py", "message": f"missing {i}"}
        for i in range(40)
    ]
    issues.insert(0, {"type": "import_error", "file": "main.py", "message": "no app.main"})
    issues.insert(1, {"type": "import_error", "file": "main.py", "message": "no app.main"})

    selected = select_llm_fix_issues(issues, max_issues=20, max_files=6)

    assert len(selected) <= 20
    assert len({item["file"] for item in selected}) <= 6
    assert selected[0]["type"] == "import_error"
    assert selected[0]["file"] == "main.py"
    assert sum(1 for item in selected if item["message"] == "no app.main") == 1
