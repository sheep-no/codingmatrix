"""ai_agent helpers 旧会话清理的事件循环卸载回归测试。

`_cleanup_old_session` 原先在 async 函数里直接 `Path.unlink` / `shutil.rmtree`
删除会话文件与项目目录（项目目录可能很大），阻塞事件循环。现抽出同步
`_delete_session_files` 并统一以 `asyncio.to_thread` 在工作线程执行。
"""
import threading
from pathlib import Path
from types import SimpleNamespace

from app.api.v1.ai_agent import helpers


class _FakeResult:
    def __init__(self, sessions):
        self._sessions = sessions

    def scalars(self):
        return self

    def all(self):
        return self._sessions


class _FakeDB:
    def __init__(self, sessions):
        self._sessions = sessions
        self.commits = 0

    async def execute(self, _stmt):
        return _FakeResult(self._sessions)

    async def commit(self):
        self.commits += 1


class _FakeSessionManager:
    def __init__(self, base: Path):
        self.base = base

    def _session_file(self, session_id: str) -> Path:
        return self.base / f"{session_id}.json"


def _session(session_id, output_dir):
    return SimpleNamespace(
        session_id=session_id,
        output_dir=output_dir,
        status="completed",
        completed_at=None,
    )


async def test_cleanup_deletes_artifacts_off_event_loop(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_PROJECT_SESSIONS_PER_USER", 1, raising=False)

    base = tmp_path / "sessions"
    base.mkdir()
    keep_file = base / "keep.json"
    keep_file.write_text("{}", encoding="utf-8")
    old_file = base / "old.json"
    old_file.write_text("{}", encoding="utf-8")
    old_dir = tmp_path / "projects" / "old"
    old_dir.mkdir(parents=True)
    (old_dir / "app.py").write_text("print(1)", encoding="utf-8")

    sessions = [_session("keep", None), _session("old", str(old_dir))]
    db = _FakeDB(sessions)

    sm = _FakeSessionManager(base)

    async def _get_sm():
        return sm

    monkeypatch.setattr(helpers, "get_session_manager", _get_sm)

    real_delete = helpers._delete_session_files
    worker_threads = []

    def _spy(session_file, output_dir):
        worker_threads.append(threading.get_ident())
        real_delete(session_file, output_dir)

    monkeypatch.setattr(helpers, "_delete_session_files", _spy)

    main_thread = threading.get_ident()
    await helpers._cleanup_old_session("u1", db)

    assert worker_threads, "清理逻辑必须实际执行删除"
    assert all(tid != main_thread for tid in worker_threads), "删除必须发生在工作线程"
    assert not old_file.exists()
    assert not old_dir.exists()
    assert keep_file.exists()
    assert db.commits == 1
    assert sessions[1].status == "cancelled"


def test_delete_session_files_removes_existing_and_tolerates_missing(tmp_path):
    session_file = tmp_path / "s.json"
    session_file.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "a.py").write_text("x", encoding="utf-8")

    helpers._delete_session_files(session_file, str(output_dir))

    assert not session_file.exists()
    assert not output_dir.exists()

    # 不存在的路径不应抛异常
    helpers._delete_session_files(tmp_path / "missing.json", str(tmp_path / "missing_dir"))
