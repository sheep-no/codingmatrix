"""Bridge framework profiles into the technology-neutral control plane."""

from __future__ import annotations

from typing import Mapping

from ..code_synthesis_contracts import ProjectModel, ValidationProfile
from ..framework_profiles import FrameworkProfile, ValidationStage
from ..toolchain import CommandSpec, ToolchainAction, ToolchainProbePlan
from ..validation_coordinator import ValidationCoordinator, ValidationPlan


_STAGE_ACTIONS = {
    ValidationStage.INSTALL: ToolchainAction.INSTALL,
    ValidationStage.LINT: ToolchainAction.LINT,
    ValidationStage.TYPECHECK: ToolchainAction.TYPECHECK,
    ValidationStage.BUILD: ToolchainAction.BUILD,
    ValidationStage.TEST: ToolchainAction.TEST,
    ValidationStage.SMOKE: ToolchainAction.SMOKE,
}


def project_model_from_profile(
    profile: FrameworkProfile,
    *,
    modules: tuple[str, ...] = (),
    targets: tuple[str, ...] = (),
    entrypoints: tuple[str, ...] = (),
    generated_zones: tuple[str, ...] = (),
) -> ProjectModel:
    """Convert a validated profile into facts understood by StrategyRouter."""
    return ProjectModel(
        language=profile.language,
        framework=profile.name,
        runtime=profile.version,
        modules=modules,
        targets=targets,
        entrypoints=entrypoints,
        generated_zones=generated_zones,
        capabilities=profile.capabilities,
    )


def validation_profile_from_framework(profile: FrameworkProfile) -> ValidationProfile:
    """Create the constrained validation contract for a framework profile."""
    return ValidationProfile(
        name=f"{profile.name}@{profile.version}",
        required_scopes=tuple(profile.validation_steps),
        commands=tuple(
            profile.command_for_stage(stage)
            for stage in (ValidationStage(item) for item in profile.validation_steps)
        ),
    )


def validation_plan_from_framework(
    profile: FrameworkProfile,
    coordinator: ValidationCoordinator | None = None,
) -> ValidationPlan:
    """Project profile commands through the existing safe validation coordinator."""
    commands = []
    for raw_stage in profile.validation_steps:
        stage = ValidationStage(raw_stage)
        command = profile.command_for_stage(stage)
        if command:
            commands.append(CommandSpec(action=_STAGE_ACTIONS[stage], command=command))
    toolchain = ToolchainProbePlan(
        workspace="profile",
        commands=tuple(commands),
        evidence=(f"framework-profile:{profile.name}",),
    )
    context: Mapping[str, object] = {
        "capability_policy": {
            "validation_steps": tuple(profile.validation_steps),
        }
    }
    return (coordinator or ValidationCoordinator()).build_plan(context, toolchain)


__all__ = [
    "project_model_from_profile",
    "validation_plan_from_framework",
    "validation_profile_from_framework",
]
