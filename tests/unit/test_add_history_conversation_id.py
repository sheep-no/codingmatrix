"""save_history_to_db 新会话 id 生成的并发回归（db_layer.md DB6）。

conversation_id 是「一个会话对多轮记录」的一对多字段，无法用唯一约束
防重；新会话 id 由 max+1 生成，单进程 async 下两个并发新会话会读到同一
max 而拿到相同 id。这里用带交错窗口的假 DB 检验按用户锁的串行化效果。
"""

import asyncio
import importlib
from types import SimpleNamespace

import pytest

add_history = importlib.import_module("app.db.add_history")
save_history_to_db = add_history.save_history_to_db


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeLockConnection:
    def __init__(self, db):
        self.db = db

    async def execute(self, stmt, params=None):
        self.db.statements.append((str(stmt), params))
        if "GET_LOCK" in str(stmt):
            return _FakeResult(self.db.lock_result)
        return _FakeResult(1)

    async def close(self):
        self.db.lock_connection_closed = True


class _FakeBind:
    def __init__(self, db):
        self.db = db

    async def connect(self):
        return _FakeLockConnection(self.db)


class _FakeDb:
    """只实现被测路径用到的接口，并在 max 查询处制造 await 交错点。"""

    def __init__(self, dialect: str = "sqlite", lock_result: int = 1):
        self.dialect = dialect
        self.lock_result = lock_result
        self._maxes: dict[int, int] = {}
        self.added = []
        self.statements = []
        self.lock_connection_closed = False
        self.bind = _FakeBind(self)

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    async def execute(self, stmt, params=None):
        statement = str(stmt)
        self.statements.append((statement, params))
        # 在查询开始瞬间取快照，还原「两个并发 SELECT 都读到旧 max」
        snapshot = self._maxes.get(self._user_id_of(stmt), 0)
        await asyncio.sleep(0.02)
        return _FakeResult(snapshot)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self._sync()

    async def flush(self):
        self._sync()

    async def refresh(self, obj):
        return None

    @staticmethod
    def _user_id_of(stmt) -> int:
        # 从 where user_id == ? 的绑定参数还原用户，模拟按用户分桶
        for key, value in stmt.compile().params.items():
            if "user_id" in key:
                return value
        return 0

    def _sync(self):
        for obj in self.added:
            current = self._maxes.get(obj.user_id, 0)
            self._maxes[obj.user_id] = max(current, obj.conversation_id)


async def test_concurrent_new_conversations_get_distinct_ids():
    db = _FakeDb()

    ids = await asyncio.gather(
        save_history_to_db(db, 1, None, "first", "r1", commit=False),
        save_history_to_db(db, 1, None, "second", "r2", commit=False),
    )

    assert sorted(ids) == [1, 2]


async def test_different_users_do_not_share_sequence():
    db = _FakeDb()

    ids = await asyncio.gather(
        save_history_to_db(db, 1, None, "a", "r", commit=False),
        save_history_to_db(db, 2, None, "b", "r", commit=False),
    )

    assert ids == [1, 1]


async def test_continuing_conversation_keeps_given_id():
    db = _FakeDb()

    conv_id = await save_history_to_db(db, 1, 7, "hi", "r", commit=False)

    assert conv_id == 7


async def test_mysql_new_conversation_uses_named_lock():
    db = _FakeDb(dialect="mysql")

    conv_id = await save_history_to_db(db, 3, None, "hi", "r", commit=False)

    assert conv_id == 1
    assert any("GET_LOCK" in statement for statement, _ in db.statements)
    assert any("RELEASE_LOCK" in statement for statement, _ in db.statements)
    assert db.lock_connection_closed is True


async def test_mysql_lock_timeout_raises_and_unlocks_process_lock():
    db = _FakeDb(dialect="mysql", lock_result=0)

    with pytest.raises(RuntimeError, match="会话 ID 生成锁超时"):
        await save_history_to_db(db, 4, None, "hi", "r", commit=False)

    assert not add_history._conversation_id_locks[4].locked()
    assert db.lock_connection_closed is True
