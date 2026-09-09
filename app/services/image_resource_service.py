"""资源受控的图片生成基础能力。"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
import time
from typing import Any, TypeVar


_GenerationResult = TypeVar("_GenerationResult")
_flight_lock: asyncio.Lock | None = None
_generation_flights: dict[str, asyncio.Task[Any]] = {}


class GenerationConcurrencyLimiter:
    """Limit provider work globally and independently for each user."""

    def __init__(self, global_limit: int = 4, user_limit: int = 2) -> None:
        if global_limit < 1 or user_limit < 1:
            raise ValueError("concurrency limits must be positive")
        self._global = asyncio.Semaphore(global_limit)
        self._user_limit = user_limit
        self._users: dict[int, asyncio.Semaphore] = {}
        self._users_lock = asyncio.Lock()

    @asynccontextmanager
    async def global_slot(self):
        async with self._global:
            yield

    @asynccontextmanager
    async def user_slot(self, user_id: int):
        async with self._users_lock:
            user_semaphore = self._users.setdefault(
                user_id, asyncio.Semaphore(self._user_limit)
            )
        async with user_semaphore:
            yield


generation_concurrency = GenerationConcurrencyLimiter()


def build_generation_response(
    result: dict[str, Any],
    *,
    cached: bool,
) -> dict[str, Any]:
    """Return one compatible response shape for generated and cached assets."""

    paths = list(result.get("paths") or [])
    response = {
        "success": bool(result.get("success")),
        "cached": cached,
        "status": "completed" if result.get("success") else "failed",
        "images": list(result.get("images") or []),
        "paths": paths,
        "paths_hash": [path.rsplit("/", 1)[-1] for path in paths],
    }
    if cached:
        response["message"] = "使用缓存的图片"
    return response


def cleanup_file(path: str | Path) -> bool:
    """Remove one generated or temporary file and report whether it existed."""

    target = Path(path)
    try:
        target.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def cleanup_stale_files(
    directory: str | Path,
    *,
    max_age_seconds: int,
    protected_paths: set[str | Path] | None = None,
) -> int:
    """Remove old regular files while preserving explicitly protected assets."""

    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")

    root = Path(directory)
    protected = {Path(path).resolve() for path in (protected_paths or set())}
    cutoff = time.time() - max_age_seconds
    removed = 0
    if not root.is_dir():
        return removed

    for path in root.iterdir():
        if not path.is_file() or path.resolve() in protected:
            continue
        try:
            if path.stat().st_mtime < cutoff and cleanup_file(path):
                removed += 1
        except OSError:
            continue
    return removed


async def get_or_create_generation(
    *,
    fingerprint: str,
    owner: Callable[[], Awaitable[_GenerationResult]],
) -> _GenerationResult:
    """Merge concurrent requests for one fingerprint into a shared task."""

    global _flight_lock
    if _flight_lock is None:
        _flight_lock = asyncio.Lock()

    async with _flight_lock:
        task = _generation_flights.get(fingerprint)
        if task is None:
            task = asyncio.create_task(owner())
            _generation_flights[fingerprint] = task

    try:
        return await asyncio.shield(task)
    finally:
        if task.done():
            async with _flight_lock:
                if _generation_flights.get(fingerprint) is task:
                    _generation_flights.pop(fingerprint, None)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFC", str(value)).strip()
    return normalized or None


def _normalize_number(value: int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("numeric generation parameters must be finite")
        rounded = round(value, 6)
        return int(rounded) if rounded.is_integer() else rounded
    return int(value)


def _canonical_payload(**kwargs: Any) -> dict[str, Any]:
    return {
        "user_id": _normalize_number(kwargs["user_id"]),
        "model": _normalize_text(kwargs["model"]),
        "generation_type": _normalize_text(kwargs["generation_type"]),
        "prompt": _normalize_text(kwargs["prompt"]),
        "negative_prompt": _normalize_text(kwargs["negative_prompt"]),
        "style": _normalize_text(kwargs["style"]),
        "reference_hash": _normalize_text(kwargs["reference_hash"]),
        "width": _normalize_number(kwargs["width"]),
        "height": _normalize_number(kwargs["height"]),
        "steps": _normalize_number(kwargs["steps"]),
        "guidance_scale": _normalize_number(kwargs["guidance_scale"]),
        "strength": _normalize_number(kwargs["strength"]),
        "num_images": _normalize_number(kwargs["num_images"]),
        "seed": _normalize_number(kwargs["seed"]),
    }


def build_image_resource_fingerprint(
    *,
    user_id: int,
    model: str,
    generation_type: str,
    prompt: str,
    negative_prompt: str,
    style: str | None,
    reference_hash: str | None,
    width: int,
    height: int,
    steps: int,
    guidance_scale: float,
    strength: float | None,
    num_images: int,
    seed: int | None,
) -> str:
    """Return a stable SHA-256 fingerprint for an equivalent request."""

    payload = _canonical_payload(
        user_id=user_id,
        model=model,
        generation_type=generation_type,
        prompt=prompt,
        negative_prompt=negative_prompt,
        style=style,
        reference_hash=reference_hash,
        width=width,
        height=height,
        steps=steps,
        guidance_scale=guidance_scale,
        strength=strength,
        num_images=num_images,
        seed=seed,
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_reference_bytes(content: bytes) -> str:
    """Hash reference image content so temporary paths do not affect caching."""

    return hashlib.sha256(content).hexdigest()
