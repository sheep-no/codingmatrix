"""
安全审计日志工具

用于记录安全相关事件：
- 登录成功/失败
- 权限变更
- Token 刷新
- 敏感操作
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

security_logger = logging.getLogger("security")


async def log_security_event(
    event_type: str,
    user_id: int,
    details: Optional[Dict[str, Any]] = None,
    ip_address: str = None,
    success: bool = True
):
    """
    记录安全事件
    
    Args:
        event_type: 事件类型 (login_failed, login_success, permission_change, token_refresh 等)
        user_id: 用户 ID
        details: 事件详情
        ip_address: 客户端 IP
        success: 是否成功
    
    用法:
        await log_security_event(
            "login_failed",
            user_id=123,
            details={"reason": "wrong_password", "attempt": 3},
            ip_address="192.168.1.100",
            success=False
        )
    """
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "success": success,
        "ip_address": ip_address,
        "details": details or {}
    }
    
    if success:
        security_logger.info(json.dumps(event, ensure_ascii=False))
    else:
        # 失败事件用 WARNING 级别
        security_logger.warning(json.dumps(event, ensure_ascii=False))


# 便捷函数

async def log_login_success(user_id: int, ip: str = None):
    """记录登录成功"""
    await log_security_event("login_success", user_id, {"method": "token"}, ip, success=True)


async def log_login_failed(user_id: int, reason: str, ip: str = None):
    """记录登录失败"""
    await log_security_event(
        "login_failed",
        user_id,
        {"reason": reason},
        ip,
        success=False
    )


async def log_permission_change(user_id: int, old_role: str, new_role: str, admin_id: int):
    """记录权限变更"""
    await log_security_event(
        "permission_change",
        user_id,
        {
            "old_role": old_role,
            "new_role": new_role,
            "changed_by": admin_id
        },
        success=True
    )


async def log_token_refresh(user_id: int, token_type: str = "access"):
    """记录 Token 刷新"""
    await log_security_event(
        "token_refresh",
        user_id,
        {"token_type": token_type},
        success=True
    )


async def log_sensitive_operation(user_id: int, operation: str, target: str = None):
    """记录敏感操作"""
    await log_security_event(
        "sensitive_operation",
        user_id,
        {"operation": operation, "target": target},
        success=True
    )
