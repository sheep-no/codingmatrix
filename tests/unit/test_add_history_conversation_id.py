"""save_history_to_db 新会话 id 生成的并发回归（db_layer.md DB6）。

conversation_id 是「一个会话对多轮记录」的一对多字段，无法用唯一约束
防重；新会话 id 由 max+1 生成，单进程 async 下两个并发新会话会读到同一
max 而拿到相同 id。这里用带交错窗口的假 DB 检验按用户锁的串行化效果。
"""

import asyncio
import importlib

add_history = importlib.import_module("app.db.add_history")
save_history_to_db = add_history.save_history_to_db


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDb:
    """只实现被测路径用到的接口，并在 max 查询处制造 await 交错点。"""

    def __init__(self):
        self._maxes: dict[int, int] = {}
        self.added = []

    async def execute(self, stmt):
        if "advisory" in str(stmt):
            # 模拟 SQLite：不支持 advisory lock，调用方必须容忍
            raise RuntimeError("no advisory lock on sqlite")
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
