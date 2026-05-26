import pytest
import tempfile
from pathlib import Path

class TestSpecCache:
    @pytest.fixture
    def cache(self):
        from app.agent.spec_cache import SpecCache
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SpecCache(Path(tmpdir))
    
    def test_save_and_lookup(self, cache):
        requirement = "Create a REST API"
        specs = {"complexity": {"level": "medium"}}
        architecture = {"tech_stack": ["fastapi"]}
        file_plan = [{"path": "main.py"}]
        
        cache.save(requirement, specs, architecture, file_plan, {"level": "medium"}, ["fastapi"])
        
        result = cache.lookup(requirement)
        assert result is not None
        assert result.architecture is not None
    
    def test_cache_miss(self, cache):
        result = cache.lookup("nonexistent requirement")
        assert result is None
