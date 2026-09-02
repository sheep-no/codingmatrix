"""Translate capability validation steps into safe executable checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainProbePlan
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
            if command is None and name in {"tests", "unit_tests", "command_test", "smoke_test"}:
                command = toolchain.for_action(ToolchainAction.TEST)
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
                process = await asyncio.create_subprocess_exec(
                    *command.command,
                    cwd=workspace,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=command.timeout_seconds
                    )
                    results.append(ValidationResult(
                        command, process.returncode, stdout.decode(errors="replace"),
                        stderr.decode(errors="replace"),
                    ))
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()
                    results.append(ValidationResult(command, None, "", "", True))
            except FileNotFoundError as exc:
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
                category=ValidationCategory.TEST,
                message=message,
                scope="local_runtime",
                code=str(result.returncode) if result.returncode is not None else "timeout",
                context_hash=context_hash,
            ))
        return ValidationReport.create(findings, source="toolchain")


__all__ = ["ValidationCoordinator", "ValidationPlan", "ValidationResult"]
