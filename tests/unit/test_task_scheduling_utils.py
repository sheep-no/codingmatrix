"""task_manager / resume_manager 回归测试。

覆盖 docs/evolution/modules/task_scheduling.md 中核实的缺陷：
- TM1：TaskManager 单例构造无锁
- TM2：_get_redis 懒加载无锁
- TM5：cleanup_old_tasks 用 KEYS 全库扫描
- RM1：save_chunk_state 读-改-写非原子、重复分片重复追加
- RM2：upload_id 直接拼接路径可穿越
"""
import asyncio
import json

import pytest

from app.utils.resume_manager import ResumeManager
from app.utils.task_manager import TASK_PREFIX, task_manager


class TestResumeManager:

    def test_invalid_upload_id_rejected(self, tmp_path):
        manager = ResumeManager(resume_dir=tmp_path / "resume")
        for bad_id in ("../escape", "/etc/passwd", "a/b", "", "x" * 65):
            with pytest.raises(ValueError):
                manager._state_file(bad_id)

    @pytest.mark.asyncio
    async def test_valid_upload_id_accepted(self, tmp_path):
        manager = ResumeManager(resume_dir=tmp_path / "resume")
        await manager.save_chunk_state("upload-1_abc", 0, "hash0")
        state = await manager.get_resume_state("upload-1_abc", total_chunks=3)
        assert state.completed_chunks == [0]

    @pytest.mark.asyncio
    async def test_duplicate_chunk_index_not_appended_twice(self, tmp_path):
        manager = ResumeManager(resume_dir=tmp_path / "resume")
        await manager.save_chunk_state("up1", 2, "h2")
        await manager.save_chunk_state("up1", 2, "h2-updated")

        state = await manager.get_resume_state("up1", total_chunks=5)
        assert state.completed_chunks == [2]
        assert state.chunk_hashes["2"] == "h2-updated"

    @pytest.mark.asyncio
    async def test_state_write_is_atomic(self, tmp_path):
        resume_dir = tmp_path / "resume"
        manager = ResumeManager(resume_dir=resume_dir)
        await manager.save_chunk_state("up2", 0, "h0")
        await manager.save_chunk_state("up2", 1, "h1")

        state_file = resume_dir / "up2.json"
        assert json.loads(state_file.read_text())["completed_chunks"] == [0, 1]
        assert list(resume_dir.glob("*.tmp")) == []

    @pytest.mark.asyncio
    async def test_concurrent_saves_keep_every_chunk(self, tmp_path):
        manager = ResumeManager(resume_dir=tmp_path / "resume")
        await asyncio.gather(
            *(manager.save_chunk_state("up3", i, f"h{i}") for i in range(20))
        )

        state = await manager.get_resume_state("up3", total_chunks=20)
        assert sorted(state.completed_chunks) == list(range(20))


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
