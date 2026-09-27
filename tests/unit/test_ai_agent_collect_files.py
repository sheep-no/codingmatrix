"""回归测试：ai_agent `_collect_files` 不得在事件循环上做阻塞文件扫描。

原实现是 async generator，直接在其中调用 ``rglob`` / ``stat`` / ``open``，
扫描大型项目目录时会阻塞事件循环。现改为在线程池中执行同步扫描。
"""

import threading
from pathlib import Path

import pytest

import app.api.v1.ai_agent.helpers as helpers


async def _collect(project_dir):
    return [entry async for entry in helpers._collect_files(project_dir)]


class TestCollectFiles:
    @pytest.mark.asyncio
    async def test_filters_hidden_skip_dirs_and_large_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print(1)")
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "util.py").write_text("x = 1")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("secret")
        (tmp_path / ".hidden.py").write_text("y = 2")
        (tmp_path / "big.txt").write_text("a" * (helpers.MAX_TEXT_FILE_SIZE + 1))
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "dep.js").write_text("module")
        (tmp_path / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")

        entries = await _collect(tmp_path)
        names = {e["name"] for e in entries}

        assert "main.py" in names
        assert "util.py" in names
        assert ".hidden.py" not in names
        assert "config" not in names
        assert "big.txt" not in names
        assert "dep.js" not in names
        assert "bin.dat" not in names

    @pytest.mark.asyncio
    async def test_scan_runs_off_event_loop_thread(self, tmp_path, monkeypatch):
        (tmp_path / "a.py").write_text("a = 1")

        rglob_threads = []
        original_rglob = Path.rglob

        def spy(self, pattern):
            rglob_threads.append(threading.get_ident())
            return original_rglob(self, pattern)

        monkeypatch.setattr(Path, "rglob", spy)

        main_thread = threading.get_ident()
        entries = await _collect(tmp_path)

        assert {e["name"] for e in entries} == {"a.py"}
        assert rglob_threads, "目录扫描必须实际发生"
        assert main_thread not in rglob_threads, "阻塞扫描必须在工作线程中执行"
