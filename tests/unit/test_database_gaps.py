"""app.db.database 连接配置、非 SQLite 分支与 get_db 会话补测。"""

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import database as module


class _Cursor:
    def __init__(self):
        self.statements = []
        self.closed = False

    def execute(self, statement):
        self.statements.append(statement)

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


def test_sqlite_connection_sets_foreign_keys_wal_and_timeout():
    connection = _Connection()

    module._configure_sqlite_connection(connection, None)

    assert connection.cursor_obj.statements == [
        "PRAGMA foreign_keys=ON",
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=30000",
    ]
    assert connection.cursor_obj.closed is True


async def test_get_db_closes_session_on_success(monkeypatch):
    events = []

    class Session:
        async def __aenter__(self):
            events.append("enter")
            return self

        async def __aexit__(self, *exc):
            events.append("exit")
            return False

        async def close(self):
            events.append("close")

    monkeypatch.setattr(module, "async_session", lambda: Session())

    gen = module.get_db()
    session = await gen.__anext__()
    assert isinstance(session, Session)
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    # finally 在 async with 退出前执行，会话先 close 再 exit
    assert events == ["enter", "close", "exit"]


async def test_get_db_closes_session_on_error(monkeypatch):
    events = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            events.append("exit")
            return False

        async def close(self):
            events.append("close")

    monkeypatch.setattr(module, "async_session", lambda: Session())

    gen = module.get_db()
    await gen.__anext__()
    with pytest.raises(ValueError):
        await gen.athrow(ValueError("boom"))
    assert events == ["close", "exit"]


def test_non_sqlite_engine_uses_empty_connect_args(monkeypatch):
    source = Path(module.__file__).read_text(encoding="utf-8")
    captured = {}

    fake_settings = SimpleNamespace(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        DB_ECHO=False,
        DB_POOL_SIZE=5,
        DB_MAX_OVERFLOW=10,
        DB_POOL_TIMEOUT=30,
        DB_POOL_RECYCLE=1800,
    )
    fake_config = types.ModuleType("app.core.config")
    fake_config.settings = fake_settings
    monkeypatch.setitem(sys.modules, "app.core.config", fake_config)

    from sqlalchemy.ext import asyncio as sa_asyncio

    real_engine = sa_asyncio.create_async_engine

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return real_engine("sqlite+aiosqlite:///:memory:", poolclass=kwargs["poolclass"])

    monkeypatch.setattr(sa_asyncio, "create_async_engine", fake_create_async_engine)

    name = "app.db._database_nonsqlite_probe"
    spec = importlib.util.spec_from_loader(name, loader=None, origin=module.__file__)
    probe = importlib.util.module_from_spec(spec)
    probe.__file__ = module.__file__
    exec(compile(source, module.__file__, "exec"), probe.__dict__)

    assert captured["url"].startswith("postgresql")
    assert captured["kwargs"]["connect_args"] == {}
