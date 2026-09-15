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

    @pytest.mark.asyncio
    async def test_validate_imports_skips_relative_imports(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "services.py"
        target.write_text(
            "from .models import Item\nfrom ..shared import util\n\nVALUE = 1\n",
            encoding="utf-8",
        )

        ok, errors = await validator.validate_imports(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_imports_ignores_docstring_examples(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "docs.py"
        target.write_text(
            '"""\nUsage:\n    import def_not_installed_lib\n    from other_missing import x\n"""\n'
            "\nVALUE = 1\n",
            encoding="utf-8",
        )

        ok, errors = await validator.validate_imports(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_imports_still_flags_missing_module(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "bad.py"
        target.write_text("import definitely_not_installed_lib_xyz\n", encoding="utf-8")

        ok, errors = await validator.validate_imports(target)

        assert ok is False
        assert any("definitely_not_installed_lib_xyz" in err for err in errors)

    @pytest.mark.asyncio
    async def test_runtime_imports_ignore_environment_errors(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "env_required.py"
        target.write_text(
            'import os\n\nDB_URL = os.environ["AGENT_TEST_MISSING_ENV"]\n',
            encoding="utf-8",
        )

        ok, errors = await validator.validate_runtime_imports(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_api_compatibility_allows_app_level_exception_handler(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "main.py"
        target.write_text(
            "from fastapi import APIRouter, FastAPI\n\n"
            "router = APIRouter()\n"
            "app = FastAPI()\n\n"
            "@app.exception_handler(Exception)\n"
            "async def handler(request, exc):\n    return None\n",
            encoding="utf-8",
        )

        ok, errors = await validator.validate_api_compatibility(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_api_compatibility_flags_router_exception_handler(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "routes.py"
        target.write_text(
            "from fastapi import APIRouter\n\nrouter = APIRouter()\nrouter.exception_handler(Exception)\n",
            encoding="utf-8",
        )

        ok, errors = await validator.validate_api_compatibility(target)

        assert ok is False
        assert any("exception_handler" in err for err in errors)

    @pytest.mark.asyncio
    async def test_css_braces_inside_strings_and_comments_are_ignored(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "styles.css"
        target.write_text(
            '/* } */\nbody::after {\n  content: "}";\n}\n',
            encoding="utf-8",
        )

        ok, errors = await validator.validate_css_syntax(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_css_unbalanced_braces_still_flagged(self, tmp_path):
        from app.agent.code_validator import CodeValidator
        validator = CodeValidator(tmp_path)
        target = tmp_path / "broken.css"
        target.write_text("body {\n  margin: 0;\n", encoding="utf-8")

        ok, errors = await validator.validate_css_syntax(target)

        assert ok is False
        assert any("大括号不匹配" in err for err in errors)

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
