"""Feature-flagged engine selection for gradual endpoint migration."""

from __future__ import annotations

import os
from typing import Any, Dict


LEGACY_ENGINE = "legacy"
CORE_ENGINE = "core"
LEGACY_ENGINE_VERSION = "legacy-v1"
CORE_ENGINE_VERSION = "core-v1"

# legacy 是唯一受支持默认。core 仍是实验性路由：固定 24 例评估矩阵的
# engineering/quality 通过率为 0/24，target_met=false；在矩阵通过前 core
# 不得成为默认。门禁见 tests/unit/test_orchestration_default_engine.py。
# 显式设置 AGENT_ORCHESTRATION_ENGINE=core 属于 opt-in，不在此门禁范围内。
DEFAULT_ENGINE = LEGACY_ENGINE


def select_engine(requested: str | None = None) -> str:
    value = (requested or os.getenv("AGENT_ORCHESTRATION_ENGINE", DEFAULT_ENGINE)).strip().lower()
    return CORE_ENGINE if value == CORE_ENGINE else LEGACY_ENGINE


def engine_metadata(engine: str) -> Dict[str, Any]:
    selected = select_engine(engine)
    return {
        "engine": selected,
        "engine_version": CORE_ENGINE_VERSION if selected == CORE_ENGINE else LEGACY_ENGINE_VERSION,
        "engine_route": "experimental" if selected == CORE_ENGINE else "stable",
    }
