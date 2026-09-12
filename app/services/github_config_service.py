"""Encrypted configuration storage using the application's existing RSA keypair."""
import base64
import json
import os
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github_config import GithubUserConfig
from app.utils.crypto import get_rsa_key_manager


def encrypt_token(token: str, user_id: int) -> str:
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    wrapped = get_rsa_key_manager().public_key.encrypt(
        key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    ciphertext = AESGCM(key).encrypt(nonce, token.encode(), f"github:{user_id}".encode())
    return json.dumps([base64.b64encode(value).decode() for value in (wrapped, nonce, ciphertext)])


def decrypt_token(record: GithubUserConfig) -> str:
    wrapped, nonce, ciphertext = [base64.b64decode(value) for value in json.loads(record.encrypted_token)]
    key = get_rsa_key_manager().private_key.decrypt(
        wrapped, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return AESGCM(key).decrypt(nonce, ciphertext, f"github:{record.user_id}".encode()).decode()


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
