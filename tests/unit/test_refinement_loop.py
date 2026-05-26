import pytest
import asyncio
import tempfile
from pathlib import Path

class TestRefinementLoop:
    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            yield RefinementLoop(ctx)
    
    def test_refine_success(self, loop):
        initial_content = "def hello(): pass"
        
        result = asyncio.run(loop.refine(
            file_path="test.py",
            file_type="backend",
            description="test",
            initial_content=initial_content,
            model_name="test-model",
            project_context={}
        ))
        
        assert result is not None
        assert hasattr(result, 'final_content')
        assert hasattr(result, 'success')
        assert hasattr(result, 'attempts')
