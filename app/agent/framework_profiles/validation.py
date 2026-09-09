"""Executable validation for declarative framework profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner

from . import FrameworkProfile, ValidationStage


def validation_targets_for_workflow(
    workflow: Any,
    registry: Any,
) -> tuple[tuple[str, FrameworkProfile], ...]:
    """Resolve one deterministic validation profile per declared node stack."""
    targets: dict[tuple[str, str], FrameworkProfile] = {}
    for node in getattr(workflow, "nodes", ()):
        technology = getattr(node, "technology", None)
        if technology is None or not technology.language:
            continue
        profile = registry.validation_profile(
            technology.language,
            technology.framework,
        )
        if profile is None:
            continue
        profile_language = str(getattr(profile, "language", technology.language)).lower()
        profile_name = str(getattr(profile, "name", technology.framework or profile_language)).lower()
        targets[(profile_language, profile_name)] = profile
    return tuple(
        sorted(targets.items(), key=lambda item: item[0])
    )


async def validate_workflow_profiles(
    project_dir: Path,
    workflow: Any,
    registry: Any,
    *,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Run deduplicated validation profiles for a mixed technology workflow."""
    results: dict[str, Any] = {}
    targets = validation_targets_for_workflow(workflow, registry)
    for key, profile in targets:
        try:
            result = await validate_project_profile(
                project_dir,
                profile,
                timeout_seconds=timeout_seconds,
            )
        except TypeError as exc:
            if "timeout_seconds" not in str(exc):
                raise
            result = await validate_project_profile(project_dir, profile)
        profile_name = str(getattr(profile, "name", key[1]))
        results[profile_name] = result
        if not result.get("passed", False):
            if len(targets) == 1:
                return result
            return {"passed": False, "profiles": results, "failed_profile": profile_name}
    if len(targets) == 1:
        return next(iter(results.values()))
    return {"passed": True, "profiles": results}


_ACTIONS = {
    ValidationStage.INSTALL: ToolchainAction.INSTALL,
    ValidationStage.LINT: ToolchainAction.LINT,
    ValidationStage.TYPECHECK: ToolchainAction.TYPECHECK,
    ValidationStage.BUILD: ToolchainAction.BUILD,
    ValidationStage.TEST: ToolchainAction.TEST,
    ValidationStage.SMOKE: ToolchainAction.SMOKE,
}


async def validate_project_profile(
    project_dir: Path,
    profile: FrameworkProfile,
    *,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Run the profile's declared validation commands in the project directory."""
    diagnostics: list[str] = []
    commands = []
    for raw_step in profile.validation_steps:
        try:
            step = ValidationStage(raw_step)
        except ValueError:
            continue
        command = profile.command_for_stage(step)
        if command:
            commands.append((step.value, CommandSpec(
                action=_ACTIONS[step], command=command,
                timeout_seconds=max(1, min(3600, int(timeout_seconds))),
            )))

    runner = ToolchainRunner()
    for step, command_spec in commands:
        try:
            returncode, stdout, stderr = await runner.run(command_spec, project_dir)
        except (OSError, ValueError) as exc:
            return {
                "passed": False,
                "status": "failed",
                "step": step,
                "command": list(command_spec.command),
                "diagnostics": [f"{step} could not start: {exc}"],
            }
        if returncode == 124:
            return {
                "passed": False,
                "status": "timed_out",
                "step": step,
                "command": list(command_spec.command),
                "diagnostics": [f"{step} timed out after {timeout_seconds:g}s"],
            }
        if returncode != 0:
            text = (stderr or stdout)[-4000:]
            diagnostics.append(f"{step} failed: {text}")
            return {
                "passed": False,
                "status": "failed",
                "step": step,
                "command": list(command_spec.command),
                "diagnostics": diagnostics,
                "stdout": stdout[-4000:],
                "stderr": stderr[-4000:],
            }

    return {"passed": True, "status": "completed", "diagnostics": []}


__all__ = [
    "validate_project_profile",
    "validate_workflow_profiles",
    "validation_targets_for_workflow",
]
