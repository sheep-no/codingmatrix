"""500 响应不得回显内部异常细节（guardian / nginx / vision / 上传）。

这些端点捕获异常后曾直接 `detail=f"...{str(e)}"`，把底层路径、命令输出、
SQL 错误原样回显。修复后统一返回通用文案，完整异常只进日志。
"""

import types

import pytest
from fastapi import HTTPException

from app.api.v1 import file_upload, vision_api
from app.api.v2 import guardian_router, nginx_api


INTERNAL = "internal path /etc/secret/db.sqlite3"


def _boom(*args, **kwargs):
    raise RuntimeError(INTERNAL)


async def _boom_async(*args, **kwargs):
    raise RuntimeError(INTERNAL)


def _assert_hidden(exc_info):
    assert exc_info.value.status_code == 500
    detail = str(exc_info.value.detail)
    assert INTERNAL not in detail
    assert "RuntimeError" not in detail


@pytest.mark.asyncio
async def test_guardian_docker_containers_hides_internal(monkeypatch):
    fake_docker = types.SimpleNamespace(from_env=_boom, errors=types.SimpleNamespace())
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)

    with pytest.raises(HTTPException) as exc:
        await guardian_router.list_docker_containers(token={"sub": "1"})
    _assert_hidden(exc)


@pytest.mark.asyncio
async def test_guardian_create_backup_hides_internal(monkeypatch):
    monkeypatch.setattr(guardian_router, "async_session", _boom)

    with pytest.raises(HTTPException) as exc:
        await guardian_router.create_backup(token={"sub": "1"})
    _assert_hidden(exc)


@pytest.mark.asyncio
async def test_guardian_list_backups_hides_internal(monkeypatch, tmp_path):
    class _BadDatetime:
        @staticmethod
        def fromtimestamp(value):
            _boom()

    monkeypatch.setattr(guardian_router, "datetime", _BadDatetime)
    monkeypatch.chdir(tmp_path)
    backup_dir = tmp_path / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "config_backup_20200101_000000.json").write_text("{}", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        await guardian_router.list_backups(token={"sub": "1"})
    _assert_hidden(exc)


@pytest.mark.asyncio
async def test_nginx_read_config_hides_internal(monkeypatch, tmp_path):
    target = tmp_path / "app.conf"
    target.write_text("server {}", encoding="utf-8")
    monkeypatch.setattr(nginx_api, "ALLOWED_NGINX_PATHS", (tmp_path,))

    import builtins

    real_open = builtins.open

    def _bad_open(path, *args, **kwargs):
        if str(path) == str(target.resolve()):
            _boom()
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _bad_open)

    with pytest.raises(HTTPException) as exc:
        await nginx_api.get_nginx_config(config_path=str(target), token={"sub": "1"})
    _assert_hidden(exc)


@pytest.mark.asyncio
async def test_vision_analyze_hides_internal(monkeypatch):
    monkeypatch.setattr(vision_api, "analyze_image", _boom_async)

    with pytest.raises(HTTPException) as exc:
        await vision_api.api_analyze_image(
            file=None,
            prompt="describe",
            image_url="data:image/png;base64,iVBORw0KGgo=",
            model=None,
            token={"sub": "1"},
        )
    _assert_hidden(exc)


@pytest.mark.asyncio
async def test_file_upload_hides_internal(monkeypatch):
    monkeypatch.setattr(file_upload, "validate_file_upload", _boom)

    fake_file = types.SimpleNamespace(
        filename="a.txt",
        content_type="text/plain",
        read=_boom_async,
    )
    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_file(
            file=fake_file,
            conversation_id=None,
            token={"sub": "1"},
            db=None,
        )
    _assert_hidden(exc)


def test_ppt_500_details_are_generic():
    """PPT 各 500 分支不得回显异常文本（静态守住 5 处修复）。"""
    import inspect
    import re

    from app.api.v1 import aiGeneratorPptx

    source = inspect.getsource(aiGeneratorPptx)
    offenders = re.findall(r'status_code=500, detail=f"[^"]*\{', source)
    assert offenders == []
