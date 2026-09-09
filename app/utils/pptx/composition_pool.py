"""Deterministic slide composition and cover selection pools."""

import hashlib
import random
from typing import Iterable


# Variant zero is the primary role-driven composition. Variants 1-6 map to
# the existing modern composition families in aiGeneratorPptx.py.
LAYOUT_VARIANT_POOL = tuple(range(11))
COVER_VARIANT_POOL = tuple(range(4))


def _stable_offset(topic: str, salt: str, size: int) -> int:
    digest = hashlib.sha256(f"{salt}:{topic}".encode("utf-8")).digest()
    return digest[0] % size


def select_layout_variants(
    topic: str,
    count: int,
    *,
    recent_variants: Iterable[int] = (),
) -> list[int]:
    """Return a stable, non-adjacent sequence for a deck's content pages."""
    if count <= 0:
        return []

    pool = list(LAYOUT_VARIANT_POOL)
    seed = int.from_bytes(hashlib.sha256(f"layout:{topic}".encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    recent = {variant for variant in recent_variants if variant in LAYOUT_VARIANT_POOL}
    sequence: list[int] = []

    while len(sequence) < count:
        cycle = pool.copy()
        rng.shuffle(cycle)
        if sequence and cycle[0] == sequence[-1]:
            cycle[0], cycle[1] = cycle[1], cycle[0]
        if not sequence and recent:
            cycle = [variant for variant in cycle if variant not in recent] + [variant for variant in cycle if variant in recent]
        sequence.extend(cycle)

    return sequence[:count]


def select_cover_variant(topic: str) -> int:
    """Select a stable cover composition variant for a topic."""
    return _stable_offset(topic, "cover", len(COVER_VARIANT_POOL))
