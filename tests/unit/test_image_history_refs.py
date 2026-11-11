"""Generated image history references stay resolvable and scoped (FRESCAN-61)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import kolors_api
from app.services.image_history_refs import (
    filename_from_reference,
    normalize_image_references,
    resolve_reference,
)


def test_filename_from_reference_handles_paths_and_data_urls():
    assert filename_from_reference("/tmp/out/kolors_1.png") == "kolors_1.png"
    assert filename_from_reference("generated_images/kolors_2.png?token=1") == "kolors_2.png"
    assert filename_from_reference("data:image/png;base64,abc") is None
    assert filename_from_reference(None) is None


def test_normalize_image_references_drops_unresolvable_values():
    assert normalize_image_references([
        "/tmp/out/kolors_1.png",
        "data:image/png;base64,abc",
        "",
        "kolors_2.png",
    ]) == ["kolors_1.png", "kolors_2.png"]
    assert normalize_image_references("kolors_1.png") == []


def test_resolve_reference_stays_inside_root(tmp_path):
    target = resolve_reference("kolors_1.png", tmp_path)
    assert target == (tmp_path / "kolors_1.png").resolve()
    # 目录部分在归一阶段被剥离，引用始终落在输出目录内
    escaped = resolve_reference("../escape.png", tmp_path)
    assert escaped == (tmp_path / "escape.png").resolve()
    assert resolve_reference("data:image/png;base64,abc", tmp_path) is None


@pytest.mark.asyncio
async def test_resource_is_owned_via_image_generation_history_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(kolors_api, "OUTPUT_DIR", tmp_path)
    image = tmp_path / "kolors_owned.png"
    image.write_bytes(b"test-image")

    metadata_records = MagicMock()
    metadata_records.scalars.return_value = []
    image_records = MagicMock()
    image_records.scalars.return_value = [["kolors_owned.png"]]
    db = AsyncMock()
    db.execute.side_effect = [metadata_records, image_records]

    response = await kolors_api.get_generated_resource(image.name, {"sub": "42"}, db)
    assert Path(response.path) == image


@pytest.mark.asyncio
async def test_resource_rejects_foreign_history_row(tmp_path, monkeypatch):
    monkeypatch.setattr(kolors_api, "OUTPUT_DIR", tmp_path)
    image = tmp_path / "kolors_foreign.png"
    image.write_bytes(b"test-image")

    metadata_records = MagicMock()
    metadata_records.scalars.return_value = []
    image_records = MagicMock()
    image_records.scalars.return_value = [["kolors_other.png"]]
    db = AsyncMock()
    db.execute.side_effect = [metadata_records, image_records]

    with pytest.raises(HTTPException) as error:
        await kolors_api.get_generated_resource(image.name, {"sub": "42"}, db)
    assert error.value.status_code == 404
