"""image_asset_service 收藏、缺失资产与默认时钟补测。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.image_asset_service import ImageAsset, ImageAssetRegistry


def _asset(asset_id=1, user_id=10, expires_in=1):
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    return ImageAsset(asset_id, user_id, f"/tmp/{asset_id}.png", now, now + timedelta(days=expires_in))


def test_set_favorite_updates_and_returns_new_instance():
    registry = ImageAssetRegistry()
    original = _asset()
    registry.add(original)

    updated = registry.set_favorite(1, 10, True)

    assert updated.is_favorite is True
    assert updated is not original
    assert registry.get_for_user(1, 10).is_favorite is True


def test_set_favorite_rejects_unknown_asset():
    registry = ImageAssetRegistry()
    with pytest.raises(PermissionError):
        registry.set_favorite(99, 10, True)


def test_set_favorite_rejects_other_user():
    registry = ImageAssetRegistry()
    registry.add(_asset())
    with pytest.raises(PermissionError):
        registry.set_favorite(1, 20, True)


def test_cleanup_expired_uses_current_clock(monkeypatch):
    registry = ImageAssetRegistry()
    expired = ImageAsset(
        1, 10, "/tmp/1.png",
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2020, 1, 2, tzinfo=timezone.utc),
    )
    registry.add(expired)

    removed = registry.cleanup_expired()

    assert [a.asset_id for a in removed] == [1]


def test_cleanup_expired_skips_assets_without_expiry():
    registry = ImageAssetRegistry()
    registry.add(ImageAsset(1, 10, "/tmp/1.png", datetime(2020, 1, 1, tzinfo=timezone.utc)))
    assert registry.cleanup_expired() == []
