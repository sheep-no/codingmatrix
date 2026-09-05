"""Endpoint-facing execution helper for Core generation adapters."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from app.agent.shared_context import SharedContext

from .adapters import GenerationModeAdapter
from .core import OrchestratorCore
from .models import OrchestrationCommand
from .routing import CORE_ENGINE_VERSION
from .store import OrchestrationCheckpointStore


def _checkpoint_task_id(task_id: str, mode: str) -> str:
    candidate = f"{task_id}-{mode}"
    if Path(candidate).name == candidate and len(candidate) <= 180:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    return f"core-{digest}"


async def execute_core_generation(
    adapter: GenerationModeAdapter,
    *,
    requirement: str,
    task_id: str,
    session_id: str,
    mode: str,
    output_dir: Path,
    metadata: Optional[Mapping[str, Any]] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> Dict[str, Any]:
    """Execute one adapter and project its result onto the existing API contract."""
    request = {"requirement": requirement, **dict(metadata or {})}
    if "profile_context" not in request:
        from app.agent.profile_discovery import profile_context

        request["profile_context"] = profile_context(output_dir)
    if "toolchain_plan" not in request:
        from app.agent.toolchain import detect_toolchain

        request["toolchain_plan"] = detect_toolchain(output_dir).model_dump(mode="json")
    core_task_id = _checkpoint_task_id(task_id, mode)
    context = SharedContext(requirement, output_dir)
    if hasattr(adapter, "_shared_context"):
        adapter._shared_context = context
    core = OrchestratorCore(
        OrchestrationCheckpointStore(Path(os.getenv(
            "AGENT_CORE_CHECKPOINT_DIR",
            "data/orchestration_core_checkpoints",
        )))
    )
    result = await core.execute(
        OrchestrationCommand(
            task_id=core_task_id,
            session_id=session_id,
            mode=mode,
            request=request,
            engine_version=CORE_ENGINE_VERSION,
        ),
        adapter,
        output_dir=output_dir,
        shared_context=context,
        cancel_event=cancel_event,
    )
    finalized = await adapter.finalize(result.state)
    return dict(finalized.result)
