from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.kolors_api import TextToImageRequest, text_to_image_api


@pytest.mark.asyncio
async def test_text_to_image_cache_hit_skips_provider():
    request = TextToImageRequest(prompt="a red bird")

    with (
        patch("app.api.v1.kolors_api.get_cached_image", new=AsyncMock(return_value="/tmp/cached.png")) as get_cache,
        patch("app.api.v1.kolors_api.text_to_image", new=AsyncMock()) as provider,
    ):
        result = await text_to_image_api(request, token={"sub": "7"}, db=AsyncMock())

    assert result["cached"] is True
    assert result["paths"] == ["/tmp/cached.png"]
    provider.assert_not_awaited()
    assert get_cache.await_args.kwargs["fingerprint"]


@pytest.mark.asyncio
async def test_text_to_image_cache_miss_calls_provider_and_persists_fingerprint():
    request = TextToImageRequest(prompt="a red bird")
    provider_result = {
        "success": True,
        "images": ["data:image/png;base64,abc"],
        "paths": ["/tmp/generated.png"],
    }

    with (
        patch("app.api.v1.kolors_api.get_cached_image", new=AsyncMock(return_value=None)),
        patch("app.api.v1.kolors_api.text_to_image", new=AsyncMock(return_value=provider_result)) as provider,
        patch("app.api.v1.kolors_api.cache_image_to_history", new=AsyncMock()) as cache_history,
        patch("app.api.v1.kolors_api.save_image_generation_history", new=AsyncMock()),
    ):
        result = await text_to_image_api(request, token={"sub": "7"}, db=AsyncMock())

    assert result["cached"] is False
    provider.assert_awaited_once()
    assert cache_history.await_args.args[4]
