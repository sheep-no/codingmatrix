"""
测试健康检查服务
"""
import pytest
from app.services.health_checker import (
    HealthChecker,
    HealthCheckResult,
    get_health_checker,
    health_checker
)


class TestHealthCheckResult:
    """测试健康检查结果数据类"""

    def test_create_result(self):
        """测试创建结果"""
        result = HealthCheckResult(
            status="healthy",
            response_time_ms=10.5,
            message="OK",
            details={"key": "value"}
        )
        assert result.status == "healthy"
        assert result.response_time_ms == 10.5
        assert result.message == "OK"
        assert result.details == {"key": "value"}

    def test_create_result_minimal(self):
        """测试创建最小结果"""
        result = HealthCheckResult(status="healthy")
        assert result.status == "healthy"
        assert result.response_time_ms == 0
        assert result.message is None
        assert result.details is None


class TestHealthChecker:
    """测试健康检查服务"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        checker1 = get_health_checker()
        checker2 = get_health_checker()
        assert checker1 is checker2
        assert checker1 is health_checker

    def test_default_version(self):
        """测试默认版本"""
        checker = HealthChecker()
        assert checker._version == "v3.0"

    @pytest.mark.asyncio
    async def test_check_live(self):
        """测试存活检查"""
        checker = HealthChecker()
        result = await checker.check_live()

        assert result["status"] == "alive"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_check_api(self):
        """测试 API 检查"""
        checker = HealthChecker()
        result = await checker.check_api()

        assert result.status == "healthy"
        assert result.response_time_ms >= 0
        assert result.message == "API 服务正常运行"
        assert "version" in result.details
        assert "uptime_seconds" in result.details


class TestHealthCheckerIntegration:
    """健康检查服务集成测试"""

    @pytest.mark.asyncio
    async def test_check_all_structure(self):
        """测试 check_all 返回结构"""
        checker = HealthChecker()
        result = await checker.check_all()

        assert "status" in result
        assert "timestamp" in result
        assert "checks" in result
        assert "version" in result

        checks = result["checks"]
        assert "api" in checks
        assert "database" in checks
        assert "redis" in checks
        assert "celery" in checks
        assert "websocket" in checks
        assert "system" in checks

    @pytest.mark.asyncio
    async def test_check_ready_structure(self):
        """测试 check_ready 返回结构"""
        checker = HealthChecker()
        result = await checker.check_ready()

        assert "status" in result
        assert "timestamp" in result
        assert result["status"] in ["ready", "not_ready"]

    @pytest.mark.asyncio
    async def test_check_live_structure(self):
        """测试 check_live 返回结构"""
        checker = HealthChecker()
        result = await checker.check_live()

        assert result["status"] == "alive"
        assert "timestamp" in result
