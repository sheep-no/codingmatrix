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
