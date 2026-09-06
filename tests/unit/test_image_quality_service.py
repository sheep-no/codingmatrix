import asyncio

from PIL import Image
import pytest

from app.services.image_quality_service import (
    create_thumbnail,
    generate_with_quality_retry,
    inspect_image,
    resolve_resource_profile,
    validate_resource_request,
)


def test_resource_profiles_validate_exact_backend_limits():
    assert resolve_resource_profile("preview")["steps"] == 24
    assert validate_resource_request(
        profile="standard", width=768, height=768, steps=36, num_images=1
    )["width"] == 768

    with pytest.raises(ValueError):
        validate_resource_request(
            profile="standard", width=1024, height=1024, steps=36, num_images=1
        )


def test_inspect_image_and_create_thumbnail(tmp_path):
    source = tmp_path / "source.png"
    thumbnail = tmp_path / "thumb.png"
    Image.new("RGB", (1024, 768), "red").save(source)

    info = inspect_image(source)
    result = create_thumbnail(source, thumbnail)

    assert info["valid"] is True
    assert (info["width"], info["height"]) == (1024, 768)
    assert result["path"] == str(thumbnail)
    assert result["width"] <= 320
    assert result["height"] <= 320
    assert inspect_image(thumbnail)["valid"] is True


def test_inspect_image_rejects_invalid_content(tmp_path):
    path = tmp_path / "invalid.png"
    path.write_bytes(b"not-an-image")

    assert inspect_image(path)["valid"] is False


def test_quality_retry_returns_retry_count():
    calls = 0

    async def generator():
        nonlocal calls
        calls += 1
        return calls

    result, retries = asyncio.run(
        generate_with_quality_retry(generator, lambda value: value == 2)
    )

    assert (result, retries, calls) == (2, 1, 2)
