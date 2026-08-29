"""Shared helpers for StateGraph capability nodes."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def artifact_summary(value: Any) -> Dict[str, Any]:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "size": len(serialized),
    }
