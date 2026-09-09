"""Translate capability validation steps into safe executable checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainProbePlan, ToolchainRunner
from app.agent.validation_report import ValidationCategory, ValidationFinding, ValidationReport


@dataclass(frozen=True)
class ValidationPlan:
    commands: Tuple[CommandSpec, ...]
    unsupported_steps: Tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.unsupported_steps


@dataclass(frozen=True)
class ValidationResult:
    command: CommandSpec
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class ValidationCoordinator:
    """Build validation commands while preserving explicit capability steps."""

    _STATIC_COMMANDS = {
        "syntax": CommandSpec(action=ToolchainAction.TEST, command=("python3", "-m", "compileall", "-q", ".")),
    }

    def __init__(self, runner: ToolchainRunner | None = None) -> None:
        self.runner = runner or ToolchainRunner()

    def build_plan(
        self,
        profile_context: Mapping[str, object],
        toolchain: ToolchainProbePlan,
    ) -> ValidationPlan:
        policy = profile_context.get("capability_policy", {})
        steps = policy.get("validation_steps", ()) if isinstance(policy, Mapping) else ()
        commands = []
        unsupported = []
        for step in steps:
            name = str(step)
            command = self._STATIC_COMMANDS.get(name)
            if command is None and name in {
                "install", "lint", "typecheck", "build", "test", "tests",
                "unit_tests", "command_test", "smoke", "smoke_test",
            }:
                action = {
                    "install": ToolchainAction.INSTALL,
                    "lint": ToolchainAction.LINT,
                    "typecheck": ToolchainAction.TYPECHECK,
                    "build": ToolchainAction.BUILD,
                    "test": ToolchainAction.TEST,
                    "tests": ToolchainAction.TEST,
                    "unit_tests": ToolchainAction.TEST,
                    "command_test": ToolchainAction.TEST,
                    "smoke": ToolchainAction.SMOKE,
                    "smoke_test": ToolchainAction.SMOKE,
                }[name]
                command = toolchain.for_action(action)
            if command is None:
                unsupported.append(name)
                continue
            if command not in commands:
                commands.append(command)
        return ValidationPlan(tuple(commands), tuple(unsupported))

    async def execute(
        self,
        plan: ValidationPlan,
        workspace: Path,
    ) -> Tuple[ValidationResult, ...]:
        """Execute approved commands without invoking a shell."""
        results = []
        for command in plan.commands:
            try:
                returncode, stdout, stderr = await self.runner.run(command, workspace)
                results.append(ValidationResult(
                    command, None if returncode == 124 else returncode,
                    stdout, stderr, returncode == 124,
                ))
            except (FileNotFoundError, ValueError) as exc:
                results.append(ValidationResult(command, 127, "", str(exc)))
        return tuple(results)

    def to_report(
        self,
        plan: ValidationPlan,
        results: Tuple[ValidationResult, ...],
        *,
        context_hash: str,
    ) -> ValidationReport:
        findings = []
        for step in plan.unsupported_steps:
            findings.append(ValidationFinding(
                category=ValidationCategory.UNKNOWN,
                message=f"unsupported validation step: {step}",
                scope="local_runtime",
                context_hash=context_hash,
            ))
        for result in results:
            if result.passed:
                continue
            message = "validation command timed out" if result.timed_out else (
                result.stderr.strip() or f"validation command exited with code {result.returncode}"
            )
            findings.append(ValidationFinding(
                category=self._category_for_action(result.command.action),
                message=message,
                scope="local_runtime",
                code=str(result.returncode) if result.returncode is not None else "timeout",
                context_hash=context_hash,
            ))
        return ValidationReport.create(findings, source="toolchain")

    @staticmethod
    def _category_for_action(action: ToolchainAction) -> ValidationCategory:
        return {
            ToolchainAction.INSTALL: ValidationCategory.DEPENDENCY,
            ToolchainAction.LINT: ValidationCategory.TYPE,
            ToolchainAction.TYPECHECK: ValidationCategory.TYPE,
            ToolchainAction.BUILD: ValidationCategory.FRAMEWORK,
            ToolchainAction.TEST: ValidationCategory.TEST,
            ToolchainAction.START: ValidationCategory.FRAMEWORK,
            ToolchainAction.SMOKE: ValidationCategory.FRAMEWORK,
            ToolchainAction.HEALTH: ValidationCategory.FRAMEWORK,
        }.get(action, ValidationCategory.UNKNOWN)


__all__ = ["ValidationCoordinator", "ValidationPlan", "ValidationResult"]
