"""CodeValidator 全分支回归：缓存、导入解析、运行时符号、契约与全量验证。"""

import ast
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import code_validator as cv
from app.agent.code_validator import CodeValidator


@pytest.fixture
def validator(tmp_path):
    return CodeValidator(tmp_path)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestImportHelpers:
    def test_imports_symbol_exact_match(self):
        source = "from fastapi import Middleware\n"
        assert cv._imports_symbol_from_module(source, "fastapi", "Middleware") is True

    def test_imports_symbol_ignores_other_symbols(self):
        source = "from fastapi import CORSMiddleware\n"
        assert cv._imports_symbol_from_module(source, "fastapi", "Middleware") is False

    def test_imports_symbol_ignores_relative_import(self):
        source = "from .fastapi import Middleware\n"
        assert cv._imports_symbol_from_module(source, "fastapi", "Middleware") is False

    def test_imports_symbol_syntax_error(self):
        assert cv._imports_symbol_from_module("from x import (", "x", "y") is False

    def test_module_exports_aliases_and_annotations(self):
        source = (
            "import os as operating_system\n"
            "from x import y as z\n"
            "from x import *\n"
            "CONST: int = 1\n"
            "class C:\n    pass\n"
            "def f():\n    pass\n"
        )
        exports = cv._module_level_exports(ast.parse(source))

        assert exports["variables"] == {"operating_system", "z", "CONST"}
        assert exports["classes"] == {"C"}
        assert exports["functions"] == {"f"}

    def test_module_exports_descend_into_compound_statements(self):
        source = (
            "try:\n"
            "    def in_try():\n"
            "        pass\n"
            "except ImportError:\n"
            "    def in_handler():\n"
            "        pass\n"
            "else:\n"
            "    def in_else():\n"
            "        pass\n"
            "finally:\n"
            "    def in_finally():\n"
            "        pass\n"
            "if True:\n"
            "    def in_if():\n"
            "        pass\n"
            "with open('x'):\n"
            "    def in_with():\n"
            "        pass\n"
        )
        exports = cv._module_level_exports(ast.parse(source))

        assert exports["functions"] == {
            "in_try",
            "in_handler",
            "in_else",
            "in_finally",
            "in_if",
            "in_with",
        }

    def test_module_exports_skips_tuple_targets(self):
        exports = cv._module_level_exports(ast.parse("a, b = 1, 2\n"))

        assert exports["variables"] == set()


class TestPathResolution:
    def test_import_search_paths_includes_src(self, tmp_path):
        (tmp_path / "src").mkdir()
        validator = CodeValidator(tmp_path)
        target = _write(tmp_path / "app" / "main.py", "")

        paths = validator._import_search_paths(target)

        assert str(tmp_path.resolve()) in paths
        assert str((tmp_path / "src").resolve()) in paths

    def test_top_level_packages_detects_modules_and_namespaces(self, tmp_path):
        (tmp_path / "pkg").mkdir()
        _write(tmp_path / "pkg" / "__init__.py", "")
        (tmp_path / "ns").mkdir()
        _write(tmp_path / "ns" / "mod.py", "")
        (tmp_path / "plain.py").write_text("", encoding="utf-8")
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "__pycache__").mkdir()

        names = CodeValidator(tmp_path)._project_top_level_packages()

        assert set(names) == {"pkg", "ns", "plain"}

    def test_top_level_packages_oserror_returns_empty(self, tmp_path, monkeypatch):
        def boom():
            raise OSError("no access")

        validator = CodeValidator(tmp_path)
        monkeypatch.setattr(Path, "iterdir", lambda self: boom())

        assert validator._project_top_level_packages() == []

    def test_top_level_packages_skips_empty_dirs_and_non_py(self, tmp_path):
        (tmp_path / "empty").mkdir()
        (tmp_path / "data.txt").write_text("x", encoding="utf-8")

        assert CodeValidator(tmp_path)._project_top_level_packages() == []

    def test_resolve_module_file_and_init(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "app" / "mod.py", "")
        _write(tmp_path / "pkg" / "__init__.py", "")

        assert validator._resolve_project_module("app.mod") == (tmp_path / "app" / "mod.py")
        assert validator._resolve_project_module("pkg") == (tmp_path / "pkg" / "__init__.py")

    def test_resolve_module_src_layout_and_namespace(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "src" / "pkg" / "mod.py", "")
        (tmp_path / "namespace").mkdir()
        _write(tmp_path / "namespace" / "x.py", "")

        assert validator._resolve_project_module("pkg.mod") == (
            tmp_path / "src" / "pkg" / "mod.py"
        )
        assert validator._resolve_project_module("namespace") == tmp_path / "namespace"

    @pytest.mark.parametrize("module", ["", ".", "a..b", "."])
    def test_resolve_module_rejects_empty_parts(self, tmp_path, module):
        assert CodeValidator(tmp_path)._resolve_project_module(module) is None

    def test_resolve_module_missing(self, tmp_path):
        assert CodeValidator(tmp_path)._resolve_project_module("ghost") is None


