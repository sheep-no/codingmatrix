"""Feature-flagged engine selection for gradual endpoint migration."""

from __future__ import annotations

import os
from typing import Any, Dict


LEGACY_ENGINE = "legacy"
CORE_ENGINE = "core"
LEGACY_ENGINE_VERSION = "legacy-v1"
CORE_ENGINE_VERSION = "core-v1"


def select_engine(requested: str | None = None) -> str:
    value = (requested or os.getenv("AGENT_ORCHESTRATION_ENGINE", LEGACY_ENGINE)).strip().lower()
    return CORE_ENGINE if value == CORE_ENGINE else LEGACY_ENGINE


def engine_metadata(engine: str) -> Dict[str, Any]:
    selected = select_engine(engine)
    return {
        "engine": selected,
        "engine_version": CORE_ENGINE_VERSION if selected == CORE_ENGINE else LEGACY_ENGINE_VERSION,
        "engine_route": "experimental" if selected == CORE_ENGINE else "stable",
    }
