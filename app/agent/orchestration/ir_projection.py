"""Projection from technology-neutral synthesis IR into Core's frozen plan."""

from __future__ import annotations

from typing import Iterable

from ..code_synthesis_contracts import ChangePlanIR
from ..strategy_router import StrategyRouter
from .plan import GenerationPlan, build_file_plan


class UnsupportedArtifactOperation(ValueError):
    """Raised when Core has no execution semantics for an IR lifecycle operation."""


def project_change_plan(
    change_plan: ChangePlanIR,
    *,
    router: StrategyRouter | None = None,
    existing_paths: Iterable[str] = (),
    requested_paths: Iterable[str] | None = None,
) -> GenerationPlan:
    """Convert a routed IR into the immutable plan consumed by GenerationScheduler."""
    router = router or StrategyRouter()
    decisions = router.route_plan(change_plan, existing_paths=existing_paths)
    entries = []
    unsupported = []

    for artifact in change_plan.artifacts:
        if artifact.operation in {"delete", "rename"}:
            unsupported.append(f"{artifact.path}:{artifact.operation}")
            continue
        decision = decisions[artifact.path]
        entries.append({
            "path": artifact.path,
            "role": artifact.role,
            "language": change_plan.project.language,
            "file_type": artifact.role,
            "dependencies": artifact.depends_on,
            "source": artifact.source,
            "reason": artifact.preconditions[0] if artifact.preconditions else None,
            "strategy": decision.strategy.value,
            "strategy_reason": decision.reason,
            "capability_evidence": decision.capability_evidence,
            "degraded": decision.degraded,
        })

    if unsupported:
        raise UnsupportedArtifactOperation(
            "Core generation plan does not support lifecycle operations: "
            + ", ".join(sorted(unsupported))
        )
    if not entries:
        raise ValueError("change plan contains no generatable artifacts")

    return build_file_plan(
        entries,
        requested_paths=requested_paths,
        version=change_plan.schema_version,
    )


__all__ = ["UnsupportedArtifactOperation", "project_change_plan"]
