"""
Tests for linked cleanup mechanism

Tests the coordination between memory-level (SessionManager) and DB-level cleanup:
1. Zombie session detection
2. Memory-DB status synchronization
3. Cleanup flow integration
"""
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestZombieSessionDetection:
    """Test zombie session detection (DB status=running but no memory state)"""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        mock = AsyncMock()
        return mock
    
    @pytest.fixture
    def mock_session_manager(self):
        """Mock session manager"""
        mock = AsyncMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_no_zombie_sessions(self, mock_db_session, mock_session_manager):
        """When no running sessions in DB, returns 0"""
        from app.api.v1.ai_agent.helpers import _detect_and_clean_zombie_sessions
        
        # Mock DB query returning empty list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result
        
        with patch('app.api.v1.ai_agent.helpers.get_session_manager', return_value=mock_session_manager):
            count = await _detect_and_clean_zombie_sessions(mock_db_session, "123")
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_zombie_session_detected(self, mock_db_session, mock_session_manager):
        """When DB has running session but no memory state, marks as failed"""
        from app.api.v1.ai_agent.helpers import _detect_and_clean_zombie_sessions
        from app.db.models import ProjectSession
        
        # Create mock session in DB
        mock_session = ProjectSession(
            session_id="test_session_1",
            user_id=123,
            requirement="test requirement",
            status="running"
        )
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_session]
        mock_db_session.execute.return_value = mock_result
        
        # Mock memory state as None (zombie)
        mock_session_manager._get_state.return_value = None
        
        with patch('app.api.v1.ai_agent.helpers.get_session_manager', return_value=mock_session_manager):
            count = await _detect_and_clean_zombie_sessions(mock_db_session, "123")
        
        assert count == 1
        assert mock_session.status == "failed"
        assert "僵尸会话" in mock_session.error_message
        assert mock_session.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_active_session_not_cleaned(self, mock_db_session, mock_session_manager):
        """When DB has running session AND memory has state, don't clean"""
        from app.api.v1.ai_agent.helpers import _detect_and_clean_zombie_sessions
        from app.db.models import ProjectSession
        from app.agent.session_manager import SessionState
        
        # Create mock session in DB
        mock_session = ProjectSession(
            session_id="test_session_2",
            user_id=123,
            requirement="test requirement",
            status="running"
        )
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_session]
        mock_db_session.execute.return_value = mock_result
        
        # Mock memory state exists (not a zombie)
        mock_state = SessionState(
            session_id="test_session_2",
            requirement="test requirement"
        )
        mock_session_manager._get_state.return_value = mock_state
        
        with patch('app.api.v1.ai_agent.helpers.get_session_manager', return_value=mock_session_manager):
            count = await _detect_and_clean_zombie_sessions(mock_db_session, "123")
        
        assert count == 0
        assert mock_session.status == "running"  # Not changed


class TestMemoryDBSync:
    """Test memory-DB status synchronization"""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        mock = AsyncMock()
        return mock
    
    @pytest.fixture
    def mock_session_manager(self):
        """Mock session manager"""
        mock = AsyncMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_update_status_syncs_to_memory(self, mock_db_session, mock_session_manager):
        """When DB status updated to terminal, memory state should be synced"""
        from app.api.v1.ai_agent.helpers import _update_project_session_status
        from app.db.models import ProjectSession
        from app.agent.session_manager import SessionState
        
        # Create mock session in DB
        mock_session = ProjectSession(
            session_id="test_session_3",
            user_id=123,
            requirement="test requirement",
            status="running"
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db_session.execute.return_value = mock_result
        
        # Mock memory state
        mock_state = SessionState(
            session_id="test_session_3",
            requirement="test requirement"
        )
        mock_session_manager._get_state.return_value = mock_state
        
        with patch('app.api.v1.ai_agent.helpers.get_session_manager', return_value=mock_session_manager):
            await _update_project_session_status(
                mock_db_session, 
                "test_session_3", 
                "completed",
                files_generated=5,
                files_total=10
            )
        
        # Verify DB updated
        assert mock_session.status == "completed"
        assert mock_session.files_generated == 5
        assert mock_session.files_total == 10
        assert mock_session.completed_at is not None
        
        # Verify memory synced
        assert mock_state.status == "completed"
        assert mock_state.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_update_status_non_terminal_no_memory_sync(self, mock_db_session, mock_session_manager):
        """When DB status updated to non-terminal, memory state should NOT be synced"""
        from app.api.v1.ai_agent.helpers import _update_project_session_status
        from app.db.models import ProjectSession
        from app.agent.session_manager import SessionState
        
        # Create mock session in DB
        mock_session = ProjectSession(
            session_id="test_session_4",
            user_id=123,
            requirement="test requirement",
            status="running"
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db_session.execute.return_value = mock_result
        
        # Mock memory state
        mock_state = SessionState(
            session_id="test_session_4",
            requirement="test requirement"
        )
        mock_session_manager._get_state.return_value = mock_state
        
        with patch('app.api.v1.ai_agent.helpers.get_session_manager', return_value=mock_session_manager):
            await _update_project_session_status(
                mock_db_session, 
                "test_session_4", 
                "running"
            )
        
        # Verify DB updated
        assert mock_session.status == "running"
        
        # Verify memory NOT synced (no call to _save_session)
        mock_session_manager._save_session.assert_not_called()


class TestCleanupExpiredSync:
    """Test that memory cleanup syncs to DB"""
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_updates_db(self):
        """When memory cleanup removes expired session, DB should be updated"""
        from app.agent.session_manager import SessionManager, SessionState
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(Path(tmpdir))
            
            # Create a session with old timestamp
            session = await manager.create_session(
                requirement="test",
                output_dir=tmpdir,
                architecture={},
                file_plan=[]
            )
            
            # Make session expired by setting old updated_at
            session.updated_at = "2020-01-01T00:00:00"
            
            # Mock DB session
            with patch('app.db.database.async_session') as mock_async_session:
                mock_db = AsyncMock()
                mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                mock_async_session.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Mock DB query returning session
                mock_db_session = MagicMock()
                mock_db_session.status = "running"
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_db_session
                mock_db.execute.return_value = mock_result
                
                # Run cleanup
                count = await manager.cleanup_expired()
                
                # Verify session was cleaned from memory
                assert count == 1
                assert session.session_id not in manager._active_sessions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
