"""skills /reload 端点必须要求管理员权限（SKY2）。

原为完全匿名可达，任何访问者都能触发提权脚本改写全局提示词文档。
"""

import subprocess

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
