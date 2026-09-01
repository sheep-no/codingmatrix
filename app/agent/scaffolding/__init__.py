"""Official scaffold command contracts without implicit command execution."""

from typing import Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.agent.toolchain import CommandSpec, ToolchainAction


class ScaffoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    framework: str = Field(min_length=1)
    language: str = Field(min_length=1)
    target_dir: str = Field(min_length=1)
    command: Tuple[str, ...] = Field(min_length=1)

    def as_command_spec(self) -> CommandSpec:
        return CommandSpec(action=ToolchainAction.INSTALL, command=self.command)


def official_scaffold_request(language: str, framework: str, target_dir: str) -> ScaffoldRequest:
    """Return a known CLI invocation for supported framework baselines."""
    key = (language.lower(), framework.lower())
    commands = {
        ("typescript", "express"): ("npx", "express-generator", target_dir),
        ("javascript", "express"): ("npx", "express-generator", target_dir),
        ("typescript", "nestjs"): ("npx", "@nestjs/cli", "new", target_dir),
    }
    command = commands.get(key)
    if command is None:
        raise LookupError(f"official scaffold not found: {language}/{framework}")
    return ScaffoldRequest(
        framework=framework,
        language=language,
        target_dir=target_dir,
        command=command,
    )


__all__ = ["ScaffoldRequest", "official_scaffold_request"]
