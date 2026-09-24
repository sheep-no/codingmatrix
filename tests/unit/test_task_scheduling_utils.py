"""task_manager 回归测试。

覆盖 docs/evolution/modules/task_scheduling.md 中核实的缺陷：
- TM1：TaskManager 单例构造无锁
- TM2：_get_redis 懒加载无锁
- TM5：cleanup_old_tasks 用 KEYS 全库扫描
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.utils.task_manager import TASK_PREFIX, task_manager


class _FakeRedis:
    """只实现所需接口；keys() 被显式禁止以证明不再使用全库扫描"""

    def __init__(self, store):
        self.store = store

    async def scan_iter(self, match=None):
        prefix = match.rstrip("*") if match else ""
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)

    async def srem(self, key, member):
        return 0

    async def keys(self, pattern):
        raise AssertionError("cleanup_old_tasks 不应使用 KEYS 全库扫描")


class TestTaskManagerCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_uses_scan_and_removes_old_tasks(self, monkeypatch):
        store = {
            f"{TASK_PREFIX}old": json.dumps(
                {"completed_at": "2000-01-01T00:00:00", "user_id": "u1"}
            ),
            f"{TASK_PREFIX}new": json.dumps(
                {"completed_at": "2999-01-01T00:00:00", "user_id": "u1"}
            ),
        }
        fake = _FakeRedis(store)

        async def _get_redis():
            return fake

        monkeypatch.setattr(task_manager, "_get_redis", _get_redis)
        await task_manager.cleanup_old_tasks(days=7)

        assert f"{TASK_PREFIX}old" not in store
        assert f"{TASK_PREFIX}new" in store

    @pytest.mark.asyncio
    async def test_get_redis_reuses_single_connection(self, monkeypatch):
        created = []

        class _Conn:
            pass

        def _from_url(*args, **kwargs):
            created.append(1)
            return _Conn()

        monkeypatch.setattr(task_manager, "_redis", None)
        monkeypatch.setattr("app.utils.task_manager.redis.from_url", _from_url)

        first = await task_manager._get_redis()
        second = await task_manager._get_redis()

        assert first is second
        assert len(created) == 1

    def test_singleton_identity(self):
        from app.utils.task_manager import TaskManager

        assert TaskManager() is TaskManager()


class TestRedisUrlConfigurable:
    """TM9：REDIS_URL 应可由环境变量配置。"""

    def test_redis_url_reads_env(self):
        env = dict(os.environ)
        env["REDIS_URL"] = "redis://custom-host:6380/3"
        result = subprocess.run(
            [sys.executable, "-c", "import app.utils.task_manager as t; print(t.REDIS_URL)"],
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "redis://custom-host:6380/3"
