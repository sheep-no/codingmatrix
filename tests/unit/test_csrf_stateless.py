"""CSRF Token 无状态化回归（docs/evolution/modules/api_security.md CS1）。"""
import base64
import json
import time

from app.utils.csrf import CSRFTokenManager, csrf_manager


async def test_token_validates_across_manager_instances():
    """多 worker 场景：A 实例签发的 token 必须能被 B 实例校验通过。"""
    issuer = CSRFTokenManager()
    verifier = CSRFTokenManager()
    token = await issuer.create_token("42")
    assert await verifier.validate_token(token, "42") is True


async def test_token_survives_process_restart():
    """进程重启（新实例、无内存状态）后，已签发的 token 仍然有效。"""
    token = await CSRFTokenManager().create_token()
    fresh = CSRFTokenManager()
    assert await fresh.validate_token(token) is True


async def test_tampered_token_rejected():
    token = await csrf_manager.create_token()
    encoded, signature = token.split(".", 1)
    assert await csrf_manager.validate_token(f"{encoded}.{'0' * len(signature)}") is False


async def test_expired_token_rejected():
    manager = CSRFTokenManager()
    payload = json.dumps({"exp": int(time.time()) - 1, "uid": ""}, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    expired = f"{encoded}.{manager._signature(payload)}"
    assert await manager.validate_token(expired) is False


async def test_user_binding_mismatch_rejected():
    token = await csrf_manager.create_token("7")
    assert await csrf_manager.validate_token(token, "8") is False


async def test_tokens_are_unique_within_same_second():
    """nonce 保证同一秒内重复签发也不产生相同 token。"""
    manager = CSRFTokenManager()
    tokens = {await manager.create_token() for _ in range(5)}
    assert len(tokens) == 5


async def test_malformed_token_rejected():
    for bad in ("", "no-dot", "!!!.???", "YWJj.bad-signature"):
        assert await csrf_manager.validate_token(bad) is False
