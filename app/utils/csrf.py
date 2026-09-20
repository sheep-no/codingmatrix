"""
CSRF Token 管理模块

防止跨站请求伪造攻击
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional

from fastapi import HTTPException, Header, status
from fastapi.requests import Request

from app.core.config import settings

logger = logging.getLogger(__name__)


class CSRFTokenManager:
    """
    CSRF Token 管理器

    使用双重提交 Cookie 模式：
    1. Token 存储在 Cookie 中（HttpOnly=False，JavaScript 可读取）
    2. 请求时需要在 Header 中携带相同 Token
    3. 后端验证 Cookie 和 Header 中的 Token 是否一致

    Token 本身是无状态的：由「过期时间 + 用户绑定」载荷与 HMAC-SHA256
    签名组成，校验时重新计算签名即可。不依赖进程内状态，因此多 worker
    或多实例部署下，任一进程签发的 token 都能在另一进程校验通过，进程
    重启也不会使已签发 token 全部失效。
    """

    TOKEN_TTL_SECONDS = 3600

    def _signature(self, payload: str) -> str:
        """对载荷做 HMAC-SHA256，作为 token 的完整性凭证。"""
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def create_token(self, user_id: Optional[str] = None) -> str:
        """生成 CSRF Token"""
        payload = json.dumps(
            {
                "exp": int(time.time()) + self.TOKEN_TTL_SECONDS,
                "uid": user_id or "",
                "nonce": secrets.token_urlsafe(16),
            },
            separators=(",", ":"),
        )
        encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
        return f"{encoded}.{self._signature(payload)}"

    async def validate_token(self, token: str, user_id: Optional[str] = None) -> bool:
        """验证 CSRF Token"""
        try:
            encoded, signature = token.split(".", 1)
            payload = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False

        if not hmac.compare_digest(self._signature(payload), signature):
            return False

        try:
            data = json.loads(payload)
            expires = int(data["exp"])
        except (ValueError, TypeError, KeyError):
            return False

        if time.time() > expires:
            return False

        if user_id and data.get("uid") and data["uid"] != user_id:
            return False

        return True

    async def invalidate_token(self, token: str) -> None:
        """无状态 token 无法在服务端撤销，登出通过清除 Cookie 完成。"""
        return None


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
