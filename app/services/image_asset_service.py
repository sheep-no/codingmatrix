"""图片资产访问隔离和生命周期基础能力。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone


@dataclass(frozen=True)
class ImageAsset:
    asset_id: int
    user_id: int
    path: str
    created_at: datetime
    expires_at: datetime | None = None
    is_favorite: bool = False
    status: str = "completed"


class ImageAssetRegistry:
    def __init__(self) -> None:
        self._assets: dict[int, ImageAsset] = {}

    def add(self, asset: ImageAsset) -> None:
        self._assets[asset.asset_id] = asset

    def get_for_user(self, asset_id: int, user_id: int) -> ImageAsset | None:
        asset = self._assets.get(asset_id)
        return asset if asset and asset.user_id == user_id else None

    def set_favorite(self, asset_id: int, user_id: int, value: bool) -> ImageAsset:
        asset = self.get_for_user(asset_id, user_id)
        if asset is None:
            raise PermissionError("asset does not belong to user")
        updated = replace(asset, is_favorite=value)
        self._assets[asset_id] = updated
        return updated

    def cleanup_expired(self, *, now: datetime | None = None) -> list[ImageAsset]:
        current = now or datetime.now(timezone.utc)
        removed: list[ImageAsset] = []
        for asset_id, asset in list(self._assets.items()):
            if (
                asset.expires_at is not None
                and asset.expires_at <= current
                and not asset.is_favorite
                and asset.status != "processing"
            ):
                removed.append(self._assets.pop(asset_id))
        return removed
