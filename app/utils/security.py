from typing import Optional
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.exceptions import WebSocketException
from pydantic import ValidationError
from starlette import status
import bcrypt
import re

from app.core.config import settings

security = HTTPBearer()
WS_TOKEN_EXPIRED = 4001
WS_TOKEN_REFRESH_EXPIRED = 4003


def validate_password_strength(password: str) -> tuple[bool, str]:
    """验证密码强度"""
    if len(password) < 8:
        return False, "密码长度至少为 8 个字符"
    
    if not re.search(r'[A-Z]', password):
        return False, "密码必须包含大写字母"
    
    if not re.search(r'[a-z]', password):
        return False, "密码必须包含小写字母"
    
    if not re.search(r'\d', password):
        return False, "密码必须包含数字"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;\'`~]', password):
        return False, "密码必须包含特殊字符"
    
    common_passwords = [
        'password', '123456', '12345678', '123456789', '1234567890',
        'qwerty', 'abc123', 'password123', 'password1234',
        'admin', 'admin123', 'admin1234', 'root', 'root123',
        'letmein', 'welcome', 'monkey', '12345', '1234',
        'dragon', 'master', 'hello', 'charlie', 'donald',
        'qwerty123', 'passw0rd', 'p@ssword', 'p@ssw0rd',
        'iloveyou', 'shadow', 'sunshine', 'princess', 'football',
        'michael', 'jennifer', 'jordan', 'superman', 'batman'
    ]
    if password.lower() in common_passwords:
        return False, "密码过于简单，请使用更复杂的密码"
    
    return True, "密码强度符合要求"


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    if not hashed_password or not hashed_password.startswith("$2b$"):
        return False
    password_bytes = password.encode('utf-8')[:72]
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)


def create_access_token(sub: str, permission_level: str, 
                        expires_delta: Optional[timedelta] = None,
                        role: str = "user",
                        extra_claims: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    refresh_until = now + timedelta(days=5)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": sub, 
        "exp": expire, 
        "iat": now,
        "type": "access",
        "refresh_until": int(refresh_until.timestamp()),
        "permission_level": permission_level or "normal",
        "role": role
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_and_validate_token(token: str, verify_expiry: bool = True) -> tuple[bool, dict | None, int | None, str | None]:
    """
    解码并验证 token，返回 (成功, payload, 错误码, 错误信息)
    用于统一 verify_token 和 verify_token_ws 的逻辑
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        try:
            unverified_payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={'verify_exp': False})
            refresh_until = unverified_payload.get("refresh_until")
            now = datetime.now(timezone.utc).timestamp()

            if not refresh_until or now > refresh_until:
                return False, None, WS_TOKEN_REFRESH_EXPIRED, "Token 已超过 5 天刷新期限，请重新登录"
            else:
                return False, None, WS_TOKEN_EXPIRED, "Token 已过期，请刷新"

        except JWTError:
            return False, None, status.WS_1008_POLICY_VIOLATION, "Token 无效"
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            return False, None, status.WS_1008_POLICY_VIOLATION, f"Token 无效：{e}"

    if verify_expiry:
        now = datetime.now(timezone.utc).timestamp()
        refresh_until = payload.get("refresh_until")
        if not refresh_until or now > refresh_until:
            return False, None, WS_TOKEN_REFRESH_EXPIRED, "Token 已超过 5 天刷新期限，请重新登录"

    return True, payload, None, None


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    success, payload, error_code, error_msg = _decode_and_validate_token(token)

    if not success:
        if error_code == WS_TOKEN_EXPIRED:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)
        elif error_code == WS_TOKEN_REFRESH_EXPIRED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error_msg)
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)

    # 验证 token 类型必须为 access
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的 token 类型")

    return payload


def require_superadmin(payload: dict = Depends(verify_token)) -> dict:
    """验证用户是否为超级管理员"""
    if payload.get("permission_level") != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限"
        )
    return payload


def verify_token_ws(token: str) -> tuple[bool, dict | None, int | None, str | None]:
    """返回：(是否成功，payload, 关闭码，原因)"""
    return _decode_and_validate_token(token)


# =============================================================================
# Refresh Token (用于 HttpOnly Cookie)
# =============================================================================

def create_refresh_token(sub: str) -> str:
    """生成 Refresh Token（长期有效，7 天）"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=7)
    
    payload = {
        "sub": sub,
        "exp": expire,
        "iat": now,
        "type": "refresh"
    }
    
    refresh_key = f"{settings.SECRET_KEY}_refresh_v1"
    return jwt.encode(payload, refresh_key, algorithm=settings.ALGORITHM)


def verify_refresh_token(token: str) -> dict:
    """验证 Refresh Token"""
    refresh_key = f"{settings.SECRET_KEY}_refresh_v1"
    
    try:
        payload = jwt.decode(token, refresh_key, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Refresh Token 已过期，请重新登录"
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Refresh Token 无效"
        )
