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
