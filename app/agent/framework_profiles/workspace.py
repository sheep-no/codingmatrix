"""Workspace-scoped profile documents and conformance probes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner

from . import FrameworkProfile, ProfileScope, ProfileStatus


PROFILE_SCHEMA_VERSION = 1
DEFAULT_CONFORMANCE_CHECKS = ("syntax", "install", "startup", "crud", "persistence")


class WorkspaceProfileDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=PROFILE_SCHEMA_VERSION, ge=1)
    workspace_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    profile: FrameworkProfile
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_scope_and_digest(self) -> "WorkspaceProfileDocument":
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported workspace profile schema version")
        if self.profile.scope is not ProfileScope.WORKSPACE:
            raise ValueError("workspace profile document requires workspace scope")
        if self.profile.status is not ProfileStatus.CUSTOM_PENDING:
            raise ValueError("new workspace profiles must start as custom_pending")
        if self.profile.owner_id != self.owner_id or self.profile.workspace_id != self.workspace_id:
            raise ValueError("workspace profile scope does not match document scope")
        if self.digest != _document_digest(
            self.schema_version, self.workspace_id, self.owner_id, self.profile
        ):
            raise ValueError("workspace profile digest does not match its contents")
        return self

    @classmethod
    def build(
        cls, *, workspace_id: str, owner_id: str, profile: FrameworkProfile
    ) -> "WorkspaceProfileDocument":
        digest = _document_digest(
            PROFILE_SCHEMA_VERSION, workspace_id, owner_id, profile
        )
        return cls(
            schema_version=PROFILE_SCHEMA_VERSION,
            workspace_id=workspace_id,
            owner_id=owner_id,
            profile=profile,
            digest=digest,
        )


class WorkspaceProfileProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    checks: Tuple[str, ...] = ()
    failures: Tuple[str, ...] = ()


def load_workspace_profile(
    path: Path,
    *,
    workspace: Path,
    workspace_id: str,
    owner_id: str,
) -> WorkspaceProfileDocument:
    """Load a signed-by-content JSON profile inside its owning workspace."""
    workspace = workspace.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("workspace profile file must stay inside workspace") from exc
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("workspace profile must be valid UTF-8 JSON") from exc
    document = WorkspaceProfileDocument.model_validate(payload)
    if document.owner_id != owner_id or document.workspace_id != workspace_id:
        raise ValueError("workspace profile cannot be reused across owners or workspaces")
    return document


async def probe_workspace_profile(
    workspace: Path,
    profile: FrameworkProfile,
    *,
    required_checks: Iterable[str] = DEFAULT_CONFORMANCE_CHECKS,
    runner: ToolchainRunner | None = None,
) -> WorkspaceProfileProbeResult:
    """Run finite, allowlisted checks before a custom profile can advance."""
    if profile.scope is not ProfileScope.WORKSPACE:
        raise ValueError("profile probe requires workspace scope")
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError("profile probe workspace must be an existing directory")

    commands = _commands_for_checks(profile)
    completed = []
    failures = []
    executor = runner or ToolchainRunner()
    for check in tuple(dict.fromkeys(required_checks)):
        command = commands.get(check)
        if not command:
            failures.append(f"{check}: probe command is required")
            continue
        if command not in profile.command_allowlist:
            failures.append(f"{check}: probe command is outside command_allowlist")
            continue
        spec = CommandSpec(
            action=_action_for_check(check), command=command,
            timeout_seconds=600 if check == "install" else 120,
        )
        try:
            returncode, stdout, stderr = await executor.run(spec, workspace)
        except (OSError, ValueError) as exc:
            failures.append(f"{check}: could not start: {exc}")
            continue
        if returncode != 0:
            detail = (stderr or stdout)[-2000:]
            failures.append(f"{check}: exit {returncode}: {detail}")
            continue
        completed.append(check)
    return WorkspaceProfileProbeResult(
        passed=not failures and bool(completed),
        checks=tuple(completed), failures=tuple(failures),
    )


def promote_workspace_profile(
    profile: FrameworkProfile,
    result: WorkspaceProfileProbeResult,
    *,
    required_checks: Iterable[str] = DEFAULT_CONFORMANCE_CHECKS,
    target: ProfileStatus = ProfileStatus.EXPERIMENTAL,
) -> FrameworkProfile:
    """Advance a custom profile after its concrete conformance evidence passes."""
    required = set(required_checks)
    if not result.passed or not required.issubset(result.checks):
        raise ValueError("workspace profile requires complete passing conformance checks")
    if target is ProfileStatus.EXPERIMENTAL:
        if profile.status is not ProfileStatus.CUSTOM_PENDING:
            raise ValueError("only custom_pending profiles can become experimental")
    elif target is ProfileStatus.SUPPORTED:
        if profile.status is not ProfileStatus.EXPERIMENTAL:
            raise ValueError("only experimental profiles can become supported")
    else:
        raise ValueError("workspace profile promotion target is unsupported")
    return profile.model_copy(update={"status": target})


def _commands_for_checks(profile: FrameworkProfile) -> Mapping[str, Tuple[str, ...]]:
    return {
        "syntax": profile.probe_commands.get("syntax", profile.build_command),
        "install": profile.probe_commands.get("install", profile.install_command),
        "startup": profile.probe_commands.get("startup", profile.smoke_command),
        "crud": profile.probe_commands.get("crud", ()),
        "persistence": profile.probe_commands.get("persistence", ()),
        **profile.probe_commands,
    }


def _action_for_check(check: str) -> ToolchainAction:
    return {
        "syntax": ToolchainAction.BUILD,
        "install": ToolchainAction.INSTALL,
        "startup": ToolchainAction.SMOKE,
        "crud": ToolchainAction.TEST,
        "persistence": ToolchainAction.TEST,
    }.get(check, ToolchainAction.TEST)


def _document_digest(
    schema_version: int,
    workspace_id: str,
    owner_id: str,
    profile: FrameworkProfile,
) -> str:
    payload = {
        "schema_version": schema_version,
        "workspace_id": workspace_id,
        "owner_id": owner_id,
        "profile": profile.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "DEFAULT_CONFORMANCE_CHECKS", "PROFILE_SCHEMA_VERSION",
    "WorkspaceProfileDocument", "WorkspaceProfileProbeResult",
    "load_workspace_profile", "probe_workspace_profile",
    "promote_workspace_profile",
]
