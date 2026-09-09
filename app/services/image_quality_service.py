"""图片资源档位、缩略图和基础质量检查。"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from PIL import Image, UnidentifiedImageError


_GenerationResult = TypeVar("_GenerationResult")


RESOURCE_PROFILES: dict[str, dict[str, int]] = {
    "preview": {"width": 512, "height": 512, "steps": 24, "num_images": 1},
    "standard": {"width": 768, "height": 768, "steps": 36, "num_images": 1},
    "high": {"width": 1024, "height": 1024, "steps": 50, "num_images": 1},
}


def resolve_resource_profile(profile: str) -> dict[str, int]:
    try:
        return dict(RESOURCE_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"unsupported resource profile: {profile}") from exc


def validate_resource_request(
    *, profile: str, width: int, height: int, steps: int, num_images: int
) -> dict[str, int]:
    expected = resolve_resource_profile(profile)
    if (width, height, steps, num_images) != (
        expected["width"], expected["height"], expected["steps"], expected["num_images"]
    ):
        raise ValueError(f"request does not match resource profile: {profile}")
    return expected


def inspect_image(path: str | Path, *, max_bytes: int = 20 * 1024 * 1024) -> dict[str, Any]:
    image_path = Path(path)
    if not image_path.is_file():
        return {"valid": False, "reason": "missing"}
    if image_path.stat().st_size > max_bytes:
        return {"valid": False, "reason": "too_large"}
    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
            image_format = image.format
        return {
            "valid": width > 0 and height > 0,
            "width": width,
            "height": height,
            "format": image_format,
            "bytes": image_path.stat().st_size,
        }
    except (OSError, UnidentifiedImageError):
        return {"valid": False, "reason": "invalid_image"}


def create_thumbnail(path: str | Path, destination: str | Path, *, max_size: tuple[int, int] = (320, 320)) -> dict[str, Any]:
    source = Path(path)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.thumbnail(max_size)
        image.save(target, format="PNG", optimize=True)
        width, height = image.size
    return {"path": str(target), "width": width, "height": height, "bytes": target.stat().st_size}


async def generate_with_quality_retry(
    generator: Callable[[], Awaitable[_GenerationResult]],
    validator: Callable[[_GenerationResult], bool],
    *,
    max_retries: int = 1,
) -> tuple[_GenerationResult, int]:
    """Retry generation once when the local result fails quality validation."""

    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    for attempt in range(max_retries + 1):
        result = await generator()
        if validator(result):
            return result, attempt
    raise ValueError("generated image failed quality validation")
