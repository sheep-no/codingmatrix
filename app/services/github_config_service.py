"""Encrypted configuration storage using the application's existing RSA keypair."""
import re

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github_config import GithubUserConfig
from app.utils.crypto import decrypt_secret, encrypt_secret


def encrypt_token(token: str, user_id: int) -> str:
    return encrypt_secret(token, f"github:{user_id}")


def decrypt_token(record: GithubUserConfig) -> str:
    return decrypt_secret(record.encrypted_token, f"github:{record.user_id}")


def config_summary(record: GithubUserConfig | None) -> dict:
    credential_state = "missing"
    if record and record.encrypted_token:
        try:
            credential_state = "stored" if decrypt_token(record) else "missing"
        except Exception:
            credential_state = "unreadable"
    return {
        "username": record.username if record else "",
        "token": "",
        "use_github": bool(record and record.use_github),
        "persisted": record is not None,
        "has_token": credential_state == "stored",
        "credential_state": credential_state,
        "verified": False,
        "verification_status": "not_performed",
    }


async def load_readable_token(db: AsyncSession, user_id: int) -> tuple[GithubUserConfig, str]:
    record = await db.get(GithubUserConfig, user_id)
    if record is None or not record.encrypted_token:
        raise HTTPException(status_code=422, detail="尚未配置 GitHub 凭据")
    try:
        token = decrypt_token(record)
    except Exception:
        raise HTTPException(status_code=422, detail="凭据无法读取，请重新填写 Token") from None
    if not token:
        raise HTTPException(status_code=422, detail="尚未配置 GitHub 凭据")
    return record, token


async def resolve_save_credentials(
    db: AsyncSession,
    user_id: int,
    username: str = "",
    token: str = "",
    use_github: bool | None = None,
) -> tuple[str, str, bool]:
    username = (username or "").strip()
    token = (token or "").strip()
    record = await db.get(GithubUserConfig, user_id)
    if use_github is None:
        use_github = bool(record and record.use_github)
    if not use_github:
        return (username or (record.username if record else "")), token, False
    if token:
        if username and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
            raise HTTPException(status_code=422, detail="GitHub 用户名格式无效")
        if not username:
            raise HTTPException(status_code=422, detail="请填写 GitHub 用户名")
        if len(token) > 4096 or any(char.isspace() for char in token):
            raise HTTPException(status_code=422, detail="GitHub Token 格式无效")
        return username, token, True
    record, stored = await load_readable_token(db, user_id)
    username = username or record.username
    if not username:
        raise HTTPException(status_code=422, detail="请填写 GitHub 用户名")
    return username, stored, True


async def save_config(db: AsyncSession, user_id: int, username: str, token: str, enabled: bool) -> dict:
    username = username.strip()
    token = token.strip()
    if username and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise HTTPException(status_code=422, detail="GitHub 用户名格式无效")
    if len(token) > 4096 or any(char.isspace() for char in token):
        raise HTTPException(status_code=422, detail="GitHub Token 格式无效")
    record = await db.get(GithubUserConfig, user_id, with_for_update=True)
    if record is None:
        record = GithubUserConfig(user_id=user_id, username="", encrypted_token="", use_github=False)
        db.add(record)
    if record.encrypted_token and username.lower() != record.username.lower() and not token:
        raise HTTPException(status_code=422, detail="变更 GitHub 用户名时请提供新 Token")
    if token:
        if not username:
            raise HTTPException(status_code=422, detail="请填写 GitHub 用户名")
        record.encrypted_token = encrypt_token(token, user_id)
    record.username = username
    record.use_github = enabled
    summary = config_summary(record)
    if enabled and (not username or not summary["has_token"]):
        raise HTTPException(status_code=422, detail="启用前请配置可读取的 GitHub 凭据")
    await db.commit()
    return {"success": True, "message": "GitHub 配置已加密保存，远端尚未验证", **summary}
