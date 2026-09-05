"""Executable validation for declarative framework profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner

from . import FrameworkProfile, ValidationStage


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
            }

    return {"passed": True, "status": "completed", "diagnostics": []}


__all__ = ["validate_project_profile"]
