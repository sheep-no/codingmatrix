"""回归测试：AiProjectCode.update_model_stats 必须更新平均执行耗时。

原实现只递增计数、更新 last_used_at，却从不重算 avg_execution_time，
导致既有统计行的平均耗时永远停留在首次记录值。
"""

import pytest

import app.api.v1.AiProjectCode as aipc
from app.models.agent_memory import ModelUsageStats


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, existing):
        self._existing = existing
        self.committed = False
        self.added = []

    async def execute(self, _stmt):
        return _FakeResult(self._existing)

    async def commit(self):
        self.committed = True

    def add(self, obj):
        self.added.append(obj)


class TestUpdateModelStats:
    @pytest.mark.asyncio
    async def test_existing_row_recomputes_running_average(self):
        stats = ModelUsageStats(
            user_id=1,
            model_key="k",
            model_name="n",
            request_count=2,
            total_tokens=10,
            success_count=1,
            failure_count=1,
            avg_execution_time=2.0,
        )
        db = _FakeDb(stats)

        await aipc.update_model_stats(
            db, user_id=1, model_key="k", model_name="n",
            tokens=5, success=True, execution_time=4.0,
        )

        # 新请求数 = 3，递增均值 = (2.0 * 2 + 4.0) / 3
        assert stats.avg_execution_time == pytest.approx(8.0 / 3.0)
        assert stats.request_count == 3
        assert stats.total_tokens == 15
        assert db.committed is True

    @pytest.mark.asyncio
    async def test_new_row_initializes_average_with_execution_time(self):
        db = _FakeDb(None)

        await aipc.update_model_stats(
            db, user_id=1, model_key="k", model_name="n",
            tokens=5, success=True, execution_time=3.5,
        )

        assert len(db.added) == 1
        created = db.added[0]
        assert created.avg_execution_time == pytest.approx(3.5)
        assert db.committed is True
