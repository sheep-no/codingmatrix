"""500 响应不得回显内部异常细节。

多个端点捕获异常后直接构造 `HTTPException(status_code=500, detail=str(e))`，
绕过了 `generic_exception_handler` 的通用文案，把底层异常（表名、约束名、
subprocess stderr、路径）原样返回给客户端。
"""

import pytest
from fastapi import HTTPException

from app.api.v2 import admin_config, nginx_api


INTERNAL = "sqlite3.OperationalError: no such column: secret_internal"


def _raise_internal(*args, **kwargs):
    raise RuntimeError(INTERNAL)


@pytest.mark.asyncio
async def test_admin_config_update_limit_hides_internal_error(monkeypatch):
    monkeypatch.setattr(
        admin_config.system_config_manager, "update_user_override", _raise_internal
    )
    update = admin_config.UserLimitUpdate(user_id="7", limit=3)
    with pytest.raises(HTTPException) as exc:
        await admin_config.update_user_concurrent_limit(update=update, token={}, db=None)
    assert exc.value.status_code == 500
    assert "secret_internal" not in str(exc.value.detail)
    assert "OperationalError" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_admin_config_remove_limit_hides_internal_error(monkeypatch):
    monkeypatch.setattr(
        admin_config.system_config_manager, "remove_user_override", _raise_internal
    )
    with pytest.raises(HTTPException) as exc:
        await admin_config.remove_user_concurrent_limit(user_id="7", token={}, db=None)
    assert exc.value.status_code == 500
    assert "secret_internal" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_admin_config_system_config_hides_internal_error(monkeypatch):
    monkeypatch.setattr(
        admin_config.system_config_manager, "set_config_value", _raise_internal
    )
    update = admin_config.ConfigUpdate(path="a.b", value=1)
    with pytest.raises(HTTPException) as exc:
        await admin_config.update_system_config(update=update, token={}, db=None)
    assert exc.value.status_code == 500
    assert "secret_internal" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_nginx_check_hides_internal_error(monkeypatch):
    """非超时/非未安装的异常只返回通用文案。"""

    def _boom(*args, **kwargs):
        raise RuntimeError("internal path /etc/nginx/secret")

    monkeypatch.setattr(nginx_api.subprocess, "run", _boom)
    body = nginx_api.NginxCheck(config="events { worker_connections 1024; }")
    with pytest.raises(HTTPException) as exc:
        await nginx_api.check_nginx(body=body, token={"sub": "1"})
    assert exc.value.status_code == 500
    assert "/etc/nginx/secret" not in str(exc.value.detail)
