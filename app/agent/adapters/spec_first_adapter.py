"""Translate Spec-first and topology artifacts into graph state deltas."""

from __future__ import annotations

from typing import Any, Dict

from app.agent.state import StateDelta


def spec_first_result_to_delta(
    result: Dict[str, Any],
    *,
    revision: int,
    stage: str,
) -> StateDelta:
    """Keep spec, dependency, and topology output under explicit metadata keys."""
    if not isinstance(result, dict):
        raise TypeError("Spec-first result must be a dictionary")
    metadata = {"spec_first_stage": stage}
    if stage in {"requirements", "specification"}:
        metadata["spec_artifacts"] = result
    elif stage == "dependency_graph":
        metadata["graph_artifact"] = result
    elif stage == "topology_schedule":
        metadata["topology_artifact"] = result
    else:
        metadata["stage_artifact"] = result
    return StateDelta(
        expected_revision=revision,
        status="generated",
        planned_changes=result.get("file_plan", []) if stage == "specification" else [],
        metadata=metadata,
    )
