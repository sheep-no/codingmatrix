"""管理端备份接口的 download_url、路由方法与真实语义一致性回归。

原实现几处问题：
1. /admin/backup/list 返回的 download_url 形如
   /api/v2/Controller/admin/backup/download/{filename}，但实际下载端点是
   /api/v2/Controller/admin/backup/{timestamp}，按该字段请求必然 404；
2. 创建备份时的保留期清理对每个候选文件直接 unlink，并发创建下另一请求
   已删掉同一文件会抛 FileNotFoundError，冒泡成「创建备份失败」500。
3. 创建备份挂在 GET /admin/backup 上：GET 有副作用，预取/重试/监控探测都会
   轮转备份，可能淘汰管理员刻意保留的历史备份；创建备份应为 POST。
"""

import os
import re
import time
from pathlib import Path

import pytest

from app.api.v2 import guardian_router


def _registered_paths() -> set[str]:
    from app.main import app

    return {route.path for route in app.routes if hasattr(route, "path")}


def _route_methods(path: str) -> set[str]:
    from app.main import app

    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", None) == path:
            methods |= set(getattr(route, "methods", None) or set())
    return methods


def _write_backups(directory: Path, timestamps) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for timestamp in timestamps:
        (directory / f"config_backup_{timestamp}.json").write_text("{}", encoding="utf-8")


class _FakeSession:
    """替代 async_session 上下文，让 create_backup 不依赖真实数据库。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        class _Result:
            def scalars(self):
                class _Scalars:
                    def all(self):
                        return []

                return _Scalars()

        return _Result()


@pytest.mark.asyncio
async def test_list_backups_download_url_points_at_download_route(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_backups(tmp_path / "data" / "backups", ["20260921_070000"])

    result = await guardian_router.list_backups(token={"sub": "1"})

    assert len(result["backups"]) == 1
    download_url = result["backups"][0]["download_url"]
    assert download_url == "/api/v2/Controller/admin/backup/20260921_070000"
    assert "/api/v2/Controller/admin/backup/{timestamp}" in _registered_paths()


@pytest.mark.asyncio
async def test_create_backup_download_url_points_at_download_route(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(guardian_router, "async_session", lambda: _FakeSession())

    result = await guardian_router.create_backup(token={"sub": "1"})

    download_url = result["download_url"]
    assert re.fullmatch(r"/api/v2/Controller/admin/backup/\d{8}_\d{6}", download_url)
    timestamp = download_url.rsplit("/", 1)[-1]
    assert (tmp_path / "data" / "backups" / f"config_backup_{timestamp}.json").exists()
    assert "/api/v2/Controller/admin/backup/{timestamp}" in _registered_paths()


@pytest.mark.asyncio
async def test_create_backup_retention_tolerates_concurrent_delete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backup_dir = tmp_path / "data" / "backups"
    _write_backups(
        backup_dir, [f"20260921_0700{i:02d}" for i in range(7)]
    )
    monkeypatch.setattr(guardian_router, "async_session", lambda: _FakeSession())

    real_unlink = os.unlink
    calls = {"count": 0}

    def flaky_unlink(path, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            # 模拟另一并发请求已先删掉同一文件
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", flaky_unlink)

    result = await guardian_router.create_backup(token={"sub": "1"})

    assert result["status"] == "success"
    assert calls["count"] >= 1


@pytest.mark.asyncio
async def test_retention_never_evicts_the_backup_it_just_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backup_dir = tmp_path / "data" / "backups"
    _write_backups(backup_dir, [f"20260921_0700{i:02d}" for i in range(7)])
    # 把历史备份的 mtime 推到未来，模拟「文件系统时间戳精度粗、新备份排不到最前」
    # 的情况：淘汰只应针对历史文件，绝不能把刚创建的这个删掉。
    future = time.time() + 3600
    for path in backup_dir.glob("config_backup_*.json"):
        os.utime(path, (future, future))
    monkeypatch.setattr(guardian_router, "async_session", lambda: _FakeSession())

    result = await guardian_router.create_backup(token={"sub": "1"})

    remaining = sorted(p.name for p in backup_dir.glob("config_backup_*.json"))
    assert len(remaining) == 5
    assert Path(result["backup_file"]).name in remaining


def test_create_backup_route_is_post_only():
    """创建备份有副作用，必须是 POST；GET /admin/backup 不得再存在。"""
    methods = _route_methods("/api/v2/Controller/admin/backup")

    assert "POST" in methods
    assert "GET" not in methods
