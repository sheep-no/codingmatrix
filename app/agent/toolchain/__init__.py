"""Safe toolchain command contracts and workspace detection."""

from enum import Enum
import asyncio
from pathlib import Path
from typing import Iterable, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolchainAction(str, Enum):
    INSPECT = "inspect"
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


class ToolchainRunner:
    """以参数数组执行受控只读命令，供语言接口探针复用。"""

    def __init__(
        self,
        *,
        output_limit: int = 64_000,
        allowed_executables: Iterable[str] = (
            "python", "python3", "node", "npx", "npm", "go", "cargo",
            "rustc", "javac", "java", "ruby", "dotnet", "tsc",
        ),
    ) -> None:
        if output_limit < 1:
            raise ValueError("output_limit must be positive")
        self.output_limit = output_limit
        self.allowed_executables = frozenset(allowed_executables)

    async def run(self, spec: CommandSpec, workspace: Path) -> Tuple[int, str, str]:
        if spec.shell:
            raise ValueError("toolchain runner requires shell=false")
        if spec.command[0] not in self.allowed_executables:
            raise ValueError(f"executable is not allowlisted: {spec.command[0]}")
        process = await asyncio.create_subprocess_exec(
            *spec.command,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=spec.timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return 124, "", "toolchain command timed out"
        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace")[: self.output_limit],
            stderr.decode("utf-8", errors="replace")[: self.output_limit],
        )


def detect_toolchain(workspace: Path) -> ToolchainProbePlan:
    """Detect conservative commands from standard project manifests."""
    commands = []
    if (workspace / "package.json").exists():
        commands.extend([
            CommandSpec(action=ToolchainAction.INSTALL, command=("npm", "install")),
            CommandSpec(action=ToolchainAction.TEST, command=("npm", "test")),
        ])
    elif (workspace / "requirements.txt").exists():
        commands.extend([
            CommandSpec(action=ToolchainAction.INSTALL, command=("python3", "-m", "pip", "install", "-r", "requirements.txt")),
            CommandSpec(action=ToolchainAction.TEST, command=("python3", "-m", "pytest")),
        ])
    elif (workspace / "pyproject.toml").exists():
        commands.extend([
            CommandSpec(action=ToolchainAction.INSTALL, command=("python3", "-m", "pip", "install", ".")),
            CommandSpec(action=ToolchainAction.TEST, command=("python3", "-m", "pytest")),
        ])
    return ToolchainProbePlan(workspace=str(workspace), commands=tuple(commands), status="detected" if commands else "unsupported")


__all__ = ["CommandSpec", "ToolchainAction", "ToolchainProbePlan", "ToolchainRunner", "detect_toolchain"]
