"""补齐 admin_config 的系统配置与沙箱配置端点。"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v2 import admin_config as module


SUPERADMIN = {"sub": "1", "permission_level": "superadmin"}


@pytest.fixture
def manager(monkeypatch):
    fake = SimpleNamespace(
        _config={"a": 1},
        update_user_override=lambda *a, **k: None,
        remove_user_override=lambda *a, **k: None,
        set_config_value=lambda *a, **k: None,
    )
    monkeypatch.setattr(module, "system_config_manager", fake)
    return fake


@pytest.mark.asyncio
async def test_update_user_limit_success(manager):
    update = module.UserLimitUpdate(user_id="7", limit=3)

    result = await module.update_user_concurrent_limit(update, token=SUPERADMIN, db=AsyncMock())

    assert result["success"] is True
    assert result["limit"] == 3
    assert result["tier"] == "custom"


@pytest.mark.asyncio
async def test_update_user_limit_failure(manager, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("bad")

    manager.update_user_override = boom

    with pytest.raises(HTTPException) as exc:
        await module.update_user_concurrent_limit(
            module.UserLimitUpdate(user_id="7", limit=3, tier="pro"),
            token=SUPERADMIN,
            db=AsyncMock(),
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_remove_user_limit_success(manager):
    result = await module.remove_user_concurrent_limit("7", token=SUPERADMIN, db=AsyncMock())

    assert result["success"] is True
    assert result["user_id"] == "7"


@pytest.mark.asyncio
async def test_remove_user_limit_failure(manager):
    def boom(*args, **kwargs):
        raise RuntimeError("bad")

    manager.remove_user_override = boom

    with pytest.raises(HTTPException) as exc:
        await module.remove_user_concurrent_limit("7", token=SUPERADMIN, db=AsyncMock())

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_update_system_config_success(manager):
    result = await module.update_system_config(
        module.ConfigUpdate(path="a", value=2), token=SUPERADMIN, db=AsyncMock()
    )

    assert result["success"] is True
    assert result["path"] == "a"
    assert result["value"] == 2


@pytest.mark.asyncio
async def test_update_system_config_failure(manager):
    def boom(*args, **kwargs):
        raise RuntimeError("bad")

    manager.set_config_value = boom

    with pytest.raises(HTTPException) as exc:
        await module.update_system_config(
            module.ConfigUpdate(path="a", value=2), token=SUPERADMIN, db=AsyncMock()
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_system_config(manager):
    assert await module.get_system_config(token=SUPERADMIN, db=AsyncMock()) == {"a": 1}


@pytest.mark.asyncio
async def test_get_sandbox_config(monkeypatch):
    from app.core import config

    settings = SimpleNamespace(ENABLE_CODE_SANDBOX=True, SANDBOX_LANGUAGES="python, node")
    monkeypatch.setattr(config, "settings", settings)

    result = await module.get_sandbox_config(token=SUPERADMIN)

    assert result == {
        "enable_code_sandbox": True,
        "sandbox_languages": ["python", "node"],
    }


@pytest.mark.asyncio
async def test_update_sandbox_config_all_fields(manager, monkeypatch):
    saved = []
    manager.set_config_value = lambda path, value: saved.append((path, value))

    result = await module.update_sandbox_config(
        module.SandboxConfigUpdate(
            enable_code_sandbox=False, sandbox_languages="python"
        ),
        token=SUPERADMIN,
    )

    assert result["success"] is True
    assert result["restart_required"] is True
    assert os.environ["ENABLE_CODE_SANDBOX"] == "false"
    assert os.environ["SANDBOX_LANGUAGES"] == "python"
    assert saved == [("enable_code_sandbox", False), ("sandbox_languages", "python")]
    monkeypatch.delenv("ENABLE_CODE_SANDBOX", raising=False)
    monkeypatch.delenv("SANDBOX_LANGUAGES", raising=False)


@pytest.mark.asyncio
async def test_update_sandbox_config_enable_only(manager, monkeypatch):
    result = await module.update_sandbox_config(
        module.SandboxConfigUpdate(enable_code_sandbox=True), token=SUPERADMIN
    )

    assert "enable_code_sandbox=True" in result["message"]
    monkeypatch.delenv("ENABLE_CODE_SANDBOX", raising=False)


@pytest.mark.asyncio
async def test_update_sandbox_config_languages_only(manager, monkeypatch):
    result = await module.update_sandbox_config(
        module.SandboxConfigUpdate(sandbox_languages="go"), token=SUPERADMIN
    )

    assert "sandbox_languages=go" in result["message"]
    monkeypatch.delenv("SANDBOX_LANGUAGES", raising=False)


@pytest.mark.asyncio
async def test_update_sandbox_config_empty(manager):
    with pytest.raises(HTTPException) as exc:
        await module.update_sandbox_config(module.SandboxConfigUpdate(), token=SUPERADMIN)

    assert exc.value.status_code == 400
