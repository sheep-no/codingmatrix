"""
限流配置服务

提供动态限流配置管理，支持多级限流策略
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """限流规则"""
    limit: int
    window: int


class RateLimitConfig:
    """限流配置数据类"""

    def __init__(self):
        self._global_limit = RateLimitRule(limit=1000, window=60)
        self._ip_limit = RateLimitRule(limit=100, window=60)
        self._user_limit = RateLimitRule(limit=50, window=60)
        self._endpoint_rules: Dict[str, RateLimitRule] = {
            "/api/v1/login": RateLimitRule(limit=5, window=60),
            "/api/v1/register": RateLimitRule(limit=10, window=60),
            "/api/v1/refresh": RateLimitRule(limit=10, window=60),
            "/api/v1/files/upload": RateLimitRule(limit=20, window=60),
            "/api/v1/code": RateLimitRule(limit=60, window=60),
            "/api/v1/generate": RateLimitRule(limit=60, window=60),
            "/api/v1/pptx": RateLimitRule(limit=60, window=60),
            "/api/v1/ai_agent": RateLimitRule(limit=10, window=60),
            "/api/v1/aicloud": RateLimitRule(limit=10, window=60),
            "/api/v1/workflow": RateLimitRule(limit=10, window=60),
        }
        self._enabled = True
        self._lock = threading.RLock()

    @property
    def global_limit(self) -> Tuple[int, int]:
        return (self._global_limit.limit, self._global_limit.window)

    @property
    def ip_limit(self) -> Tuple[int, int]:
        return (self._ip_limit.limit, self._ip_limit.window)

    @property
    def user_limit(self) -> Tuple[int, int]:
        return (self._user_limit.limit, self._user_limit.window)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_endpoint_rule(self, endpoint: str) -> Tuple[int, int]:
        """获取端点限流规则"""
        if endpoint in self._endpoint_rules:
            rule = self._endpoint_rules[endpoint]
            return (rule.limit, rule.window)
        return (60, 60)

    def set_global_limit(self, limit: int, window: int):
        """设置全局限流"""
        with self._lock:
            self._global_limit = RateLimitRule(limit=limit, window=window)
        logger.info(f"全局限流已更新 | limit={limit} | window={window}")

    def set_ip_limit(self, limit: int, window: int):
        """设置 IP 限流"""
        with self._lock:
            self._ip_limit = RateLimitRule(limit=limit, window=window)
        logger.info(f"IP限流已更新 | limit={limit} | window={window}")

    def set_user_limit(self, limit: int, window: int):
        """设置用户限流"""
        with self._lock:
            self._user_limit = RateLimitRule(limit=limit, window=window)
        logger.info(f"用户限流已更新 | limit={limit} | window={window}")

    def set_endpoint_rule(self, endpoint: str, limit: int, window: int):
        """设置端点限流规则"""
        with self._lock:
            self._endpoint_rules[endpoint] = RateLimitRule(limit=limit, window=window)
        logger.info(f"端点限流已更新 | endpoint={endpoint} | limit={limit} | window={window}")

    def remove_endpoint_rule(self, endpoint: str):
        """移除端点限流规则"""
        with self._lock:
            if endpoint in self._endpoint_rules:
                del self._endpoint_rules[endpoint]
        logger.info(f"端点限流已移除 | endpoint={endpoint}")

    def set_enabled(self, enabled: bool):
        """启用/禁用限流"""
        with self._lock:
            self._enabled = enabled
        logger.info(f"限流已{'启用' if enabled else '禁用'}")

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "enabled": self._enabled,
            "global": {
                "limit": self._global_limit.limit,
                "window": self._global_limit.window
            },
            "by_ip": {
                "limit": self._ip_limit.limit,
                "window": self._ip_limit.window
            },
            "by_user": {
                "limit": self._user_limit.limit,
                "window": self._user_limit.window
            },
            "endpoints": {
                endpoint: {
                    "limit": rule.limit,
                    "window": rule.window
                }
                for endpoint, rule in self._endpoint_rules.items()
            }
        }


_rate_limit_config_instance: Optional[RateLimitConfig] = None


def get_rate_limit_config() -> RateLimitConfig:
    """获取限流配置单例"""
    global _rate_limit_config_instance
    if _rate_limit_config_instance is None:
        _rate_limit_config_instance = RateLimitConfig()
    return _rate_limit_config_instance


rate_limit_config = get_rate_limit_config()
