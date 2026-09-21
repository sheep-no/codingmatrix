"""ConversationMessage.to_dict 的 timestamp 语义回归（db_layer.md DB11）。

SQLite 读回 DateTime(timezone=True) 会丢 tzinfo，值本身是 UTC。
直接 .timestamp() 会按本地时区解释，非 UTC 服务器上偏移 TZ 秒。
"""

import importlib
import os
import time
from datetime import datetime, timezone

import pytest

models = importlib.import_module("app.db.models")
ConversationMessage = models.ConversationMessage


@pytest.fixture()
def cst_timezone():
    """切到 UTC+8，让 naive UTC 值被本地化解释时产生可见偏差。"""
    original = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Shanghai"
    time.tzset()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def _message(created_at):
    msg = ConversationMessage(
        session_id="s-1", user_id="u-1", role="user", content="hi"
    )
    msg.created_at = created_at
    return msg


def test_naive_utc_value_maps_to_utc_epoch(cst_timezone):
    naive_utc = datetime(2026, 1, 1, 12, 0, 0)
    expected = int(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())

    assert _message(naive_utc).to_dict()["timestamp"] == expected


def test_aware_value_is_preserved(cst_timezone):
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    assert _message(aware).to_dict()["timestamp"] == int(aware.timestamp())


def test_missing_created_at_returns_zero():
    assert _message(None).to_dict()["timestamp"] == 0
