"""Safe toolchain command contracts and workspace detection."""

from enum import Enum
from pathlib import Path
from typing import Iterable, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolchainAction(str, Enum):
    INSTALL = "install"
    BUILD = "build"
    FORMAT = "format"
    LINT = "lint"
    TEST = "test"
    START = "start"
    HEALTH = "health"


class CommandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: ToolchainAction
    command: Tuple[str, ...] = Field(min_length=1)
    shell: bool = False
    timeout_seconds: int = Field(default=120, ge=1, le=3600)

    @model_validator(mode="before")
    @classmethod
    def validate_command_parts(cls, values):
        if isinstance(values, dict) and "command" in values:
            values = dict(values)
            values["command"] = cls.validate_command(values["command"])
        return values

    @staticmethod
    def validate_command(command: Iterable[str]) -> Tuple[str, ...]:
        values = tuple(command)
        if not values or any(not isinstance(part, str) or not part.strip() for part in values):
            raise ValueError("toolchain commands must contain non-empty arguments")
        if any(any(token in part for token in (";", "&&", "||", "|", ">", "<", "`", "$(")) for part in values):
            raise ValueError("shell operators are forbidden in toolchain commands")
        if values[0] in {"sh", "bash", "zsh", "cmd", "powershell", "pwsh"}:
            raise ValueError("shell interpreters are forbidden in toolchain commands")
        return values


class ToolchainProbePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace: str = Field(min_length=1)
    commands: Tuple[CommandSpec, ...] = ()
    status: str = "detected"

    def for_action(self, action: ToolchainAction) -> CommandSpec | None:
        return next((item for item in self.commands if item.action is action), None)


def detect_toolchain(workspace: Path) -> ToolchainProbePlan:
    """Detect conservative commands from standard project manifests."""
    commands = []
    if (workspace / "package.json").exists():
        commands.extend([
            CommandSpec(action=ToolchainAction.INSTALL, command=("npm", "install")),
            CommandSpec(action=ToolchainAction.TEST, command=("npm", "test")),
        ])
    elif (workspace / "requirements.txt").exists() or (workspace / "pyproject.toml").exists():
        commands.extend([
            CommandSpec(action=ToolchainAction.INSTALL, command=("python3", "-m", "pip", "install", "-r", "requirements.txt")),
            CommandSpec(action=ToolchainAction.TEST, command=("python3", "-m", "pytest")),
        ])
    return ToolchainProbePlan(workspace=str(workspace), commands=tuple(commands), status="detected" if commands else "unsupported")


__all__ = ["CommandSpec", "ToolchainAction", "ToolchainProbePlan", "detect_toolchain"]
