"""Shared helpers for StateGraph capability nodes."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def artifact_summary(value: Any) -> dict[str, Any]:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "size": len(serialized),
    }
