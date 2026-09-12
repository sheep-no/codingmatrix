import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.db.models import ImageGenerationHistory
from app.models.base import Base
from app.services.generated_asset_retention import (
    cleanup_expired_image_history,
    cleanup_expired_ppt_artifacts,
    cleanup_generated_assets,
    ppt_id_from_filename,
)


def _touch(path: Path, age_seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"asset")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_ppt_id_from_filename_maps_known_artifacts():
    assert ppt_id_from_filename("abc_slides.json") == "abc"
    assert ppt_id_from_filename("abc.pptx") == "abc"
    assert ppt_id_from_filename("abc.pdf") == "abc"
    assert ppt_id_from_filename("readme.txt") is None


def test_cleanup_expired_ppt_artifacts_removes_old_group_and_keeps_fresh(tmp_path):
    old_id = "old-ppt"
    fresh_id = "fresh-ppt"
    mixed_id = "mixed-ppt"

    _touch(tmp_path / f"{old_id}_slides.json", 40 * 24 * 3600)
    _touch(tmp_path / f"{old_id}.pptx", 40 * 24 * 3600)
    _touch(tmp_path / ".owners" / f"{old_id}.json", 40 * 24 * 3600)

    _touch(tmp_path / f"{fresh_id}_slides.json", 3600)
    _touch(tmp_path / f"{fresh_id}.pptx", 3600)

    _touch(tmp_path / f"{mixed_id}_slides.json", 40 * 24 * 3600)
    _touch(tmp_path / f"{mixed_id}.pptx", 60)

    stats = cleanup_expired_ppt_artifacts(tmp_path, max_age_seconds=30 * 24 * 3600)

    assert stats["removed_ids"] == 1
    assert stats["removed_files"] == 3
    assert not (tmp_path / f"{old_id}.pptx").exists()
    assert not (tmp_path / ".owners" / f"{old_id}.json").exists()
    assert (tmp_path / f"{fresh_id}.pptx").exists()
    assert (tmp_path / f"{mixed_id}_slides.json").exists()
    assert (tmp_path / f"{mixed_id}.pptx").exists()


def test_cleanup_expired_ppt_artifacts_rejects_negative_age(tmp_path):
    with pytest.raises(ValueError):
        cleanup_expired_ppt_artifacts(tmp_path, max_age_seconds=-1)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_expired_image_history_deletes_old_rows_and_orphans(db, tmp_path):
    old_file = tmp_path / "old.png"
    fresh_file = tmp_path / "fresh.png"
    orphan_file = tmp_path / "orphan.png"
    protected_file = tmp_path / "protected.png"
    _touch(old_file, 40 * 24 * 3600)
    _touch(fresh_file, 3600)
    _touch(orphan_file, 40 * 24 * 3600)
    _touch(protected_file, 40 * 24 * 3600)

    db.add(
        ImageGenerationHistory(
            image_id="old-image",
            user_id="1",
            prompt="old",
            image_urls=[str(old_file)],
            created_at=datetime.now() - timedelta(days=40),
        )
    )
    db.add(
        ImageGenerationHistory(
            image_id="fresh-image",
            user_id="1",
            prompt="fresh",
            image_urls=[str(fresh_file), str(protected_file)],
            created_at=datetime.now() - timedelta(hours=1),
        )
    )
    await db.flush()

    stats = await cleanup_expired_image_history(
        db,
        max_age_seconds=30 * 24 * 3600,
        image_dir=tmp_path,
    )

    remaining = (await db.scalars(select(ImageGenerationHistory))).all()
    remaining_ids = [row.image_id for row in remaining]

    assert stats["removed_records"] == 1
    assert stats["removed_orphans"] == 1
    assert remaining_ids == ["fresh-image"]
    assert not old_file.exists()
    assert not orphan_file.exists()
    assert fresh_file.exists()
    assert protected_file.exists()


@pytest.mark.asyncio
async def test_cleanup_generated_assets_combines_ppt_and_image_cleanup(db, tmp_path):
    ppt_dir = tmp_path / "pptx_output"
    image_dir = tmp_path / "generated_images"
    old_ppt = ppt_dir / "expired_slides.json"
    old_image = image_dir / "expired.png"
    _touch(old_ppt, 40 * 24 * 3600)
    _touch(old_image, 40 * 24 * 3600)

    db.add(
        ImageGenerationHistory(
            image_id="expired-image",
            user_id="1",
            prompt="expired",
            image_urls=[str(old_image)],
            created_at=datetime.now() - timedelta(days=40),
        )
    )
    await db.flush()

    result = await cleanup_generated_assets(
        db,
        max_age_seconds=30 * 24 * 3600,
        ppt_output_dir=ppt_dir,
        image_dir=image_dir,
    )

    assert result["ppt"]["removed_ids"] == 1
    assert result["images"]["removed_records"] == 1
    assert not old_ppt.exists()
    assert not old_image.exists()
