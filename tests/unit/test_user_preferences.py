import pytest
import tempfile
from pathlib import Path

class TestUserPreferences:
    @pytest.fixture
    def prefs(self):
        from app.services.user_preferences import UserPreferences
        with tempfile.TemporaryDirectory() as tmpdir:
            old_db = UserPreferences.DB_PATH
            UserPreferences.DB_PATH = Path(tmpdir) / "prefs.db"
            p = UserPreferences()
            yield p
            UserPreferences.DB_PATH = old_db
    
    def test_get_set_preferences(self, prefs):
        prefs.set_preferences(1, {"code_style": "functional"})
        result = prefs.get_preferences(1)
        assert result["code_style"] == "functional"
    
    def test_update_stats(self, prefs):
        prefs.update_stats(1, "projects_created", 5)
        stats = prefs.get_stats(1)
        assert stats["projects_created"] == 5
    
    def test_get_db_size(self, prefs):
        size = prefs.get_db_size()
        assert size >= 0
