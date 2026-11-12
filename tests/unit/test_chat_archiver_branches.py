"""Branch coverage for app/db/chat_archiver.py without a real database."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.db import chat_archiver as module
from app.db.chat_archiver import ChatArchiver
from app.models.chat_history import ChatHistory


class _Result:
    def __init__(self, *, rows=None, scalar=None, rowcount=0):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDb:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.flushed = False
        self.rolled_back = False
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)
        item = self.results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def add(self, obj):
        self.added.append(obj)
        obj.id = 1

    async def flush(self):
        self.flushed = True

    async def rollback(self):
        self.rolled_back = True

    async def commit(self):
        return None


class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _message(msg_id=1, role="user", content="hello", created_at=None):
    return SimpleNamespace(
        id=msg_id,
        role=role,
        content=content,
        created_at=created_at or datetime(2026, 1, 1),
    )


def _summary(end_date):
    return SimpleNamespace(end_date=end_date)


def _stub_checkpoints(monkeypatch):
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(module, "save_summary_checkpoint", noop)
    monkeypatch.setattr(module, "delete_messages_for_legacy_ids", noop)


# ---------------------------------------------------------------------------
# _archive_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_user_skips_when_watermark_not_older(monkeypatch) -> None:
    db = _FakeDb([_Result(scalar=_summary(datetime.utcnow()))])
    archiver = ChatArchiver(db)

    await archiver._archive_user(1, days_ago_start=3, days_ago_end=13)

    assert len(db.executed) == 1
    assert db.added == []


@pytest.mark.asyncio
async def test_archive_user_skips_on_overlap(monkeypatch) -> None:
    db = _FakeDb(
        [
            _Result(scalar=None),
            _Result(scalar=SimpleNamespace(id=1)),
        ]
    )
    archiver = ChatArchiver(db)

    await archiver._archive_user(1, days_ago_start=3, days_ago_end=13)

    assert len(db.executed) == 2
    assert db.added == []


@pytest.mark.asyncio
async def test_archive_user_skips_without_old_messages(monkeypatch) -> None:
    db = _FakeDb([_Result(scalar=None), _Result(scalar=None), _Result(rows=[])])
    archiver = ChatArchiver(db)

    await archiver._archive_user(1, days_ago_start=3, days_ago_end=13)

    assert db.added == []


@pytest.mark.asyncio
async def test_archive_user_creates_summary_and_deletes_messages(monkeypatch) -> None:
    _stub_checkpoints(monkeypatch)
    earlier = datetime(2026, 1, 1)
    later = datetime(2026, 1, 2)
    messages = [_message(1, created_at=earlier), _message(2, "assistant", "ok", later)]
    db = _FakeDb(
        [
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(rows=messages),
            _Result(rowcount=2),
        ]
    )

    async def summary(self, msgs):
        return "摘要"

    monkeypatch.setattr(ChatArchiver, "_generate_summary_with_ai", summary)
    archiver = ChatArchiver(db)

    await archiver._archive_user(1, days_ago_start=3, days_ago_end=13)

    assert db.flushed is True
    assert len(db.added) == 1
    assert db.added[0].start_date == earlier
    assert db.added[0].end_date == later


@pytest.mark.asyncio
async def test_archive_user_rolls_back_and_raises(monkeypatch) -> None:
    db = _FakeDb([RuntimeError("db down")])
    archiver = ChatArchiver(db)

    with pytest.raises(RuntimeError):
        await archiver._archive_user(1, days_ago_start=3, days_ago_end=13)

    assert db.rolled_back is True


# ---------------------------------------------------------------------------
# archive_all_users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_all_users_processes_batches(monkeypatch) -> None:
    db = _FakeDb([_Result(rows=[1, 2]), _Result(rows=[])])
    sessions = []

    class Session(_FakeDb):
        def __init__(self):
            super().__init__([])
            sessions.append(self)

    monkeypatch.setattr(module, "async_session", lambda: _SessionCtx(Session()))

    async def archive(self, user_id, start, end):
        return None

    monkeypatch.setattr(ChatArchiver, "_archive_user", archive)

    await ChatArchiver(db).archive_all_users(batch_size=2)

    assert len(sessions) == 2
    assert all(session is not None for session in sessions)


@pytest.mark.asyncio
async def test_archive_all_users_records_failed_users(monkeypatch) -> None:
    db = _FakeDb([_Result(rows=[1, 2]), _Result(rows=[])])
    sessions = []

    class Session(_FakeDb):
        def __init__(self):
            super().__init__([])
            sessions.append(self)

    monkeypatch.setattr(module, "async_session", lambda: _SessionCtx(Session()))

    async def archive(self, user_id, start, end):
        raise ValueError("bad user")

    monkeypatch.setattr(ChatArchiver, "_archive_user", archive)
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    await ChatArchiver(db).archive_all_users(batch_size=2)

    assert all(session.rolled_back for session in sessions)
    assert warnings


@pytest.mark.asyncio
async def test_archive_all_users_reraises_outer_error(monkeypatch) -> None:
    db = _FakeDb([RuntimeError("query failed")])

    with pytest.raises(RuntimeError):
        await ChatArchiver(db).archive_all_users()


@pytest.mark.asyncio
async def test_archive_all_users_truncates_failed_list(monkeypatch) -> None:
    db = _FakeDb([_Result(rows=list(range(1, 13))), _Result(rows=[])])

    class Session(_FakeDb):
        def __init__(self):
            super().__init__([])

    monkeypatch.setattr(module, "async_session", lambda: _SessionCtx(Session()))

    async def archive(self, user_id, start, end):
        raise OSError("io")

    monkeypatch.setattr(ChatArchiver, "_archive_user", archive)
    warnings = []
    monkeypatch.setattr(
        module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    await ChatArchiver(db).archive_all_users(batch_size=12)

    assert warnings
    assert warnings[0][0].endswith("...")


# ---------------------------------------------------------------------------
# _generate_summary_with_ai
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_summary_success(monkeypatch) -> None:
    async def fake_call_llm(**kwargs):
        return {"choices": [{"message": {"content": "  summary  "}}]}

    monkeypatch.setattr(module, "call_llm", fake_call_llm)

    result = await ChatArchiver(_FakeDb([]))._generate_summary_with_ai([_message()])

    assert result == "summary"


@pytest.mark.asyncio
async def test_generate_summary_truncates_long_content(monkeypatch) -> None:
    async def fake_call_llm(**kwargs):
        return {"choices": [{"message": {"content": "x" * 900}}]}

    monkeypatch.setattr(module, "call_llm", fake_call_llm)

    result = await ChatArchiver(_FakeDb([]))._generate_summary_with_ai([_message()])

    assert len(result) == 800
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_generate_summary_retries_and_falls_back(monkeypatch) -> None:
    attempts = []

    async def fake_call_llm(**kwargs):
        attempts.append(1)
        return {"choices": []}

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(module, "call_llm", fake_call_llm)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    result = await ChatArchiver(_FakeDb([]))._generate_summary_with_ai(
        [_message(content="question")]
    )

    assert len(attempts) == 3
    assert result.startswith("历史对话主题：")


@pytest.mark.asyncio
async def test_generate_summary_empty_content_returns_empty(monkeypatch) -> None:
    async def fake_call_llm(**kwargs):
        return {"choices": [{"message": {}}]}

    monkeypatch.setattr(module, "call_llm", fake_call_llm)

    result = await ChatArchiver(_FakeDb([]))._generate_summary_with_ai([_message()])

    assert result == ""


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------


def test_build_conversation_text_roles_and_truncation() -> None:
    messages = [
        _message(1, "user", "a" * 900),
        _message(2, "assistant", "reply"),
    ]

    text = ChatArchiver(_FakeDb([]))._build_conversation_text(messages)

    assert "[用户]" in text
    assert "[助手]" in text
    assert "a" * 800 in text
    assert "a" * 801 not in text


def test_build_conversation_text_omits_remaining_messages() -> None:
    messages = [_message(index, "user", "x" * 800) for index in range(20)]

    text = ChatArchiver(_FakeDb([]))._build_conversation_text(messages)

    assert "（省略" in text
    assert text.count("[用户]") < len(messages)


def test_build_summary_prompt_embeds_conversation() -> None:
    prompt = ChatArchiver(_FakeDb([]))._build_summary_prompt("CONV")

    assert "对话内容：\nCONV" in prompt
    assert prompt.endswith("请生成摘要：")


def test_fallback_summary_more_than_three_queries() -> None:
    messages = [_message(index, "user", f"q{index}") for index in range(4)]

    result = ChatArchiver(_FakeDb([]))._fallback_summary(messages)

    assert result.startswith("历史对话主题：q0；q1；q2")
    assert result.endswith("...")


def test_fallback_summary_few_queries() -> None:
    messages = [_message(1, "user", "q1"), _message(2, "assistant", "a")]

    result = ChatArchiver(_FakeDb([]))._fallback_summary(messages)

    assert result == "历史对话主题：q1"


def test_fallback_summary_no_user_queries() -> None:
    messages = [_message(1, "assistant", "a")]

    assert ChatArchiver(_FakeDb([]))._fallback_summary(messages) == "历史对话：无主要内容"
