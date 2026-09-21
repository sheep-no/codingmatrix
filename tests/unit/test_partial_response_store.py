"""AIC6：跨 worker 部分响应缓存（Redis）与降级行为。

覆盖：写入/读取/消费往返、TTL<=0 不写入、Redis 异常时回退进程内存储。
"""

import pytest

from app.utils import partial_response_store


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)
        return 1


class _BrokenRedis:
    def setex(self, *args, **kwargs):
        raise RuntimeError("redis down")

    def get(self, *args, **kwargs):
        raise RuntimeError("redis down")

    def delete(self, *args, **kwargs):
        raise RuntimeError("redis down")


@pytest.fixture(autouse=True)
def _reset_store():
    partial_response_store._fallback.clear()
    yield
    partial_response_store.set_store_client(None)
    partial_response_store._fallback.clear()


def test_round_trip_get_and_pop():
    fake = _FakeRedis()
    partial_response_store.set_store_client(fake)

    assert partial_response_store.save_partial_response("r1", {"user_id": "u", "v": 1}, 300) is True
    assert fake.ttls["partial_response:r1"] == 300
    assert partial_response_store.get_partial_response("r1") == {"user_id": "u", "v": 1}
    # get 不消费
    assert partial_response_store.get_partial_response("r1") is not None
    # pop 消费
    assert partial_response_store.pop_partial_response("r1") == {"user_id": "u", "v": 1}
    assert partial_response_store.get_partial_response("r1") is None


def test_zero_ttl_is_not_stored():
    partial_response_store.set_store_client(_FakeRedis())
    assert partial_response_store.save_partial_response("r1", {"a": 1}, 0) is False
    assert partial_response_store.get_partial_response("r1") is None


def test_falls_back_to_process_memory_when_redis_broken():
    partial_response_store.set_store_client(_BrokenRedis())

    assert partial_response_store.save_partial_response("r1", {"user_id": "u"}, 300) is True
    assert partial_response_store.get_partial_response("r1") == {"user_id": "u"}
    assert partial_response_store.pop_partial_response("r1") == {"user_id": "u"}
    assert partial_response_store.get_partial_response("r1") is None
