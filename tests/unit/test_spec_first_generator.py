import pytest
import tempfile
from pathlib import Path

class TestSpecFirstGenerator:
    @pytest.fixture
    def generator(self):
        from app.agent.spec_first_generator import SpecFirstGenerator
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            yield SpecFirstGenerator(ctx)
    
    def test_get_spec_context_for_file(self, generator):
        from app.agent.shared_context import SpecArtifact
        
        generator.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi",
            content={"paths": {"/users": {}}},
            generated_by="test-model"
        )
        
        context = generator.get_spec_context_for_file("api.py", "backend")
        assert context is not None
