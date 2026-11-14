"""image_quota_service 额度边界补测。"""

from datetime import date

import pytest

from app.services.image_quota_service import ImageQuotaService


def test_invalid_daily_limit():
    with pytest.raises(ValueError):
        ImageQuotaService(0)


def test_invalid_amount():
    with pytest.raises(ValueError):
        ImageQuotaService().consume(1, 0)


def test_consume_reduces_remaining():
    service = ImageQuotaService(daily_limit=3)
    day = date(2026, 1, 1)

    assert service.consume(1, on_date=day) == 2
    assert service.consume(1, amount=2, on_date=day) == 0


def test_over_limit_raises():
    service = ImageQuotaService(daily_limit=1)
    day = date(2026, 1, 1)
    service.consume(7, on_date=day)

    with pytest.raises(RuntimeError):
        service.consume(7, on_date=day)


def test_remaining_never_negative():
    service = ImageQuotaService(daily_limit=2)
    assert service.remaining(1, on_date=date(2026, 1, 1)) == 2
