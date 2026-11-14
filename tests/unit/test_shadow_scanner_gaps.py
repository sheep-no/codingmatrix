"""shadow_scanner 扫描与跳过规则补测。"""

import asyncio

from app.agent import shadow_scanner


def test_scan_detects_patterns(tmp_path):
    source = tmp_path / "app.py"
    source.write_text(
        "import os\neval('1')\nimportlib.import_module('x')\nos.getenv('A')\n",
        encoding="utf-8",
    )

    result = shadow_scanner._scan_sync(tmp_path)

    assert set(result["app.py"]) == {"eval_exec", "dynamic_import", "env_dependency"}


def test_scan_skips_unsupported_and_skip_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "a.py").write_text("eval('1')", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("eval('1')", encoding="utf-8")
    (tmp_path / "clean.js").write_text("const x = 1;", encoding="utf-8")

    assert shadow_scanner._scan_sync(tmp_path) == {}


def test_scan_ignores_unreadable_files(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("eval('1')", encoding="utf-8")

    original = shadow_scanner.Path.read_text

    def boom(self, *args, **kwargs):
        if self.name == "a.py":
            raise OSError("unreadable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(shadow_scanner.Path, "read_text", boom)

    assert shadow_scanner._scan_sync(tmp_path) == {}


def test_scan_skips_directories(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("eval('1')", encoding="utf-8")

    assert shadow_scanner._scan_sync(tmp_path) == {"pkg/a.py": ["eval_exec"]}


def test_scan_detects_js_patterns(tmp_path):
    (tmp_path / "a.jsx").write_text(
        "require.context('./x'); getattr(obj, 'x');", encoding="utf-8"
    )
    (tmp_path / "b.vue").write_text("import('x')", encoding="utf-8")

    result = shadow_scanner._scan_sync(tmp_path)

    assert result["a.jsx"] == ["dynamic_require", "getattr_dynamic"]
    assert result["b.vue"] == ["dynamic_require"]


def test_async_scan_wraps_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_scanner, "_scan_sync", lambda path: {"x": ["y"]})
    assert asyncio.run(shadow_scanner.scan_shadow_dependencies(tmp_path)) == {"x": ["y"]}
