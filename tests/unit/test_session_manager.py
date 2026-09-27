import pytest
import asyncio
import tempfile
from pathlib import Path

class TestSessionManager:
    @pytest.fixture
    def manager(self):
        from app.agent.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SessionManager(Path(tmpdir))
    
    def test_create_and_resume_session(self, manager):
        with tempfile.TemporaryDirectory() as output_dir:
            session = asyncio.run(manager.create_session(
                requirement="test",
                output_dir=output_dir,
                architecture={},
                file_plan=[]
            ))
            assert session is not None
            assert session.session_id is not None
            
            resumed = asyncio.run(manager.resume_session(session.session_id))
            assert resumed is not None
    
    def test_detect_no_changes(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(manager.create_session(
                requirement="test",
                output_dir=tmpdir,
                architecture={},
                file_plan=[{"path": "main.py"}]
            ))
            
            Path(tmpdir, "main.py").write_text("print('hello')")
            
            result = asyncio.run(manager.detect_incremental_changes(
                session.session_id, "test", Path(tmpdir)
            ))
            assert "state" in result

    def test_default_session_id_is_unique(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = asyncio.run(manager.create_session(
                requirement="a", output_dir=tmpdir, file_plan=[]
            ))
            second = asyncio.run(manager.create_session(
                requirement="b", output_dir=tmpdir, file_plan=[]
            ))
        assert first.session_id != second.session_id

    def test_small_changes_not_duplicated_in_unchanged(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(manager.create_session(
                requirement="test",
                output_dir=tmpdir,
                architecture={},
                file_plan=[{"path": "a.py"}]
            ))
            Path(tmpdir, "a.py").write_text("print('v2')")
            # 过期 hash + 已有 embedding，进入语义相似度分支
            fs = session.file_statuses["a.py"]
            fs.status = "completed"
            fs.content_hash = "stale-hash"
            fs.content_embedding = [1.0, 0.0]
            asyncio.run(manager._save_session(session))

            result = asyncio.run(manager.detect_incremental_changes(
                session.session_id, "test", Path(tmpdir),
                file_embeddings={"a.py": [1.0, 0.05]}
            ))

        assert result["small_changes"] == ["a.py"]
        assert result["unchanged_files"] == ["a.py"]
        assert result["state"].unchanged_files == ["a.py"]

    def test_unreadable_file_treated_as_changed(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(manager.create_session(
                requirement="test",
                output_dir=tmpdir,
                architecture={},
                file_plan=[{"path": "bad.py"}]
            ))
            # 非法 UTF-8 内容会触发 UnicodeDecodeError，不应中断增量检测
            Path(tmpdir, "bad.py").write_bytes(b"\xff\xfe\x00binary")

            result = asyncio.run(manager.detect_incremental_changes(
                session.session_id, "test", Path(tmpdir)
            ))

        assert result["changed_files"] == ["bad.py"]
        assert result["state"].changed_files == ["bad.py"]

    def test_session_status_exposes_reuse_evidence(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(manager.create_session(
                requirement="test",
                output_dir=tmpdir,
                architecture={},
                file_plan=[{"path": "a.py"}]
            ))
            status = asyncio.run(manager.get_session_status(session.session_id))

        assert status["files"]["a.py"]["content_hash"] == ""
        assert status["files"]["a.py"]["has_embedding"] is False

    def test_resume_session_restores_from_disk_when_not_cached(self, manager):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(manager.create_session(
                requirement="persisted", output_dir=tmpdir, architecture={}, file_plan=[]
            ))
            manager._active_sessions.clear()
            resumed = asyncio.run(manager.resume_session(session.session_id))

        assert resumed is not None
        assert resumed.session_id == session.session_id
        assert resumed.requirement == "persisted"

    def test_fresh_manager_restores_session_from_disk(self, manager):
        from app.agent.session_manager import SessionManager

        with tempfile.TemporaryDirectory() as tmpdir:
            session = asyncio.run(manager.create_session(
                requirement="persisted", output_dir=tmpdir, architecture={}, file_plan=[]
            ))
            # 模拟进程重启：新实例，内存中没有该会话，只能从磁盘恢复
            fresh = SessionManager(manager.session_dir)
            resumed = asyncio.run(fresh.resume_session(session.session_id))

        assert resumed is not None
        assert resumed.session_id == session.session_id


def _record_open_threads(monkeypatch):
    """记录每次 builtins.open 调用所在的线程 id。"""
    import builtins
    import threading

    records = []
    real_open = builtins.open

    def spy(file, *args, **kwargs):
        records.append((threading.get_ident(), str(file)))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    return records


def test_save_session_writes_file_off_event_loop(monkeypatch):
    import threading
    from app.agent.session_manager import SessionManager

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(Path(tmpdir))
        main_thread = threading.get_ident()
        session = asyncio.run(manager.create_session(
            requirement="test", output_dir=tmpdir, architecture={}, file_plan=[]
        ))

        records = _record_open_threads(monkeypatch)
        asyncio.run(manager._save_session(session))

    written = [
        tid for tid, path in records
        if session.session_id in path and path.endswith(".tmp")
    ]
    assert written, "未观察到会话文件写入"
    assert all(tid != main_thread for tid in written)


def test_resume_session_reads_file_off_event_loop(monkeypatch):
    import threading
    from app.agent.session_manager import SessionManager

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(Path(tmpdir))
        main_thread = threading.get_ident()
        session = asyncio.run(manager.create_session(
            requirement="test", output_dir=tmpdir, architecture={}, file_plan=[]
        ))
        manager._active_sessions.clear()

        records = _record_open_threads(monkeypatch)
        resumed = asyncio.run(manager.resume_session(session.session_id))

    assert resumed is not None
    read = [
        tid for tid, path in records
        if session.session_id in path and path.endswith(".json")
    ]
    assert read, "未观察到会话文件读取"
    assert all(tid != main_thread for tid in read)


def test_detect_incremental_reads_project_files_off_event_loop(monkeypatch):
    import threading
    from app.agent.session_manager import SessionManager

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(Path(tmpdir))
        main_thread = threading.get_ident()
        session = asyncio.run(manager.create_session(
            requirement="test",
            output_dir=tmpdir,
            architecture={},
            file_plan=[{"path": "main.py"}],
        ))
        manager._active_sessions.clear()
        Path(tmpdir, "main.py").write_text("print('hello')")

        records = _record_open_threads(monkeypatch)
        result = asyncio.run(manager.detect_incremental_changes(
            session.session_id, "test", Path(tmpdir)
        ))

    assert "state" in result
    read = [tid for tid, path in records if path.endswith("main.py")]
    assert read, "未观察到项目文件读取"
    assert all(tid != main_thread for tid in read)
