"""image_quality_service 资源档位与校验边界补测。"""

import asyncio

import pytest
from PIL import Image

from app.services.image_quality_service import (
    generate_with_quality_retry,
    inspect_image,
    resolve_resource_profile,
)


def test_unknown_resource_profile_raises():
    with pytest.raises(ValueError, match="unsupported resource profile"):
        resolve_resource_profile("ultra")


def test_missing_image_is_reported(tmp_path):
    assert inspect_image(tmp_path / "nope.png") == {"valid": False, "reason": "missing"}


def test_oversized_image_is_rejected(tmp_path):
    path = tmp_path / "big.png"
    Image.new("RGB", (8, 8), "blue").save(path)

    assert inspect_image(path, max_bytes=1) == {"valid": False, "reason": "too_large"}


def test_negative_retries_are_rejected():
    async def generator():
        return 1

    with pytest.raises(ValueError, match="non-negative"):
        asyncio.run(generate_with_quality_retry(generator, lambda _: True, max_retries=-1))


def test_quality_failure_exhausts_retries():
    calls = 0

    async def generator():
        nonlocal calls
        calls += 1
        return "bad"

    with pytest.raises(ValueError, match="quality"):
        asyncio.run(generate_with_quality_retry(generator, lambda _: False, max_retries=2))

    assert calls == 3


def test_zero_retries_succeeds_immediately():
    async def generator():
        return "good"

    result, attempts = asyncio.run(
        generate_with_quality_retry(generator, lambda value: value == "good", max_retries=0)
    )
    assert (result, attempts) == ("good", 0)
