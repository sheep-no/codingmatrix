"""
CSRF Token 管理模块

防止跨站请求伪造攻击
"""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Header, status
from fastapi.requests import Request
import logging

logger = logging.getLogger(__name__)


class CSRFTokenManager:
    """
    CSRF Token 管理器

    使用双重提交 Cookie 模式：
    1. Token 存储在 Cookie 中（HttpOnly=False，JavaScript 可读取）
    2. 请求时需要在 Header 中携带相同 Token
    3. 后端验证 Cookie 和 Header 中的 Token 是否一致
    """

    def __init__(self):
        self._tokens = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = 3600
        self._last_cleanup = datetime.now(timezone.utc)

    async def create_token(self, user_id: Optional[str] = None) -> str:
        """生成 CSRF Token"""
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        async with self._lock:
            self._tokens[token] = {
                "user_id": user_id,
                "expires": expires
            }

        await self._cleanup_if_needed()

        return token

    async def validate_token(self, token: str, user_id: Optional[str] = None) -> bool:
        """验证 CSRF Token"""
        async with self._lock:
            token_data = self._tokens.get(token)

            if not token_data:
                return False

            if datetime.now(timezone.utc) > token_data["expires"]:
                self._tokens.pop(token, None)
                return False

            if user_id and token_data.get("user_id") != user_id:
                return False

            return True

    async def invalidate_token(self, token: str):
        """使 Token 失效（logout 时调用）"""
        async with self._lock:
            self._tokens.pop(token, None)

    async def _cleanup_if_needed(self):
        """清理过期 token"""
        now = datetime.now(timezone.utc)
        if (now - self._last_cleanup).total_seconds() > self._cleanup_interval:
            async with self._lock:
                expired = [
                    token for token, data in self._tokens.items()
                    if now > data["expires"]
                ]
                for token in expired:
                    self._tokens.pop(token, None)
                self._last_cleanup = now


# 全局 CSRF 管理器实例
csrf_manager = CSRFTokenManager()


async def get_csrf_token() -> str:
    """获取新的 CSRF Token"""
    return await csrf_manager.create_token()


# =============================================================================
# FastAPI Depends 验证器
# =============================================================================

async def csrf_protect(
    request: Request,
    x_csrf_token: str = Header(None, alias="X-CSRF-Token")
) -> str:
    """
    CSRF 保护验证器

    使用方式：
    @router.post("/endpoint")
    async def endpoint(csrf: str = Depends(csrf_protect)):
        # csrf 验证通过
        pass

    异常：
        HTTPException(403): CSRF Token 无效或缺失
    """
    cookie_token = request.cookies.get("csrf_token")

    if not x_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="缺少 CSRF Token"
        )

    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cookie 中缺少 CSRF Token"
        )

    if x_csrf_token != cookie_token:
        logger.warning(f"CSRF Token 不匹配 | header={x_csrf_token[:10]}... | cookie={cookie_token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF Token 不匹配"
        )

    if not await csrf_manager.validate_token(x_csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF Token 无效或已过期"
        )

    return x_csrf_token


async def csrf_protect_optional(
    request: Request,
    x_csrf_token: str = Header(None, alias="X-CSRF-Token")
) -> Optional[str]:
    """
    可选的 CSRF 保护验证器

    如果 CSRF 验证失败，返回 None 而不是抛出异常
    适用于某些需要兼容性的场景
    """
    cookie_token = request.cookies.get("csrf_token")

    if not x_csrf_token or not cookie_token:
        return None

    if x_csrf_token != cookie_token:
        return None

    if not await csrf_manager.validate_token(x_csrf_token):
        return None

    return x_csrf_token
