"""Testable asynchronous orchestration for the PPT generation stages."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


STAGES = ("planning", "assets", "rendering", "rule_qa", "reflow", "vision_qa", "completed")
StageHandler = Callable[[dict[str, Any]], Any]
ProgressCallback = Callable[[dict[str, Any]], Any]
CancelCheck = Callable[[], Any]


class OrchestrationCancelled(Exception):
    """Raised internally when cancellation is requested between stages."""


@dataclass
class OrchestrationResult:
    """The serializable outcome of one orchestration run."""

    status: str
    stage: str
    context: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class PPTGenerationOrchestrator:
    """Run injected PPT stages in order with progress and recovery support."""

    stages = STAGES

    def __init__(
        self,
        handlers: Mapping[str, StageHandler] | None = None,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.handlers = dict(handlers or {})
        self.progress_callback = progress_callback
        self.cancel_check = cancel_check

    async def run(
        self,
        context: Mapping[str, Any] | None = None,
        *,
        start_stage: str = "planning",
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> OrchestrationResult:
        """Run from ``start_stage`` and return a terminal, recoverable result."""
        if start_stage not in self.stages:
            raise ValueError(f"start_stage must be one of {self.stages!r}")

        state = dict(context or {})
        quality_mode = state.get("quality_mode")
        stages = tuple(
            stage for stage in self.stages
            if stage != "vision_qa" or quality_mode != "standard"
        )
        if start_stage not in stages:
            raise ValueError(f"start_stage is unavailable for quality_mode={quality_mode!r}")
        emit = progress_callback or self.progress_callback
        check_cancel = cancel_check or self.cancel_check
        first_index = stages.index(start_stage)
        stage_count = len(stages)

        try:
            for index, stage in enumerate(stages[first_index:], start=first_index):
                await self._check_cancel(check_cancel)
                await self._emit(emit, stage, "started", index / stage_count)

                handler = self.handlers.get(stage)
                if handler is not None:
                    updated = handler(state)
                    if inspect.isawaitable(updated):
                        updated = await updated
                    if updated is not None:
                        state = dict(updated)

                await self._check_cancel(check_cancel)
                await self._emit(emit, stage, "completed", (index + 1) / stage_count)

            return OrchestrationResult("completed", "completed", state)
        except OrchestrationCancelled:
            await self._emit(emit, stage, "cancelled", index / stage_count)
            return OrchestrationResult("cancelled", stage, state)
        except Exception as exc:
            await self._emit(emit, stage, "failed", index / stage_count, error=str(exc))
            return OrchestrationResult("failed", stage, state, str(exc))

    async def _check_cancel(self, check_cancel: CancelCheck | None) -> None:
        if check_cancel is None:
            return
        requested = check_cancel()
        if inspect.isawaitable(requested):
            requested = await requested
        if requested:
            raise OrchestrationCancelled

    async def _emit(
        self,
        callback: ProgressCallback | None,
        stage: str,
        status: str,
        progress: float,
        **extra: Any,
    ) -> None:
        if callback is None:
            return
        event = {"stage": stage, "status": status, "progress": progress, **extra}
        result = callback(event)
        if inspect.isawaitable(result):
            await result


async def run_ppt_generation(
    context: Mapping[str, Any] | None = None,
    *,
    handlers: Mapping[str, StageHandler] | None = None,
    start_stage: str = "planning",
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> OrchestrationResult:
    """Convenience entry point for callers that do not need an instance."""
    return await PPTGenerationOrchestrator(
        handlers,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    ).run(context, start_stage=start_stage)
