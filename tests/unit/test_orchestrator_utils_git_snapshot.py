"""UtilsMixin._git_save_snapshot 事件循环阻塞与快照行为测试。

原实现在 async 函数里直接跑 git 子进程与文件写入，会占住事件循环；
现改为投递到线程池，这里锁住该行为并验证快照仍然生效。
"""

import asyncio
import subprocess as sp
from pathlib import Path

import app.agent.orchestrator_utils as ou
from app.agent.orchestrator_utils import UtilsMixin


class _Host(UtilsMixin):
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.session_id = "s-1"
        self.model_name = "test-model"


def test_git_snapshot_offloads_blocking_work_to_thread(tmp_path, monkeypatch):
    host = _Host(tmp_path)
    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    monkeypatch.setattr(ou.asyncio, "to_thread", fake_to_thread)

    asyncio.run(host._git_save_snapshot("snapshot"))

    assert len(calls) == 1
    assert calls[0][0] == host._git_save_snapshot_sync
    assert calls[0][1] == ("snapshot",)


def test_git_snapshot_sync_creates_repo_and_commit(tmp_path):
    host = _Host(tmp_path)
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")

    host._git_save_snapshot_sync("first commit")

    assert (tmp_path / ".git").exists()
    log = sp.run(
        ["git", "log", "--oneline"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "first commit" in log.stdout


def test_git_snapshot_sync_is_idempotent_on_no_changes(tmp_path):
    host = _Host(tmp_path)
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")

    host._git_save_snapshot_sync("first commit")
    host._git_save_snapshot_sync("no changes")

    log = sp.run(
        ["git", "log", "--oneline"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.count("\n") == 1
    assert "no changes" not in log.stdout
