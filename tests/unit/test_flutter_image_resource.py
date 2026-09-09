"""Authenticated cached image delivery without provider calls."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from app.api.v1 import kolors_api


@pytest.mark.asyncio
async def test_cached_image_uses_owned_history(tmp_path, monkeypatch):
    monkeypatch.setattr(kolors_api, "OUTPUT_DIR", tmp_path)
    image = tmp_path / "kolors_123.png"
    image.write_bytes(b"test-image")
    records = MagicMock()
    records.scalars.return_value = [json.dumps({"type": "image", "path": str(image)})]
    db = AsyncMock()
    db.execute.return_value = records
    response = await kolors_api.get_generated_resource(image.name, {"sub": "42"}, db)
    assert response.path == image
    assert response.headers["cache-control"] == "private, no-store"
    query = db.execute.call_args.args[0]
    assert 42 in query.compile().params.values()


@pytest.mark.asyncio
async def test_image_without_owner_history_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(kolors_api, "OUTPUT_DIR", tmp_path)
    records = MagicMock()
    records.scalars.return_value = []
    db = AsyncMock()
    db.execute.return_value = records
    with pytest.raises(HTTPException) as error:
        await kolors_api.get_generated_resource("kolors_missing.png", {"sub": "42"}, db)
    assert error.value.status_code == 404
