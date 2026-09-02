import pytest
import asyncio
from pathlib import Path
import tempfile
import os

class TestCodeValidator:
    @pytest.fixture
    def validator(self):
        from app.agent.code_validator import CodeValidator
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CodeValidator(Path(tmpdir))
    
    def test_compute_content_hash(self):
        from app.agent.code_validator import CodeValidator
        content1 = "test content"
        content2 = "test content"
        content3 = "different content"
        
        hash1 = CodeValidator._compute_content_hash(content1)
        hash2 = CodeValidator._compute_content_hash(content2)
        hash3 = CodeValidator._compute_content_hash(content3)
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 16
    
    def test_cache_validation(self, validator):
        content = "print('hello')"
        result = {"is_valid": True, "syntax_errors": []}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            f.flush()
            file_path = Path(f.name)
        
        try:
            validator.cache_validation(file_path, result)
            cached = validator.get_cached_validation(file_path)
            assert cached is not None
            assert cached["is_valid"] is True
        finally:
            os.unlink(file_path)
    
    def test_get_cache_stats(self, validator):
        stats = validator.get_cache_stats()
        assert "entries" in stats
        assert "size_bytes" in stats
        assert "hit_rate" in stats

    @pytest.mark.asyncio
    async def test_single_file_validation_resolves_sibling_generated_module(self, validator):
        project_path = validator.project_path
        (project_path / "todo.py").write_text("VALUE = 1\n", encoding="utf-8")
        candidate = project_path / ".temp_main.py"
        candidate.write_text("from todo import VALUE\n", encoding="utf-8")

        result = await validator.validate_single_file(candidate)

        assert result["is_valid"] is True

class TestCodeValidatorLRU:
    def test_lru_cache_limit(self):
        from app.agent.code_validator import CodeValidator
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = CodeValidator(Path(tmpdir))
            validator._max_cache_bytes = 1024 * 1024  # 1MB for testing
            
            for i in range(20):
                content = f"print({i})" * 50
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(content)
                    f.flush()
                    file_path = Path(f.name)
                
                validator.cache_validation(file_path, {"is_valid": True})
                os.unlink(file_path)
            
            stats = validator.get_cache_stats()
            assert stats["size_bytes"] <= validator._max_cache_bytes * 1.1
