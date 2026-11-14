"""chat_history_service 日期过滤、计数为 None 与删除分支补测。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.db.chat_history_service import ChatHistoryService


def _db(scalar=None, scalars=None):
    db = MagicMock()
    db.execute = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = scalar
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = scalars or []
    db.execute.return_value = result
    db.flush = AsyncMock()
    return db


async def test_get_user_history_applies_date_filters():
    db = _db(scalar=2)
    service = ChatHistoryService(db)
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 2)

    records, total = await service.get_user_history(
        "u", start_date=start, end_date=end
    )

    assert records == []
    assert total == 2
    assert db.execute.await_count == 2


async def test_get_user_history_none_total_becomes_zero():
    db = _db(scalar=None)
    service = ChatHistoryService(db)

    records, total = await service.get_user_history("u")

    assert records == []
    assert total == 0


async def test_delete_record_returns_true_when_rows_deleted():
    db = _db()
    db.execute.return_value.rowcount = 1
    service = ChatHistoryService(db)

    assert await service.delete_record(1, "u") is True
    db.flush.assert_awaited_once()


async def test_delete_record_returns_false_when_missing():
    db = _db()
    db.execute.return_value.rowcount = 0
    service = ChatHistoryService(db)

    assert await service.delete_record(1, "u") is False


async def test_delete_records_returns_rowcount():
    db = _db()
    db.execute.return_value.rowcount = 3
    service = ChatHistoryService(db)

    assert await service.delete_records(["1", "2"], "u") == 3
    db.flush.assert_awaited_once()


async def test_clear_user_history_returns_rowcount():
    db = _db()
    db.execute.return_value.rowcount = 5
    service = ChatHistoryService(db)

    assert await service.clear_user_history("u") == 5
    db.flush.assert_awaited_once()


async def test_get_lightweight_context_returns_messages_in_order():
    summary = SimpleNamespace(summary_text="summary")
    messages = [
        SimpleNamespace(role="assistant", content="a"),
        SimpleNamespace(role="user", content="u"),
    ]
    db = MagicMock()
    db.execute = AsyncMock()
    first = MagicMock()
    first.scalar_one_or_none.return_value = summary
    second = MagicMock()
    second.scalars.return_value.all.return_value = messages
    db.execute.side_effect = [first, second]
    service = ChatHistoryService(db)

    result, summary_text = await service.get_lightweight_context("u")

    assert result == [
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]
    assert summary_text == "summary"
