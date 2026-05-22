"""
ConcurrentLimitManager - 并发限制动态管理器

v4.8.0 新增：
- 热调整并发限制（无需重启服务）
- 渐进式生效（已有会话自然完成）
- 审计日志记录每次变更
- 负载自适应推荐
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LimitChangeRecord:
    """限制变更记录"""
    role: str
    old_limit: int
    new_limit: int
    changed_by: str
    timestamp: datetime
    reason: str = ""


class ConcurrentLimitManager:
    """
    并发限制动态管理器

    支持：
    - 通过 API 更新限制（无需重启）
    - 渐进式生效：已有会话自然完成，新限制只对新请求生效
    - 审计日志：记录每次变更的时间、操作者、新旧值
    - 负载自适应：根据系统负载推荐合适的限制值
    """

    BASE_LIMITS = {
        "free": 1,
        "basic": 2,
        "premium": 5,
        "enterprise": 10,
    }

    def __init__(self, load_monitor=None):
        self.load_monitor = load_monitor
        self._limits: Dict[str, int] = dict(self.BASE_LIMITS)
        self._active_sessions: Dict[str, int] = {}
        self._change_log: List[LimitChangeRecord] = []

    async def update_limit(
        self,
        role: str,
        new_limit: int,
        changed_by: str,
        reason: str = "",
    ) -> LimitChangeRecord:
        """
        更新并发限制（热调整）

        Args:
            role: 用户角色
            new_limit: 新的限制值
            changed_by: 操作者
            reason: 变更原因

        Returns:
            LimitChangeRecord 变更记录
        """
        old_limit = self._limits.get(role, 1)
        self._limits[role] = new_limit

        record = LimitChangeRecord(
            role=role,
            old_limit=old_limit,
            new_limit=new_limit,
            changed_by=changed_by,
            timestamp=datetime.now(),
            reason=reason,
        )
        self._change_log.append(record)

        logger.info(
            f"并发限制更新: {role} {old_limit} -> {new_limit} "
            f"(by {changed_by})"
        )
        return record

    def can_create_session(self, role: str) -> bool:
        """
        检查是否可以创建新会话

        渐进式生效：当前活跃会话数 < 当前限制值时允许。
        已有的超额会话允许继续运行。
        """
        active = self._active_sessions.get(role, 0)
        limit = self._limits.get(role, 1)
        return active < limit

    def register_session(self, role: str) -> None:
        """注册新会话"""
        self._active_sessions[role] = self._active_sessions.get(role, 0) + 1

    def unregister_session(self, role: str) -> None:
        """注销会话（会话结束时调用）"""
        if role in self._active_sessions:
            self._active_sessions[role] -= 1
            if self._active_sessions[role] <= 0:
                del self._active_sessions[role]

    def get_limit(self, role: str) -> int:
        """获取当前限制值"""
        return self._limits.get(role, 1)

    def get_active_count(self, role: str) -> int:
        """获取当前活跃会话数"""
        return self._active_sessions.get(role, 0)

    async def get_recommended_limits(self) -> Dict[str, int]:
        """
        根据系统负载推荐限制值

        高负载时降低限制，低负载时恢复基础限制。

        Returns:
            {role: recommended_limit}
        """
        if not self.load_monitor:
            return dict(self._limits)

        try:
            load = await self.load_monitor.get_system_load()
            recommendations = {}

            for role, base_limit in self._limits.items():
                if load.cpu_percent > 80 or load.memory_percent > 80:
                    recommendations[role] = max(1, base_limit // 2)
                elif load.cpu_percent > 60 or load.memory_percent > 60:
                    recommendations[role] = max(1, int(base_limit * 0.75))
                else:
                    recommendations[role] = base_limit

            return recommendations
        except Exception:
            return dict(self._limits)

    def get_change_history(self, limit: int = 50) -> List[LimitChangeRecord]:
        """获取变更历史"""
        return self._change_log[-limit:]