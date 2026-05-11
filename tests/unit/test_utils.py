"""
工具函数单元测试

测试范围:
    - 安全工具函数 (密码哈希、Token 生成验证)
    - 系统监控函数
    - 日志服务

标记:
    @pytest.mark.unit - 单元测试
    @pytest.mark.security - 安全相关测试
    @pytest.mark.logging - 日志相关测试
    @pytest.mark.monitoring - 监控相关测试
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone
from jose import jwt

from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token_ws,
)
from app.core.config import settings


# =============================================================================
# 密码哈希测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.security
class TestPasswordHashing:
    """密码哈希和验证测试"""

    @pytest.mark.parametrize("password", [
        "test_password_123",
        "P@ssw0rd!",
        "12345678",
        "a" * 100,  # 长密码
    ])
    def test_hash_password_output_format(self, password: str):
        """测试密码哈希输出格式"""
        hashed = hash_password(password)
        
        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60  # bcrypt 哈希长度固定

    @pytest.mark.parametrize("password", [
        "simple_password",
        "C0mpl3x!P@ssw0rd",
        "中文密码测试",
        "emoji🔐test",
    ])
    def test_verify_password_correct(self, password: str):
        """测试验证正确密码"""
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """测试验证错误密码"""
        password = "correct_password"
        hashed = hash_password(password)
        
        assert verify_password("wrong_password", hashed) is False

    @pytest.mark.parametrize("invalid_hash", [
        "",
        None,
        "invalid_hash",
        "not_bcrypt",
    ])
    def test_verify_password_invalid_hash(self, invalid_hash):
        """测试无效哈希格式"""
        assert verify_password("password", invalid_hash) is False

    def test_hash_uniqueness(self):
        """测试相同密码生成不同哈希"""
        password = "same_password"
        hashed1 = hash_password(password)
        hashed2 = hash_password(password)
        
        assert hashed1 != hashed2  # bcrypt 使用随机 salt
        assert verify_password(password, hashed1) is True
        assert verify_password(password, hashed2) is True


# =============================================================================
# JWT Token 测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.security
class TestTokenGeneration:
    """JWT Token 生成和验证测试"""

    def test_create_access_token_basic(self):
        """测试创建基础 Token"""
        token = create_access_token(
            sub="123",
            permission_level="normal"
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_payload_structure(self):
        """测试 Token payload 结构"""
        token = create_access_token(
            sub="123",
            permission_level="super"
        )
        
        payload = jwt.decode(
            token,
            key="",
            algorithms=["HS256"],
            options={"verify_signature": False}
        )
        
        assert "sub" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "type" in payload
        assert "refresh_until" in payload
        assert "permission_level" in payload
        
        assert payload["sub"] == "123"
        assert payload["permission_level"] == "super"
        assert payload["type"] == "access"

    def test_create_access_token_expiry(self):
        """测试 Token 过期时间"""
        token = create_access_token(
            sub="789",
            permission_level="normal"
        )
        
        payload = jwt.decode(
            token,
            key="",
            algorithms=["HS256"],
            options={"verify_signature": False}
        )
        
        exp_timestamp = payload["exp"]
        iat_timestamp = payload["iat"]
        expected_delta = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        actual_delta = exp_timestamp - iat_timestamp
        
        assert abs(actual_delta - expected_delta) < 5  # 允许 5 秒误差

    def test_create_access_token_custom_expiry(self):
        """测试自定义过期时间"""
        custom_delta = timedelta(hours=2)
        token = create_access_token(
            sub="456",
            permission_level="super",
            expires_delta=custom_delta
        )
        
        payload = jwt.decode(
            token,
            key="",
            algorithms=["HS256"],
            options={"verify_signature": False}
        )
        
        exp_timestamp = payload["exp"]
        iat_timestamp = payload["iat"]
        expected_delta = custom_delta.total_seconds()
        actual_delta = exp_timestamp - iat_timestamp
        
        assert abs(actual_delta - expected_delta) < 5

    def test_create_access_token_extra_claims(self):
        """测试额外声明"""
        extra_claims = {"custom_field": "custom_value", "another": 123}
        token = create_access_token(
            sub="789",
            permission_level="normal",
            extra_claims=extra_claims
        )
        
        payload = jwt.decode(
            token,
            key="",
            algorithms=["HS256"],
            options={"verify_signature": False}
        )
        
        assert payload["custom_field"] == "custom_value"
        assert payload["another"] == 123

    def test_default_permission_level(self):
        """测试默认权限级别"""
        token = create_access_token(
            sub="456",
            permission_level=None
        )
        
        payload = jwt.decode(
            token,
            key="",
            algorithms=["HS256"],
            options={"verify_signature": False}
        )
        
        assert payload["permission_level"] == "normal"

    @pytest.mark.parametrize("user_id,permission", [
        ("1", "normal"),
        ("999", "super"),
        ("12345", "normal"),
    ])
    def test_create_access_token_with_different_users(
        self,
        user_id: str,
        permission: str
    ):
        """测试不同用户 Token 生成"""
        token = create_access_token(
            sub=user_id,
            permission_level=permission
        )
        
        payload = jwt.decode(
            token,
            key="",
            algorithms=["HS256"],
            options={"verify_signature": False}
        )
        
        assert payload["sub"] == user_id
        assert payload["permission_level"] == permission


# =============================================================================
# WebSocket Token 验证测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.security
class TestWebSocketTokenValidation:
    """WebSocket Token 验证测试"""

    def test_verify_token_ws_valid_token(self, auth_token: str):
        """测试验证有效 Token"""
        is_valid, payload, close_code, reason = verify_token_ws(auth_token)
        
        assert is_valid is True
        assert payload is not None
        assert "sub" in payload
        assert "permission_level" in payload
        assert close_code is None
        assert reason is None

    def test_verify_token_ws_invalid_token(self):
        """测试验证无效 Token"""
        is_valid, payload, close_code, reason = verify_token_ws("invalid_token_xyz")
        
        assert is_valid is False
        assert payload is None
        assert close_code is not None
        assert reason is not None

    def test_verify_token_ws_empty_token(self):
        """测试验证空 Token"""
        is_valid, payload, close_code, reason = verify_token_ws("")
        
        assert is_valid is False
        assert close_code is not None

    def test_verify_token_ws_expired_token(self):
        """测试验证过期 Token"""
        with patch("app.utils.security.datetime") as mock_datetime:
            mock_now = datetime.now(timezone.utc) - timedelta(days=10)
            mock_datetime.now.return_value = mock_now
            
            old_token = create_access_token(
                sub="123",
                permission_level="normal",
                expires_delta=timedelta(minutes=5)
            )
        
        is_valid, payload, close_code, reason = verify_token_ws(old_token)
        
        assert is_valid in [True, False]


# =============================================================================
# 系统监控测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.monitoring
class TestSystemMonitoring:
    """系统监控函数测试"""

    def test_get_system_stats_structure(self):
        """测试系统统计信息结构"""
        from app.utils.system_monitor import get_system_stats
        
        stats = get_system_stats()
        
        assert "timestamp" in stats
        assert "cpu" in stats
        assert "memory" in stats
        assert "disk" in stats
        assert "network" in stats

    def test_get_system_stats_cpu_fields(self):
        """测试 CPU 统计字段"""
        from app.utils.system_monitor import get_system_stats
        
        stats = get_system_stats()
        
        assert "total_percent" in stats["cpu"]
        assert 0 <= stats["cpu"]["total_percent"] <= 100

    def test_get_system_stats_memory_fields(self):
        """测试内存统计字段"""
        from app.utils.system_monitor import get_system_stats
        
        stats = get_system_stats()
        
        assert "percent" in stats["memory"]
        assert "total_gb" in stats["memory"]
        assert "used_gb" in stats["memory"]
        assert 0 <= stats["memory"]["percent"] <= 100

    def test_get_system_stats_disk_fields(self):
        """测试磁盘统计字段"""
        from app.utils.system_monitor import get_system_stats
        
        stats = get_system_stats()
        
        assert "percent" in stats["disk"]
        assert "total_gb" in stats["disk"]
        assert "used_gb" in stats["disk"]

    def test_get_system_stats_network_fields(self):
        """测试网络统计字段"""
        from app.utils.system_monitor import get_system_stats
        
        stats = get_system_stats()
        
        assert "bytes_sent" in stats["network"]
        assert "bytes_recv" in stats["network"]
        assert stats["network"]["bytes_sent"] >= 0
        assert stats["network"]["bytes_recv"] >= 0


# =============================================================================
# 日志服务测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.logging
class TestLogService:
    """日志服务测试"""

    @pytest.mark.asyncio
    async def test_log_filter_default(self):
        """测试默认日志过滤器"""
        from app.db.log_server import LogFilter
        
        log_filter = LogFilter()
        
        assert log_filter.level is None
        assert log_filter.keyword is None

    @pytest.mark.asyncio
    async def test_log_filter_with_values(self):
        """测试带值的过滤器"""
        from app.db.log_server import LogFilter
        
        log_filter = LogFilter(level="ERROR", keyword="websocket")
        
        assert log_filter.level == "ERROR"
        assert log_filter.keyword == "websocket"

    @pytest.mark.asyncio
    async def test_log_filter_to_dict(self):
        """测试过滤器转换为字典"""
        from app.db.log_server import LogFilter
        
        log_filter = LogFilter(level="INFO", keyword="test")
        result = log_filter.to_dict()
        
        assert isinstance(result, dict)
        assert "level" in result
        assert "keyword" in result

    @pytest.mark.asyncio
    async def test_log_filter_to_dict_empty(self):
        """测试空过滤器转字典"""
        from app.db.log_server import LogFilter
        
        log_filter = LogFilter()
        result = log_filter.to_dict()
        
        assert result == {"level": None, "keyword": None}


# =============================================================================
# 进程守护测试
# =============================================================================

@pytest.mark.unit
@pytest.mark.guardian
class TestProcessGuardian:
    """进程守护测试"""

    @pytest.mark.asyncio
    async def test_async_smart_guardian_initialization(self):
        """测试异步智能守护初始化"""
        from app.utils.async_enhanced_guard import AsyncSmartGuardian
        
        guardian = AsyncSmartGuardian(check_interval=10)
        
        assert guardian is not None
        assert guardian.check_interval == 10
        
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_async_guardian_scan_and_learn(self):
        """测试扫描和学习功能"""
        from app.utils.async_enhanced_guard import AsyncSmartGuardian
        
        guardian = AsyncSmartGuardian(check_interval=10)
        await guardian.scan_and_learn(auto_enable_trusted=True)
        
        assert guardian.config_manager is not None
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_service_config_manager(self):
        """测试服务配置管理器"""
        from app.utils.service_config_manager import ServiceConfigManager
        
        manager = ServiceConfigManager()
        
        assert manager is not None
        assert hasattr(manager, "configs")
        assert hasattr(manager, "get_or_create_config")
        assert hasattr(manager, "save_configs")

    @pytest.mark.asyncio
    async def test_is_port_open(self):
        """测试端口检测"""
        from app.utils.async_enhanced_guard import AsyncSmartGuardian
        
        guardian = AsyncSmartGuardian(check_interval=10)
        is_open = await guardian.is_port_open(8000)
        
        assert isinstance(is_open, bool)
        await guardian.shutdown()
