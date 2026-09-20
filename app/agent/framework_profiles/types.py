"""Shared framework profile types used by the package, workspace, and validation.

These definitions live in a leaf module so the package initializer, the
workspace document layer, and the validation layer can all depend on them
without importing each other during initialization.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.capabilities import CapabilitySet


class ProfileStatus(str, Enum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    CUSTOM_PENDING = "custom_pending"


class ProfileScope(str, Enum):
    SYSTEM = "system"
    WORKSPACE = "workspace"


class ValidationStage(str, Enum):
    INSTALL = "install"
    LINT = "lint"
    TYPECHECK = "typecheck"
    BUILD = "build"
    TEST = "test"
    SMOKE = "smoke"


class FrameworkProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    language: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: ProfileStatus
    capabilities: CapabilitySet
    dependencies: Tuple[str, ...] = ()
    install_command: Tuple[str, ...] = ()
    lint_command: Tuple[str, ...] = ()
    typecheck_command: Tuple[str, ...] = ()
    build_command: Tuple[str, ...] = ()
    test_command: Tuple[str, ...] = ()
    smoke_command: Tuple[str, ...] = ()
    start_command: Tuple[str, ...] = ()
    health_path: str = "/health"
    scope: ProfileScope = ProfileScope.SYSTEM
    owner_id: str | None = None
    workspace_id: str | None = None
    command_allowlist: Tuple[Tuple[str, ...], ...] = ()
    dependency_allowlist: Tuple[str, ...] = ()
    probe_commands: Mapping[str, Tuple[str, ...]] = Field(default_factory=dict)
    file_role_patterns: Mapping[str, Tuple[str, ...]] = Field(default_factory=dict)
    contract_rules: Mapping[str, Any] = Field(default_factory=dict)
    validation_steps: Tuple[str, ...] = ()
    default_for_language: bool = False

    @model_validator(mode="after")
    def validate_workspace_contract(self) -> "FrameworkProfile":
        command_fields = (
            self.install_command, self.lint_command, self.typecheck_command,
            self.build_command, self.test_command, self.smoke_command,
            self.start_command,
        )
        for command in command_fields:
            if command:
                from app.agent.toolchain import CommandSpec

                CommandSpec.validate_command(command)
        for raw_step in self.validation_steps:
            try:
                stage = ValidationStage(raw_step)
            except ValueError as exc:
                raise ValueError(f"unsupported validation step: {raw_step}") from exc
            if not self.command_for_stage(stage):
                raise ValueError(f"validation step requires a command: {stage.value}")
        if self.scope is ProfileScope.WORKSPACE:
            if not self.owner_id:
                raise ValueError("workspace profile requires owner_id")
            if not self.workspace_id:
                raise ValueError("workspace profile requires workspace_id")
            if any(not command for command in self.command_allowlist):
                raise ValueError("workspace command allowlist cannot contain empty commands")
            if any(dependency not in self.dependency_allowlist for dependency in self.dependencies):
                raise ValueError("profile dependencies must be in dependency_allowlist")
            declared_commands = tuple(command for command in command_fields if command)
            declared_commands += tuple(self.probe_commands.values())
            if any(command not in self.command_allowlist for command in declared_commands):
                raise ValueError("workspace profile commands must be in command_allowlist")
            for command in self.probe_commands.values():
                from app.agent.toolchain import CommandSpec

                CommandSpec.validate_command(command)
            for command in declared_commands:
                _validate_workspace_command(command)
        return self

    def command_for_stage(self, stage: str | ValidationStage) -> Tuple[str, ...]:
        name = ValidationStage(stage)
        return {
            ValidationStage.INSTALL: self.install_command,
            ValidationStage.LINT: self.lint_command,
            ValidationStage.TYPECHECK: self.typecheck_command,
            ValidationStage.BUILD: self.build_command,
            ValidationStage.TEST: self.test_command,
            ValidationStage.SMOKE: self.smoke_command,
        }[name]

    @classmethod
    def custom_pending(
        cls, *, name: str, language: str, owner_id: str,
        workspace_id: str | None = None, version: str = "1"
    ) -> "FrameworkProfile":
        if not owner_id.strip():
            raise ValueError("custom profile requires owner_id")
        return cls(
            name=name,
            language=language,
            version=version,
            status=ProfileStatus.CUSTOM_PENDING,
            capabilities=CapabilitySet(),
            scope=ProfileScope.WORKSPACE,
            owner_id=owner_id,
            workspace_id=workspace_id or owner_id,
            command_allowlist=(),
            dependency_allowlist=(),
        )


def _validate_workspace_command(command: Tuple[str, ...]) -> None:
    from pathlib import PurePosixPath

    from app.agent.toolchain import DEFAULT_ALLOWED_EXECUTABLES

    executable = command[0]
    if executable not in DEFAULT_ALLOWED_EXECUTABLES and executable not in {"./gradlew", "./mvnw"}:
        raise ValueError(f"workspace profile executable is not allowlisted: {executable}")
    if executable in {"python", "python3"} and "-c" in command[1:]:
        raise ValueError("workspace profiles cannot execute inline interpreter code")
    if executable == "node" and any(value in {"-e", "--eval"} for value in command[1:]):
        raise ValueError("workspace profiles cannot execute inline interpreter code")
    for argument in command[1:]:
        normalized = argument.replace("\\", "/")
        path_value = normalized.split("=", 1)[-1]
        if path_value.startswith("/") or ".." in PurePosixPath(path_value).parts:
            raise ValueError("workspace profile command arguments must stay inside workspace")
