"""Age-based cleanup for PPT and Kolors generated artifacts."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ImageGenerationHistory
from app.services.image_resource_service import cleanup_file, cleanup_stale_files

DEFAULT_PPT_OUTPUT_DIR = Path("./pptx_output")
DEFAULT_IMAGE_OUTPUT_DIR = Path("./generated_images")
_PPT_FILE_SUFFIXES = (".pptx", ".html", ".md", ".pdf")
_SLIDES_SUFFIX = "_slides.json"


def retention_max_age_seconds(days: int | None = None) -> int:
    """Convert configured retention days into seconds."""

    retention_days = settings.GENERATED_ASSET_RETENTION_DAYS if days is None else days
    if retention_days < 1:
        raise ValueError("retention days must be >= 1")
    return retention_days * 24 * 60 * 60


def ppt_id_from_filename(name: str) -> str | None:
    """Map a generated PPT filename back to its task id."""

    if name.endswith(_SLIDES_SUFFIX):
        ppt_id = name[: -len(_SLIDES_SUFFIX)]
        return ppt_id or None
    for suffix in _PPT_FILE_SUFFIXES:
        if name.endswith(suffix):
            ppt_id = name[: -len(suffix)]
            return ppt_id or None
    return None


def collect_ppt_groups(output_dir: str | Path) -> dict[str, list[Path]]:
    """Group PPT artifacts and owner files by task id."""

    root = Path(output_dir)
    groups: dict[str, list[Path]] = {}
    if not root.is_dir():
        return groups

    for path in root.iterdir():
        if not path.is_file():
            continue
        ppt_id = ppt_id_from_filename(path.name)
        if ppt_id:
            groups.setdefault(ppt_id, []).append(path)

    owner_dir = root / ".owners"
    if owner_dir.is_dir():
        for path in owner_dir.glob("*.json"):
            if path.is_file():
                groups.setdefault(path.stem, []).append(path)
    return groups


def _newest_mtime(paths: list[Path]) -> float | None:
    newest: float | None = None
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def cleanup_expired_ppt_artifacts(
    output_dir: str | Path,
    *,
    max_age_seconds: int,
    now: float | None = None,
) -> dict[str, int]:
    """Delete PPT groups whose newest file is older than the retention window."""

    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")

    cutoff = (time.time() if now is None else now) - max_age_seconds
    removed_ids = 0
    removed_files = 0
    for _ppt_id, paths in collect_ppt_groups(output_dir).items():
        newest = _newest_mtime(paths)
        if newest is None or newest >= cutoff:
            continue
        for path in paths:
            if cleanup_file(path):
                removed_files += 1
        removed_ids += 1
    return {"removed_ids": removed_ids, "removed_files": removed_files}


async def cleanup_expired_image_history(
    db: AsyncSession,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
    image_dir: str | Path | None = None,
) -> dict[str, int]:
    """Delete expired image history rows, their files, and leftover orphans."""

    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")

    cutoff = (now or datetime.now()) - timedelta(seconds=max_age_seconds)
    records = (
        await db.scalars(
            select(ImageGenerationHistory).where(
                ImageGenerationHistory.created_at < cutoff
            )
        )
    ).all()

    removed_records = 0
    removed_files = 0
    for record in records:
        for url in record.image_urls or []:
            if url and cleanup_file(url):
                removed_files += 1
        await db.delete(record)
        removed_records += 1

    if records:
        await db.flush()

    removed_orphans = 0
    if image_dir is not None:
        remaining = (await db.scalars(select(ImageGenerationHistory))).all()
        protected = {
            Path(url) for record in remaining for url in (record.image_urls or []) if url
        }
        removed_orphans = cleanup_stale_files(
            image_dir,
            max_age_seconds=max_age_seconds,
            protected_paths=protected,
        )

    return {
        "removed_records": removed_records,
        "removed_files": removed_files,
        "removed_orphans": removed_orphans,
    }


async def cleanup_generated_assets(
    db: AsyncSession | None = None,
    *,
    max_age_seconds: int | None = None,
    ppt_output_dir: str | Path | None = None,
    image_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run PPT filesystem cleanup and image history cleanup together."""

    seconds = (
        retention_max_age_seconds()
        if max_age_seconds is None
        else max_age_seconds
    )
    ppt_dir = DEFAULT_PPT_OUTPUT_DIR if ppt_output_dir is None else Path(ppt_output_dir)
    images = DEFAULT_IMAGE_OUTPUT_DIR if image_dir is None else Path(image_dir)
    ppt_now = None if now is None else now.timestamp()
    ppt_stats = cleanup_expired_ppt_artifacts(
        ppt_dir,
        max_age_seconds=seconds,
        now=ppt_now,
    )

    if db is not None:
        image_stats = await cleanup_expired_image_history(
            db,
            max_age_seconds=seconds,
            now=now,
            image_dir=images,
        )
        return {"ppt": ppt_stats, "images": image_stats}

    from app.db.database import async_session

    async with async_session() as session:
        image_stats = await cleanup_expired_image_history(
            session,
            max_age_seconds=seconds,
            now=now,
            image_dir=images,
        )
        await session.commit()
    return {"ppt": ppt_stats, "images": image_stats}
