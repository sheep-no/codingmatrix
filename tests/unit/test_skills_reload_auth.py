"""skills /reload 端点必须要求管理员权限（SKY2）。

原为完全匿名可达，任何访问者都能触发提权脚本改写全局提示词文档。
"""

import subprocess
import threading

import pytest
from fastapi import HTTPException

from app.api.v1.skills import reload_prompts


@pytest.mark.asyncio
async def test_reload_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await reload_prompts(token={"sub": "1", "permission_level": "normal"})

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reload_allows_admin(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Result())

    result = await reload_prompts(token={"sub": "1", "permission_level": "admin"})

    assert result["message"] == "提示词文档已更新"


@pytest.mark.asyncio
async def test_reload_runs_extract_off_event_loop(monkeypatch):
    """阻塞的 subprocess.run 必须在线程中执行，避免卡住整个事件循环。"""
    seen = {}

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _run(*args, **kwargs):
        seen["thread"] = threading.get_ident()
        return _Result()

    monkeypatch.setattr(subprocess, "run", _run)

    await reload_prompts(token={"sub": "1", "permission_level": "admin"})

    assert seen["thread"] != threading.main_thread().ident


@pytest.mark.asyncio
async def test_reload_hides_extract_stderr(monkeypatch):
    """提取失败时不得把 stderr 原样回显给客户端。"""

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "Traceback: /etc/skills/secret-token"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Result())

    with pytest.raises(HTTPException) as exc:
        await reload_prompts(token={"sub": "1", "permission_level": "admin"})

    assert exc.value.status_code == 500
    assert "secret-token" not in str(exc.value.detail)
    assert "Traceback" not in str(exc.value.detail)
