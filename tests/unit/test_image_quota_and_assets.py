from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.image_asset_service import ImageAsset, ImageAssetRegistry
from app.services.image_quota_service import ImageQuotaService


def test_image_quota_tracks_users_and_rejects_over_limit():
    quota = ImageQuotaService(daily_limit=2)
    today = date(2026, 9, 5)

    assert quota.consume(1, on_date=today) == 1
    assert quota.consume(1, on_date=today) == 0
    assert quota.remaining(2, on_date=today) == 2
    with pytest.raises(RuntimeError):
        quota.consume(1, on_date=today)


def test_asset_registry_enforces_ownership_and_preserves_favorites():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    registry = ImageAssetRegistry()
    registry.add(ImageAsset(1, 10, "/tmp/one.png", now, now - timedelta(days=1)))
    registry.add(ImageAsset(2, 10, "/tmp/two.png", now, now - timedelta(days=1), True))
    registry.add(ImageAsset(3, 10, "/tmp/three.png", now, now - timedelta(days=1), False, "processing"))
    registry.add(ImageAsset(4, 20, "/tmp/four.png", now, now - timedelta(days=1)))

    assert registry.get_for_user(1, 20) is None

    removed = registry.cleanup_expired(now=now)
    assert [asset.asset_id for asset in removed] == [1, 4]
    assert registry.get_for_user(2, 10) is not None
    assert registry.get_for_user(3, 10) is not None
