import pytest

class TestResourceGuard:
    @pytest.fixture
    def guard(self):
        from app.utils.resource_guard import ResourceGuard
        return ResourceGuard()
    
    def test_check_resources(self, guard):
        result = guard.check_resources()
        assert isinstance(result, bool)
    
    def test_get_safe_concurrency(self, guard):
        concurrency = guard.get_safe_concurrency()
        assert 2 <= concurrency <= 4
    
    def test_get_resource_status(self, guard):
        status = guard.get_resource_status()
        assert "memory_percent" in status
        assert "cpu_percent" in status
        assert "disk_percent" in status
    
    def test_get_available_disk_mb(self, guard):
        available = guard.get_available_disk_mb()
        assert available > 0
