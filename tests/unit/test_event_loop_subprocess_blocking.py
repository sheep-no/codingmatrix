"""async 端点内的阻塞 subprocess 调用必须离开事件循环。

`skills.reload_prompts`、`nginx_api.check_nginx`、`nginx_api.deploy_nginx`
是 async 处理函数，直接调用 `subprocess.run` 会在等待外部进程期间阻塞整个
事件循环，让所有并发请求停摆。
"""

import subprocess
import threading

import pytest
from fastapi import HTTPException

from app.api.v2 import nginx_api


class _Result:
    returncode = 0
    stdout = ""
    stderr = "syntax is ok"


def _spy_thread(seen):
    def _run(*args, **kwargs):
        seen.append(threading.get_ident())
        return _Result()

    return _run


@pytest.mark.asyncio
async def test_nginx_check_runs_subprocess_off_event_loop(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", _spy_thread(seen))

    body = nginx_api.NginxCheck(config="events { worker_connections 1024; }")
    result = await nginx_api.check_nginx(body=body, token={"sub": "1"})

    assert result == {"status": "ok", "message": "配置语法正确"}
    assert seen and all(t != threading.main_thread().ident for t in seen)


@pytest.mark.asyncio
async def test_nginx_deploy_runs_subprocess_off_event_loop(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", _spy_thread(seen))
    monkeypatch.setattr(nginx_api, "ALLOWED_NGINX_PATHS", (tmp_path,))

    request = nginx_api.NginxDeployRequest(
        config="server { listen 80; }", nginx_path=str(tmp_path), backup=False
    )
    result = await nginx_api.deploy_nginx(req=request, token={"sub": "1"})

    assert result.status == "success"
    assert seen and all(t != threading.main_thread().ident for t in seen)


@pytest.mark.asyncio
async def test_nginx_deploy_rejects_path_outside_allowed_dirs(tmp_path):
    request = nginx_api.NginxDeployRequest(
        config="server { listen 80; }", nginx_path=str(tmp_path), backup=False
    )
    with pytest.raises(HTTPException) as exc:
        await nginx_api.deploy_nginx(req=request, token={"sub": "1"})

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_nginx_deploy_hides_internal_error(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("internal path /etc/nginx/secret")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(nginx_api, "ALLOWED_NGINX_PATHS", (tmp_path,))

    request = nginx_api.NginxDeployRequest(
        config="server { listen 80; }", nginx_path=str(tmp_path), backup=False
    )
    with pytest.raises(HTTPException) as exc:
        await nginx_api.deploy_nginx(req=request, token={"sub": "1"})

    assert exc.value.status_code == 500
    assert "/etc/nginx/secret" not in str(exc.value.detail)