class TestMissingSymbols:
    def test_no_resolution_returns_empty(self, tmp_path):
        assert CodeValidator(tmp_path)._missing_project_symbols("ghost", ["x"]) == []

    def test_init_reexports_submodule_and_symbol(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(
            tmp_path / "pkg" / "__init__.py",
            "from .mod import real\n",
        )
        _write(tmp_path / "pkg" / "mod.py", "def real():\n    pass\n")

        assert validator._missing_project_symbols("pkg", ["real", "mod"]) == []
        assert validator._missing_project_symbols("pkg", ["ghost"]) == ["ghost"]

    def test_missing_symbol_skips_implicit_attrs_and_star(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "mod.py", "VALUE = 1\n")

        assert validator._missing_project_symbols(
            "mod", ["VALUE", "__doc__", "*", ""]
        ) == []

    def test_syntax_error_returns_empty(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "mod.py", "def broken(\n")

        assert validator._missing_project_symbols("mod", ["x"]) == []

    def test_oserror_returns_empty(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "mod.py", "X = 1\n")
        orig = Path.read_text

        def boom(self, *args, **kwargs):
            if self.name == "mod.py":
                raise OSError("denied")
            return orig(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", boom)

        assert validator._missing_project_symbols("mod", ["x"]) == []


class TestThirdPartyScan:
    def test_skips_relative_and_invalid_files(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "pkg" / "mod.py", "import requests\nfrom . import x\n")
        _write(tmp_path / "pkg" / "bad.py", "def broken(\n")
        _write(tmp_path / "__pycache__" / "cached.py", "import numpy\n")

        assert validator._python_third_party_imports() == ["requests"]

    def test_stdlib_and_local_are_excluded(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "pkg" / "__init__.py", "")
        _write(tmp_path / "pkg" / "mod.py", "import os\nimport pkg\n")

    def test_absolute_from_import_is_collected(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "mod.py", "from django.db import models\n")

        assert validator._python_third_party_imports() == ["django"]


class TestCache:
    def test_store_replace_updates_size(self, tmp_path):
        validator = CodeValidator(tmp_path)
        validator.store_validation("k", {"is_valid": True})
        size = validator._cache_size_bytes

        validator.store_validation("k", {"is_valid": False})

        assert validator._cache_size_bytes == size
        assert len(validator._lru_cache) == 1

    def test_clear_old_cache_drops_expired_success_and_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        clock = {"now": cv.time.time()}
        monkeypatch.setattr(cv.time, "time", lambda: clock["now"])
        validator.store_validation("ok", {"is_valid": True})
        validator.store_validation("bad", {"is_valid": False})

        validator._clear_old_cache()

        # 时间冻结在写入时刻，两个条目都未过期
        assert len(validator._lru_cache) == 2

        # 时间前进到所有 TTL 之外后清空
        clock["now"] += 10_000
        validator._clear_old_cache()
        assert validator._lru_cache == {}

    def test_clear_old_cache_enforces_size_limit(self, tmp_path):
        validator = CodeValidator(tmp_path)
        validator._max_cache_bytes = 1
        validator.store_validation("a", {"is_valid": True})
        validator.store_validation("b", {"is_valid": True})

        assert len(validator._lru_cache) <= 2
        assert validator._cache_size_bytes >= 0

    def test_get_cached_validation_missing_file_is_miss(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert validator.get_cached_validation(tmp_path / "ghost.py") is None
        assert validator._cache_misses == 1

    def test_get_cached_validation_uncached_file_is_miss(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.py", "X = 1\n")

        assert validator.get_cached_validation(path) is None
        assert validator._cache_misses == 1

    def test_get_cached_validation_expired_recomputes(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.py", "X = 1\n")
        result = {"is_valid": True}
        validator.cache_validation(path, result)
        clock = {"now": cv.time.time() + 10_000}
        monkeypatch.setattr(cv.time, "time", lambda: clock["now"])

        assert validator.get_cached_validation(path) is None
        assert validator._cache_misses == 1

    def test_get_cached_validation_hit_moves_to_end(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.py", "X = 1\n")
        validator.cache_validation(path, {"is_valid": True})
        validator.store_validation("other", {"is_valid": True})

        assert validator.get_cached_validation(path) is not None
        assert list(validator._lru_cache)[-1].startswith(str(path))
        assert validator._cache_hits == 1

    def test_cache_validation_write_failure_logs(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        orig = Path.read_text

        def boom(self, *args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(Path, "read_text", boom)
        validator.cache_validation(tmp_path / "a.py", {"is_valid": True})

        assert not validator._lru_cache

    def test_get_cached_validation_by_key_miss_and_hit(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        assert validator.get_cached_validation_by_key("missing") is None

        validator.store_validation("k", {"is_valid": True})
        assert validator.get_cached_validation_by_key("k") == {"is_valid": True}

        clock = {"now": cv.time.time() + 10_000}
        monkeypatch.setattr(cv.time, "time", lambda: clock["now"])
        assert validator.get_cached_validation_by_key("k") is None

    def test_cache_stats_hit_rate(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert validator.get_cache_stats()["hit_rate"] == 0.0

        validator._cache_hits = 1
        validator._cache_misses = 3
        assert validator.get_cache_stats()["hit_rate"] == pytest.approx(0.25)


class TestSyntaxAndImports:
    @pytest.mark.asyncio
    async def test_syntax_non_python(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_syntax(tmp_path / "a.js") == (True, [])

    @pytest.mark.asyncio
    async def test_syntax_success_and_error(self, tmp_path):
        validator = CodeValidator(tmp_path)
        good = _write(tmp_path / "good.py", "X = 1\n")
        bad = _write(tmp_path / "bad.py", "def broken(\n")

        assert await validator.validate_syntax(good) == (True, [])
        ok, errs = await validator.validate_syntax(bad)
        assert ok is False
        assert errs[0].startswith("语法错误")

    @pytest.mark.asyncio
    async def test_syntax_read_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.py", "")

        async def boom(*args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(cv, "_read_text_async", boom)
        ok, errs = await validator.validate_syntax(path)

        assert ok is False
        assert errs == ["验证失败: denied"]

    @pytest.mark.asyncio
    async def test_imports_non_python_and_syntax_error(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_imports(tmp_path / "a.js") == (True, [])

        bad = _write(tmp_path / "bad.py", "def broken(\n")
        assert await validator.validate_imports(bad) == (True, [])

    @pytest.mark.asyncio
    async def test_imports_detects_missing_and_relative_skipped(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "mod.py",
            "import os\nfrom . import sibling\nfrom ghostpkg.sub import x\n",
        )

        ok, errs = await validator.validate_imports(path)

        assert ok is False
        assert errs == ["缺少依赖: ghostpkg"]
        assert all(".sibling" not in e for e in errs)

    @pytest.mark.asyncio
    async def test_imports_cleans_added_sys_path(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "import os\n")
        before = list(sys.path)
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

        await validator.validate_imports(path)

        assert sys.path == before

    @pytest.mark.asyncio
    async def test_imports_path_already_on_sys_path_is_not_removed(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "import os\n")
        sys.path.insert(0, str(tmp_path))
        monkeypatch.setattr(validator, "_import_search_paths", lambda p: [str(tmp_path)])
        before = list(sys.path)

        await validator.validate_imports(path)

        assert sys.path == before
        sys.path.remove(str(tmp_path))

    @pytest.mark.asyncio
    async def test_imports_sys_path_failure_is_logged(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "import os\n")
        monkeypatch.setattr(
            validator, "_import_search_paths", lambda p: (_ for _ in ()).throw(RuntimeError("bad"))
        )

        ok, errs = await validator.validate_imports(path)
        assert ok is True

    @pytest.mark.asyncio
    async def test_imports_read_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "")

        async def boom(*args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(cv, "_read_text_async", boom)
        ok, errs = await validator.validate_imports(path)

        assert ok is False
        assert errs == ["导入验证失败: denied"]

    @pytest.mark.asyncio
    async def test_imports_find_spec_raises(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "import ghostpkg\n")

        def boom(name):
            raise ValueError(name)

        monkeypatch.setattr(importlib.util, "find_spec", boom)

        ok, errs = await validator.validate_imports(path)

        assert ok is False
        assert errs == ["缺少依赖: ghostpkg"]

    @pytest.mark.asyncio
    async def test_imports_find_spec_resolved(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "import pytest\n")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

        assert await validator.validate_imports(path) == (True, [])


class TestRuntimeImports:
    @pytest.mark.asyncio
    async def test_non_python_and_init_skip(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_runtime_imports(tmp_path / "a.js") == (True, [])

        init = _write(tmp_path / "pkg" / "__init__.py", "import ghost\n")
        assert await validator.validate_runtime_imports(init) == (True, [])

    @pytest.mark.asyncio
    async def test_read_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.py", "")

        async def boom(*args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(cv, "_read_text_async", boom)
        ok, errs = await validator.validate_runtime_imports(path)

        assert ok is False
        assert errs == ["运行时验证异常: denied"]

    @pytest.mark.asyncio
    async def test_passlib_import_rules(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "mod.py",
            "import passlib.hash.bcrypt\nimport passlib.hash\n",
        )

        ok, errs = await validator.validate_runtime_imports(path)

        assert ok is False
        assert len(errs) == 2

    @pytest.mark.asyncio
    async def test_passlib_correct_import_passes(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "from passlib.hash import bcrypt\n")

        assert await validator.validate_runtime_imports(path) == (True, [])

    @pytest.mark.asyncio
    async def test_syntax_error_keeps_text_errors(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "import passlib.hash\ndef broken(\n")

        ok, errs = await validator.validate_runtime_imports(path)

        assert ok is False
        assert len(errs) == 1

    @pytest.mark.asyncio
    async def test_missing_project_module_and_symbol(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "pkg" / "__init__.py", "")
        _write(tmp_path / "pkg" / "real.py", "def exported():\n    pass\n")
        path = _write(
            tmp_path / "pkg" / "main.py",
            "import pkg.ghost\nfrom pkg.real import exported, ghost\n"
            "from pkg import missing\nfrom external import thing\n"
            "from . import relative\n",
        )

        ok, errs = await validator.validate_runtime_imports(path)

        assert ok is False
        assert "运行时导入失败: No module named 'pkg.ghost'" in errs
        assert "运行时导入失败: 无法从 'pkg.real' 导入 'ghost'" in errs
        assert "运行时导入失败: 无法从 'pkg' 导入 'missing'" in errs
        assert not any("external" in e for e in errs)
        assert not any("relative" in e for e in errs)

    @pytest.mark.asyncio
    async def test_missing_submodule_import(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "pkg" / "__init__.py", "")
        path = _write(tmp_path / "pkg" / "main.py", "from pkg.ghost import thing\n")

        ok, errs = await validator.validate_runtime_imports(path)

        assert ok is False
        assert errs == ["运行时导入失败: No module named 'pkg.ghost'"]


class TestApiCompatibility:
    @pytest.mark.asyncio
    async def test_non_python(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_api_compatibility(tmp_path / "a.js") == (True, [])

    @pytest.mark.asyncio
    async def test_legacy_token_url(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "mod.py",
            "from fastapi.security import OAuth2PasswordBearer\n"
            "oauth = OAuth2PasswordBearer(token_url='/token')\n",
        )

        ok, errs = await validator.validate_api_compatibility(path)

        assert ok is False
        assert "tokenUrl" in errs[0]

    @pytest.mark.asyncio
    async def test_modern_token_url(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "mod.py",
            "oauth = OAuth2PasswordBearer(tokenUrl='/token')\n",
        )
        assert await validator.validate_api_compatibility(path) == (True, [])

    @pytest.mark.asyncio
    async def test_middleware_symbol(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "from fastapi import Middleware\n")

        ok, errs = await validator.validate_api_compatibility(path)
        assert ok is False
        assert "middleware.cors" in errs[0]

    @pytest.mark.asyncio
    async def test_mro_conflict_detected(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "mod.py",
            "class User(Base, BaseModel):\n    pass\n",
        )

        ok, errs = await validator.validate_api_compatibility(path)
        assert ok is False
        assert "MRO" in errs[0]

    @pytest.mark.asyncio
    async def test_router_exception_handler(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "mod.py",
            "router = APIRouter()\nrouter.exception_handler(Exception)\n",
        )

        ok, errs = await validator.validate_api_compatibility(path)
        assert ok is False
        assert "add_exception_handler" in errs[0]

    @pytest.mark.asyncio
    async def test_read_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "")

        async def boom(*args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(cv, "_read_text_async", boom)
        ok, errs = await validator.validate_api_compatibility(path)

        assert ok is False
        assert errs == ["API 兼容性检查异常: denied"]


class TestFrontendValidators:
    @pytest.mark.asyncio
    async def test_js_non_js(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_js_syntax(tmp_path / "a.py") == (True, [])

    @pytest.mark.asyncio
    async def test_js_node_missing(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.js", "")

        async def boom(*args, **kwargs):
            raise FileNotFoundError

        monkeypatch.setattr(cv.asyncio, "create_subprocess_exec", boom)

        assert await validator.validate_js_syntax(path) == (True, [])

    @pytest.mark.asyncio
    async def test_js_unexpected_error(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.js", "")

        async def boom(*args, **kwargs):
            raise RuntimeError("spawn failed")

        monkeypatch.setattr(cv.asyncio, "create_subprocess_exec", boom)
        ok, errs = await validator.validate_js_syntax(path)

        assert ok is False
        assert errs == ["JS 验证异常: spawn failed"]

    @pytest.mark.asyncio
    async def test_js_node_exit_codes(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.js", "")

        class Proc:
            def __init__(self, returncode):
                self.returncode = returncode

            async def communicate(self):
                return b"", b"bad syntax"

        async def killed(*args, **kwargs):
            return Proc(-9)

        monkeypatch.setattr(cv.asyncio, "create_subprocess_exec", killed)
        assert await validator.validate_js_syntax(path) == (True, [])

        async def failed(*args, **kwargs):
            return Proc(1)

        monkeypatch.setattr(cv.asyncio, "create_subprocess_exec", failed)
        ok, errs = await validator.validate_js_syntax(path)
        assert ok is False
        assert errs == ["JS 语法错误: bad syntax"]

        async def passed(*args, **kwargs):
            return Proc(0)

        monkeypatch.setattr(cv.asyncio, "create_subprocess_exec", passed)
        assert await validator.validate_js_syntax(path) == (True, [])

    @pytest.mark.asyncio
    async def test_html_non_html(self, tmp_path):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_html_structure(tmp_path / "a.py") == (True, [])

    @pytest.mark.asyncio
    async def test_html_read_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.html", "")

        async def boom(*args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(cv, "_read_text_async", boom)
        ok, errs = await validator.validate_html_structure(path)

        assert ok is False
        assert errs == ["HTML 验证异常: denied"]

    @pytest.mark.asyncio
    async def test_html_valid_content(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(
            tmp_path / "a.html",
            "<!DOCTYPE html><html><head><title>t</title></head>"
            "<body><p>ok</p></body></html>",
        )

        assert await validator.validate_html_structure(path) == (True, [])

    @pytest.mark.asyncio
    async def test_css_non_css_and_failure(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        assert await validator.validate_css_syntax(tmp_path / "a.py") == (True, [])

        path = _write(tmp_path / "a.css", "")

        async def boom(*args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(cv, "_read_text_async", boom)
        ok, errs = await validator.validate_css_syntax(path)

        assert ok is False
        assert errs == ["CSS 验证异常: denied"]

    @pytest.mark.asyncio
    async def test_css_valid_content(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "a.css", "body { color: red; }\n")

        assert await validator.validate_css_syntax(path) == (True, [])


class TestCrossFileSync:
    def test_skips_pycache_and_syntax_errors(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "pkg" / "__init__.py", "")
        _write(tmp_path / "pkg" / "bad.py", "def broken(\n")
        _write(tmp_path / "__pycache__" / "x.py", "import ghost\n")

        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is True
        assert errs == []

    def test_main_missing_module(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "from ghost import x\n")

        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is False
        assert "不存在的模块 'ghost'" in errs[0]

    def test_main_imports_unparsed_module_skips_symbol_check(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "bad.py", "def broken(\n")
        _write(tmp_path / "main.py", "from bad import ghost\n")

        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is True
        assert errs == []

    def test_main_missing_symbol_and_submodule(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "app" / "__init__.py", "A = 1\n")
        _write(tmp_path / "app" / "mod.py", "")
        _write(
            tmp_path / "main.py",
            "from app import A, ghost\nfrom app import mod\n",
        )

        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is False
        assert len(errs) == 1
        assert "ghost" in errs[0]

    def test_main_syntax_error_ignored(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "def broken(\n")

        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is True

    def test_main_read_failure_is_logged(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "")
        orig = Path.read_text

        def boom(self, *args, **kwargs):
            if self.name == "main.py":
                raise OSError("denied")
            return orig(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", boom)
        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is True

    def test_main_processing_exception_is_logged(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "from app import A\n")
        _write(tmp_path / "app" / "__init__.py", "A = 1\n")

        real_parse = cv.ast.parse
        calls = {"n": 0}

        def flaky(source, *args, **kwargs):
            calls["n"] += 1
            # 第一次解析用于收集定义，第二次解析 main.py，第三次用于提取导入
            if calls["n"] >= 3:
                raise RuntimeError("parse failed")
            return real_parse(source, *args, **kwargs)

        monkeypatch.setattr(cv.ast, "parse", flaky)
        ok, errs = validator._validate_cross_file_consistency_sync()

        assert ok is True
        assert errs == []


class TestSingleFilePython:
    @pytest.mark.asyncio
    async def test_other_suffix_returns_defaults(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "notes.txt", "hello\n")

        result = await validator.validate_single_file(path)

        assert result["is_valid"] is True
        assert result["frontend_errors"] == []

    @pytest.mark.asyncio
    async def test_valid_python(self, tmp_path):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "X = 1\n")

        result = await validator.validate_single_file(path)

        assert result["is_valid"] is True
        assert result["validated_files"] == 1

    @pytest.mark.asyncio
    async def test_runtime_failure_invalidates(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        path = _write(tmp_path / "mod.py", "X = 1\n")

        async def runtime_fail(p):
            return False, ["runtime"]

        monkeypatch.setattr(validator, "validate_runtime_imports", runtime_fail)
        result = await validator.validate_single_file(path)

        assert result["is_valid"] is False
        assert result["runtime_errors"] == ["runtime"]

    @pytest.mark.asyncio
    async def test_html_and_css_failure_invalidate(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        html = _write(tmp_path / "a.html", "")
        css = _write(tmp_path / "a.css", "")

        monkeypatch.setattr(validator, "validate_html_structure", _false_errors)
        monkeypatch.setattr(validator, "validate_css_syntax", _false_errors)

        assert (await validator.validate_single_file(html))["is_valid"] is False
        assert (await validator.validate_single_file(css))["is_valid"] is False


class TestSingleFile:
    @pytest.mark.asyncio
    async def test_js_html_css_branches(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        js = _write(tmp_path / "a.js", "")
        html = _write(tmp_path / "a.html", "")
        css = _write(tmp_path / "a.css", "")

        monkeypatch.setattr(validator, "validate_js_syntax", _true_errors)
        monkeypatch.setattr(validator, "validate_html_structure", _true_errors)
        monkeypatch.setattr(validator, "validate_css_syntax", _true_errors)

        for path in (js, html, css):
            result = await validator.validate_single_file(path)
            assert result["is_valid"] is True
            assert result["frontend_errors"] == ["err"]

    @pytest.mark.asyncio
    async def test_js_failure_invalidates(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        js = _write(tmp_path / "a.js", "")
        monkeypatch.setattr(
            validator, "validate_js_syntax", _false_errors
        )

        result = await validator.validate_single_file(js)
        assert result["is_valid"] is False


async def _true_errors(path):
    return True, ["err"]


async def _false_errors(path):
    return False, ["err"]


class TestPipfileAndRequirements:
    def test_packages_from_pipfile(self, tmp_path):
        path = tmp_path / "Pipfile"
        path.write_text(
            "[packages]\nPyYAML = '*'\nrequests = '*'\n"
            "[dev-packages]\npytest = '*'\n",
            encoding="utf-8",
        )

        assert CodeValidator._packages_from_pipfile(path) == [
            "pyyaml",
            "requests",
            "pytest",
        ]

    def test_packages_from_pipfile_skips_paths(self, tmp_path):
        path = tmp_path / "Pipfile"
        path.write_text(
            '[packages]\nlocal = {path = "."}\n"./vendored" = "*"\n"/sys" = "*"\n',
            encoding="utf-8",
        )
        # 路径式键（以 . 或 / 开头）被跳过；具名包即使指向本地路径也保留
        assert CodeValidator._packages_from_pipfile(path) == ["local"]

    @pytest.mark.asyncio
    async def test_requirements_parses_variants(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        requirements = tmp_path / "requirements.txt"
        requirements.write_text(
            "# comment\n"
            "-r other.txt\n"
            "git+https://example.com/repo.git\n"
            "requests[security]>=2.0\n"
            "fastapi==0.100.0\n"
            "uvicorn~=0.1\n"
            "flask<=2.0\n"
            "django!=1.0\n"
            "local @ file:./pkg\n"
            "./local\n"
            "/abs\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(importlib, "import_module", lambda name: object())

        ok, errs = await validator.validate_requirements()

        assert ok is True
        assert errs == []

    @pytest.mark.asyncio
    async def test_requirements_skips_constraint_only_line(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        (tmp_path / "requirements.txt").write_text("==1.0\n", encoding="utf-8")
        monkeypatch.setattr(importlib, "import_module", lambda name: object())

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_pyproject_variants(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "dependencies = [\n"
            "  'requests>=2',\n"
            "  'git+https://example.com/x.git',\n"
            "  'uvicorn',\n"
            "]\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(importlib, "import_module", lambda name: object())

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_pyproject_skips_constraint_only_line(
        self, tmp_path, monkeypatch
    ):
        validator = CodeValidator(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            "[project]\ndependencies = ['==1.0']\n", encoding="utf-8"
        )
        monkeypatch.setattr(importlib, "import_module", lambda name: object())

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_pyproject_parse_error(self, tmp_path):
        validator = CodeValidator(tmp_path)
        (tmp_path / "pyproject.toml").write_text("not toml", encoding="utf-8")

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_pipfile(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        (tmp_path / "Pipfile").write_text(
            "[packages]\nrequests = '*'\n", encoding="utf-8"
        )
        monkeypatch.setattr(importlib, "import_module", lambda name: object())

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_pipfile_skips_empty_names(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        (tmp_path / "Pipfile").write_text("[packages]\n", encoding="utf-8")
        monkeypatch.setattr(
            CodeValidator,
            "_packages_from_pipfile",
            staticmethod(lambda p: ["", "fastapi"]),
        )
        seen = []
        monkeypatch.setattr(
            importlib, "import_module", lambda name: seen.append(name) or object()
        )

        ok, errs = await validator.validate_requirements()

        assert ok is True
        assert seen == ["fastapi"]

    @pytest.mark.asyncio
    async def test_requirements_pipfile_parse_error(self, tmp_path):
        validator = CodeValidator(tmp_path)
        (tmp_path / "Pipfile").write_text("not toml", encoding="utf-8")

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_no_manifest_non_python_project(self, tmp_path):
        validator = CodeValidator(tmp_path)
        (tmp_path / "index.html").write_text("", encoding="utf-8")

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_no_manifest_stdlib_only(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "import os\n")

        assert await validator.validate_requirements() == (True, [])

    @pytest.mark.asyncio
    async def test_requirements_missing_manifest_with_third_party(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "import requests\n")

        ok, errs = await validator.validate_requirements()

        assert ok is False
        assert "requests" in errs[0]

    @pytest.mark.asyncio
    async def test_requirements_missing_installed_package_is_warning_only(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        (tmp_path / "requirements.txt").write_text("ghostpkg==1.0\n", encoding="utf-8")

        def boom(name):
            raise ImportError(name)

        monkeypatch.setattr(importlib, "import_module", boom)

        assert await validator.validate_requirements() == (True, [])


class TestRunFullValidation:
    @pytest.mark.asyncio
    async def test_empty_project(self, tmp_path):
        validator = CodeValidator(tmp_path)

        result = await validator.run_full_validation()

        assert result["validated_files"] == 0
        assert result["is_valid"] is True
        assert validator._lru_cache == {}

    @pytest.mark.asyncio
    async def test_cache_hit_short_circuits(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "X = 1\n")

        first = await validator.run_full_validation()
        second = await validator.run_full_validation()

        assert first["validated_files"] == 1
        assert second["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_python_exception_result_marks_invalid(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "X = 1\n")

        async def boom(path):
            raise RuntimeError("explode")

        monkeypatch.setattr(validator, "validate_syntax", boom)
        result = await validator.run_full_validation()

        assert result["is_valid"] is False
        assert any("验证异常" in e for e in result["import_errors"])

    @pytest.mark.asyncio
    async def test_python_errors_mark_invalid(self, tmp_path):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "def broken(\n")

        result = await validator.run_full_validation()

        assert result["is_valid"] is False
        assert result["syntax_errors"]

    @pytest.mark.asyncio
    async def test_frontend_exception_result_marks_invalid(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "app.js", "")

        async def boom(path):
            raise RuntimeError("front")

        monkeypatch.setattr(validator, "validate_js_syntax", boom)
        result = await validator.run_full_validation()

        assert result["is_valid"] is False
        assert any("前端验证异常" in e for e in result["frontend_errors"])

    @pytest.mark.asyncio
    async def test_frontend_errors_mark_invalid(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "app.js", "")
        _write(tmp_path / "index.html", "")
        _write(tmp_path / "style.css", "")

        monkeypatch.setattr(validator, "validate_js_syntax", _false_errors)
        monkeypatch.setattr(validator, "validate_html_structure", _false_errors)
        monkeypatch.setattr(validator, "validate_css_syntax", _false_errors)
        result = await validator.run_full_validation()

        assert result["is_valid"] is False
        assert len(result["frontend_errors"]) == 3

    @pytest.mark.asyncio
    async def test_frontend_mixed_results(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "ok.js", "")
        _write(tmp_path / "bad.css", "")

        async def js_ok(path):
            return True, []

        monkeypatch.setattr(validator, "validate_js_syntax", js_ok)
        monkeypatch.setattr(validator, "validate_css_syntax", _false_errors)
        result = await validator.run_full_validation()

        assert result["frontend_errors"] == ["err"]
        assert result["is_valid"] is False

    @pytest.mark.asyncio
    async def test_cross_file_and_dependency_errors(self, tmp_path, monkeypatch):
        validator = CodeValidator(tmp_path)
        _write(tmp_path / "main.py", "X = 1\n")

        async def cross_fail():
            return False, ["cross"]

        async def dep_fail():
            return False, ["dep"]

        monkeypatch.setattr(validator, "validate_cross_file_consistency", cross_fail)
        monkeypatch.setattr(validator, "validate_requirements", dep_fail)
        result = await validator.run_full_validation()

        assert result["is_valid"] is False
        assert result["cross_file_errors"] == ["cross"]
        assert result["dependency_errors"] == ["dep"]
