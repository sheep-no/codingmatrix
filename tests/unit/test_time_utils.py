"""app/core/time.py 的单元测试。"""

from datetime import datetime, timedelta, timezone

from app.core.time import utcnow_naive


def test_utcnow_naive_returns_naive_datetime():
    now = utcnow_naive()
    assert now.tzinfo is None


def test_utcnow_naive_is_utc_wall_clock():
    """
    与 datetime.utcnow() 语义一致：都是 UTC 墙上时间，允许少量执行耗时。
    """
    naive = utcnow_naive()
    aware_utc = datetime.now(timezone.utc)
    delta = abs((aware_utc.replace(tzinfo=None) - naive).total_seconds())
    assert delta < 5


def test_utcnow_naive_compares_with_naive_datetimes():
    """
    结果可与 naive 时间直接做算术和比较，不触发 naive/aware TypeError。
    """
    now = utcnow_naive()
    assert (now - timedelta(days=1)) < now
    assert isinstance(now.isoformat(), str)
    assert "+" not in now.isoformat()
