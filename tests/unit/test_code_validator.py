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

    @pytest.mark.asyncio
    async def test_js_syntax_signal_kill_is_not_a_syntax_error(self, tmp_path, monkeypatch):
        """node 被信号终止（如 OOM，返回码为负）属环境异常，不能判为语法错误。"""
        import asyncio

        from app.agent.code_validator import CodeValidator

        class _Proc:
            returncode = -9

            async def communicate(self):
                return (b"", b"")

        async def fake_exec(*args, **kwargs):
            return _Proc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        target = tmp_path / "app.js"
        target.write_text("export class App {}\n", encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_js_syntax(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_js_syntax_real_error_still_flagged(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "broken.js"
        target.write_text("const x = ;\n", encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_js_syntax(target)

        assert ok is False
        assert errors

    @pytest.mark.asyncio
    async def test_runtime_imports_survive_shadowing_module_name(self, tmp_path):
        """生成项目与 Agent 自身包同名（app/）时不能解析到 Agent 自己的代码。"""
        import sys
        from app.agent.code_validator import CodeValidator

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "__init__.py").write_text(
            "from .factory import create_app\n", encoding="utf-8"
        )
        (tmp_path / "app" / "factory.py").write_text(
            "def create_app():\n    return None\n", encoding="utf-8"
        )
        target = tmp_path / "main.py"
        target.write_text("from app import create_app\n\napp = create_app()\n", encoding="utf-8")

        Validator = CodeValidator
        validator = Validator(tmp_path)
        backend_app = sys.modules.get("app")
        assert backend_app is not None, "Agent 自身 app 包应在 sys.modules 中"

        ok, errors = await validator.validate_runtime_imports(target)

        assert ok is True, errors
        assert sys.modules["app"] is backend_app

    @pytest.mark.asyncio
    async def test_requirements_skip_manifest_for_non_python_project(self, tmp_path):
        """纯前端工程没有 requirements.txt 不算缺陷。"""
        from app.agent.code_validator import CodeValidator

        (tmp_path / "package.json").write_text('{"name": "demo"}\n', encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.js").write_text("export default 1;\n", encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_requirements()

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_requirements_missing_manifest_still_flagged_for_python_project(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_requirements()

        assert ok is False
        assert any("缺少 requirements.txt" in err for err in errors)

    @pytest.mark.asyncio
    async def test_requirements_uninstalled_package_is_environment_not_defect(self, tmp_path):
        """依赖清单里的包在当前环境未安装，不能判为生成代码无效。"""
        from app.agent.code_validator import CodeValidator

        (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text(
            "definitely_not_installed_pkg_xyz\n", encoding="utf-8"
        )

        ok, errors = await CodeValidator(tmp_path).validate_requirements()

        assert ok is True

    @pytest.mark.asyncio
    async def test_cross_file_accepts_alias_and_reexport_imports(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        (tmp_path / "utils.py").write_text(
            "def helper():\n    return 1\n\n\nclass Thing:\n    pass\n", encoding="utf-8"
        )
        (tmp_path / "config.py").write_text(
            "from .base import settings\n", encoding="utf-8"
        )
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "__init__.py").write_text(
            "from .factory import create_app\n", encoding="utf-8"
        )
        (tmp_path / "app" / "factory.py").write_text(
            "def create_app():\n    return None\n", encoding="utf-8"
        )
        (tmp_path / "main.py").write_text(
            "from utils import helper as h\n"
            "from utils import (helper,\n                   Thing)\n"
            "from config import settings\n"
            "from app import create_app\n"
            "from app.factory import create_app as factory\n",
            encoding="utf-8",
        )

        ok, errors = await CodeValidator(tmp_path).validate_cross_file_consistency()

        assert ok is True, errors

    @pytest.mark.asyncio
    async def test_cross_file_still_flags_missing_symbol(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "__init__.py").write_text(
            "from .factory import create_app\n", encoding="utf-8"
        )
        (tmp_path / "app" / "factory.py").write_text(
            "def create_app():\n    return None\n", encoding="utf-8"
        )
        (tmp_path / "main.py").write_text("from app import nope\n", encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_cross_file_consistency()

        assert ok is False
        assert any("nope" in err for err in errors)

    @pytest.mark.asyncio
    async def test_cross_file_accepts_subpackage_import(self, tmp_path):
        """`from pkg import subpkg` 应解析到 subpkg/__init__.py，而非只找 subpkg.py。"""
        from app.agent.code_validator import CodeValidator

        (tmp_path / "app" / "routers" / "users").mkdir(parents=True)
        (tmp_path / "app" / "__init__.py").write_text('"""pkg"""\n', encoding="utf-8")
        (tmp_path / "app" / "routers" / "__init__.py").write_text('"""pkg"""\n', encoding="utf-8")
        (tmp_path / "app" / "routers" / "users" / "__init__.py").write_text(
            "from .router import router\n", encoding="utf-8"
        )
        (tmp_path / "app" / "routers" / "users" / "router.py").write_text(
            "router = object()\n", encoding="utf-8"
        )
        (tmp_path / "main.py").write_text(
            "from app.routers import users\nfrom app import routers\n", encoding="utf-8"
        )

        ok, errors = await CodeValidator(tmp_path).validate_cross_file_consistency()

        assert ok is True, errors

    @pytest.mark.asyncio
    async def test_cross_file_still_flags_missing_subpackage(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        (tmp_path / "app" / "routers").mkdir(parents=True)
        (tmp_path / "app" / "__init__.py").write_text('"""pkg"""\n', encoding="utf-8")
        (tmp_path / "app" / "routers" / "__init__.py").write_text('"""pkg"""\n', encoding="utf-8")
        (tmp_path / "main.py").write_text(
            "from app.routers import nonexistent\n", encoding="utf-8"
        )

        ok, errors = await CodeValidator(tmp_path).validate_cross_file_consistency()

        assert ok is False
        assert any("nonexistent" in err for err in errors)


class TestHtmlCssStructureGate:
    @pytest.mark.asyncio
    async def test_html5_optional_closing_tags_are_accepted(self, tmp_path):
        """HTML5 允许省略 </head>/</body>，文档以 </html> 结束即合法。"""
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "index.html"
        target.write_text(
            '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <title>x</title>\n'
            "<body>\n  <p>hi</p>\n</html>\n",
            encoding="utf-8",
        )

        ok, errors = await CodeValidator(tmp_path).validate_html_structure(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_html_fragment_without_root_tags_is_accepted(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "partial.html"
        target.write_text('<div class="card">\n  <span>hi</span>\n</div>\n', encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_html_structure(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_script_tag_text_inside_string_is_not_a_tag(self, tmp_path):
        """JS 字符串里的 "<script ...>" 不是标签，不能据它判 script 未闭合。"""
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "page.html"
        target.write_text(
            '<html><head></head><body><script>\nconst t = "<script src=x>";\n'
            "</script></body></html>\n",
            encoding="utf-8",
        )

        ok, errors = await CodeValidator(tmp_path).validate_html_structure(target)

        assert ok is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_truncated_html_is_still_flagged(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "truncated.html"
        target.write_text(
            "<!DOCTYPE html>\n<html>\n<head>\n</head>\n<body>\n  <p>hi</p>\n",
            encoding="utf-8",
        )

        ok, errors = await CodeValidator(tmp_path).validate_html_structure(target)

        assert ok is False
        assert any("</body>" in err for err in errors)

    @pytest.mark.asyncio
    async def test_unclosed_script_is_still_flagged(self, tmp_path):
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "broken.html"
        target.write_text(
            "<html><head></head><body><script>var a=1;</body></html>", encoding="utf-8"
        )

        ok, errors = await CodeValidator(tmp_path).validate_html_structure(target)

        assert ok is False
        assert any("</script>" in err for err in errors)

    @pytest.mark.asyncio
    async def test_css_empty_declarations_are_accepted(self, tmp_path):
        """空声明（连续或孤立的分号）在 CSS 中是合法的。"""
        from app.agent.code_validator import CodeValidator

        target = tmp_path / "styles.css"
        target.write_text("a {\n  color: red;;\n}\n", encoding="utf-8")

        ok, errors = await CodeValidator(tmp_path).validate_css_syntax(target)

        assert ok is True
        assert errors == []


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
