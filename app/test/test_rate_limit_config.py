"""
测试限流配置服务
"""
import pytest
from app.services.rate_limit_config import (
    RateLimitConfig,
    RateLimitRule,
    get_rate_limit_config,
    rate_limit_config
)


class TestRateLimitConfig:
    """测试限流配置"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        config1 = get_rate_limit_config()
        config2 = get_rate_limit_config()
        assert config1 is config2
        assert config1 is rate_limit_config

    def test_default_global_limit(self):
        """测试默认全局限流"""
        limit, window = rate_limit_config.global_limit
        assert limit == 1000
        assert window == 60

    def test_default_ip_limit(self):
        """测试默认 IP 限流"""
        limit, window = rate_limit_config.ip_limit
        assert limit == 100
        assert window == 60

    def test_default_user_limit(self):
        """测试默认用户限流"""
        limit, window = rate_limit_config.user_limit
        assert limit == 50
        assert window == 60

    def test_set_global_limit(self):
        """测试设置全局限流"""
        rate_limit_config.set_global_limit(2000, 120)
        limit, window = rate_limit_config.global_limit
        assert limit == 2000
        assert window == 120

    def test_set_ip_limit(self):
        """测试设置 IP 限流"""
        rate_limit_config.set_ip_limit(200, 60)
        limit, window = rate_limit_config.ip_limit
        assert limit == 200
        assert window == 60

    def test_set_user_limit(self):
        """测试设置用户限流"""
        rate_limit_config.set_user_limit(100, 60)
        limit, window = rate_limit_config.user_limit
        assert limit == 100
        assert window == 60

    def test_set_endpoint_rule(self):
        """测试设置端点限流规则"""
        rate_limit_config.set_endpoint_rule("/api/v1/test", 30, 60)
        limit, window = rate_limit_config.get_endpoint_rule("/api/v1/test")
        assert limit == 30
        assert window == 60

    def test_get_unknown_endpoint_default(self):
        """测试获取未知端点使用默认配置"""
        limit, window = rate_limit_config.get_endpoint_rule("/api/v1/unknown")
        assert limit == 60
        assert window == 60

    def test_remove_endpoint_rule(self):
        """测试移除端点限流规则"""
        rate_limit_config.set_endpoint_rule("/api/v1/remove_test", 30, 60)
        rate_limit_config.remove_endpoint_rule("/api/v1/remove_test")
        limit, window = rate_limit_config.get_endpoint_rule("/api/v1/remove_test")
        assert limit == 60
        assert window == 60

    def test_enabled_property(self):
        """测试启用/禁用"""
        assert rate_limit_config.enabled is True
        rate_limit_config.set_enabled(False)
        assert rate_limit_config.enabled is False
        rate_limit_config.set_enabled(True)
        assert rate_limit_config.enabled is True

    def test_to_dict(self):
        """测试转换为字典"""
        data = rate_limit_config.to_dict()
        assert "enabled" in data
        assert "global" in data
        assert "by_ip" in data
        assert "by_user" in data
        assert "endpoints" in data
        assert "limit" in data["global"]
        assert "window" in data["global"]


class TestRateLimitRule:
    """测试限流规则数据类"""

    def test_create_rule(self):
        """测试创建限流规则"""
        rule = RateLimitRule(limit=100, window=60)
        assert rule.limit == 100
        assert rule.window == 60
