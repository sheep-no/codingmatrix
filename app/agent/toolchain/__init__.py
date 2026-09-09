"""Safe toolchain command contracts and workspace detection."""

import asyncio
import json
import os
import signal
import tomllib
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_ALLOWED_EXECUTABLES = (
    "python", "python3", "node", "npx", "npm", "go", "cargo", "gofmt",
    "rustc", "javac", "java", "mvn", "gradle", "ruby", "dotnet", "tsc",
)


class ToolchainAction(str, Enum):
    INSPECT = "inspect"
    INSTALL = "install"
    BUILD = "build"
    FORMAT = "format"
    LINT = "lint"
    TYPECHECK = "typecheck"
    TEST = "test"
    START = "start"
    SMOKE = "smoke"
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
        if isinstance(values, dict) and values.get("shell"):
            raise ValueError("toolchain commands require shell=false")
        if isinstance(values, dict) and "command" in values:
            values = dict(values)
            values["command"] = cls.validate_command(values["command"])
        return values

    @staticmethod
    def validate_command(command: Iterable[str]) -> Tuple[str, ...]:
        values = tuple(command)
        if not values or any(not isinstance(part, str) or not part.strip() for part in values):
            raise ValueError("toolchain commands must contain non-empty arguments")
        if any(part.strip() in {";", "&&", "||", "|", ">", "<", "`"} for part in values):
            raise ValueError("shell operators are forbidden in toolchain commands")
        if values[0] in {"sh", "bash", "zsh", "cmd", "powershell", "pwsh"}:
            raise ValueError("shell interpreters are forbidden in toolchain commands")
        return values


class ToolchainProbePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace: str = Field(min_length=1)
    commands: Tuple[CommandSpec, ...] = ()
    status: str = "detected"
    evidence: Tuple[str, ...] = ()

    def for_action(self, action: ToolchainAction) -> CommandSpec | None:
        return next((item for item in self.commands if item.action is action), None)


class ToolchainRunner:
    """以参数数组执行受控只读命令，供语言接口探针复用。"""

    def __init__(
        self,
        *,
        output_limit: int = 64_000,
        allowed_executables: Iterable[str] = DEFAULT_ALLOWED_EXECUTABLES,
    ) -> None:
        if output_limit < 1:
            raise ValueError("output_limit must be positive")
        self.output_limit = output_limit
        self.allowed_executables = frozenset(allowed_executables)

    async def run(self, spec: CommandSpec, workspace: Path) -> Tuple[int, str, str]:
        if spec.shell:
            raise ValueError("toolchain runner requires shell=false")
        workspace = workspace.resolve()
        if not workspace.is_dir():
            raise ValueError("toolchain workspace must be an existing directory")
        executable = spec.command[0]
        is_workspace_wrapper = executable in {"./gradlew", "./mvnw"}
        if executable not in self.allowed_executables and not is_workspace_wrapper:
            raise ValueError(f"executable is not allowlisted: {spec.command[0]}")
        if is_workspace_wrapper:
            wrapper = (workspace / executable.removeprefix("./")).resolve()
            try:
                wrapper.relative_to(workspace.resolve())
            except ValueError as exc:
                raise ValueError("toolchain wrapper must stay inside workspace") from exc
            if not wrapper.is_file():
                raise FileNotFoundError(f"workspace wrapper not found: {executable}")
        environment = os.environ.copy()
        # A host regular package can shadow a project's namespace package even
        # when cwd is correct. Do not inherit the host's Python search path.
        environment["PYTHONPATH"] = str(workspace)
        process = await asyncio.create_subprocess_exec(
            *spec.command,
            cwd=str(workspace),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        stdout_task = asyncio.create_task(self._read_limited(process.stdout))
        stderr_task = asyncio.create_task(self._read_limited(process.stderr))
        try:
            await asyncio.wait_for(process.wait(), timeout=spec.timeout_seconds)
        except asyncio.TimeoutError:
            self._kill_process_group(process)
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task)
            return 124, "", "toolchain command timed out"
        except asyncio.CancelledError:
            self._kill_process_group(process)
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task)
            raise
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def _read_limited(self, stream: asyncio.StreamReader | None) -> bytes:
        if stream is None:
            return b""
        chunks = bytearray()
        while True:
            chunk = await stream.read(8192)
            if not chunk:
                break
            remaining = self.output_limit - len(chunks)
            if remaining > 0:
                chunks.extend(chunk[:remaining])
        return bytes(chunks)

    @staticmethod
    def _kill_process_group(process: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def detect_toolchain(workspace: Path) -> ToolchainProbePlan:
    """Detect conservative commands from standard project manifests."""
    workspace = workspace.resolve()
    commands: list[CommandSpec] = []
    evidence: list[str] = []

    package_json = workspace / "package.json"
    if package_json.is_file():
        package = _read_json_object(package_json)
        scripts = package.get("scripts", {})
        scripts = scripts if isinstance(scripts, Mapping) else {}
        evidence.append("package.json")
        install = ("npm", "ci") if (workspace / "package-lock.json").is_file() else ("npm", "install")
        _append_command(commands, ToolchainAction.INSTALL, install, timeout_seconds=600)
        for action, names in (
            (ToolchainAction.FORMAT, ("format:check", "format")),
            (ToolchainAction.LINT, ("lint",)),
            (ToolchainAction.TYPECHECK, ("typecheck", "type-check")),
            (ToolchainAction.BUILD, ("build",)),
            (ToolchainAction.TEST, ("test",)),
            (ToolchainAction.START, ("start", "dev")),
            (ToolchainAction.SMOKE, ("smoke",)),
            (ToolchainAction.HEALTH, ("health",)),
        ):
            script = next((name for name in names if isinstance(scripts.get(name), str)), None)
            if script:
                _append_command(commands, action, ("npm", "run", script))

    requirements = workspace / "requirements.txt"
    pyproject = workspace / "pyproject.toml"
    if requirements.is_file() or pyproject.is_file():
        evidence.append("requirements.txt" if requirements.is_file() else "pyproject.toml")
        install = (
            ("python3", "-m", "pip", "install", "-r", "requirements.txt")
            if requirements.is_file()
            else ("python3", "-m", "pip", "install", ".")
        )
        _append_command(commands, ToolchainAction.INSTALL, install, timeout_seconds=600)
        _append_command(commands, ToolchainAction.BUILD, ("python3", "-m", "compileall", "."))
        pyproject_data = _read_toml_object(pyproject) if pyproject.is_file() else {}
        tool_config = pyproject_data.get("tool", {})
        tool_config = tool_config if isinstance(tool_config, Mapping) else {}
        if "ruff" in tool_config:
            _append_command(commands, ToolchainAction.LINT, ("python3", "-m", "ruff", "check", "."))
        if "mypy" in tool_config:
            _append_command(commands, ToolchainAction.TYPECHECK, ("python3", "-m", "mypy", "."))
        _append_command(commands, ToolchainAction.TEST, ("python3", "-m", "pytest"))

    if (workspace / "go.mod").is_file():
        evidence.append("go.mod")
        _append_command(commands, ToolchainAction.INSTALL, ("go", "mod", "download"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.FORMAT, ("gofmt", "-l", "."))
        _append_command(commands, ToolchainAction.LINT, ("go", "vet", "./..."))
        _append_command(commands, ToolchainAction.BUILD, ("go", "build", "./..."))
        _append_command(commands, ToolchainAction.TEST, ("go", "test", "./..."))

    if (workspace / "Cargo.toml").is_file():
        evidence.append("Cargo.toml")
        _append_command(commands, ToolchainAction.INSTALL, ("cargo", "fetch"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.FORMAT, ("cargo", "fmt", "--", "--check"))
        _append_command(commands, ToolchainAction.LINT, ("cargo", "clippy", "--all-targets", "--", "-D", "warnings"))
        _append_command(commands, ToolchainAction.TYPECHECK, ("cargo", "check"))
        _append_command(commands, ToolchainAction.BUILD, ("cargo", "build"))
        _append_command(commands, ToolchainAction.TEST, ("cargo", "test"))

    if (workspace / "pom.xml").is_file():
        evidence.append("pom.xml")
        executable = "./mvnw" if (workspace / "mvnw").is_file() else "mvn"
        _append_command(commands, ToolchainAction.INSTALL, (executable, "dependency:go-offline"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.BUILD, (executable, "-q", "-DskipTests", "package"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.TEST, (executable, "-q", "test"), timeout_seconds=600)

    gradle_manifest = next(
        (workspace / name for name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts") if (workspace / name).is_file()),
        None,
    )
    if gradle_manifest is not None:
        evidence.append(gradle_manifest.name)
        executable = "./gradlew" if (workspace / "gradlew").is_file() else "gradle"
        _append_command(commands, ToolchainAction.INSTALL, (executable, "dependencies"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.TYPECHECK, (executable, "compileJava"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.BUILD, (executable, "build", "-x", "test"), timeout_seconds=600)
        _append_command(commands, ToolchainAction.TEST, (executable, "test"), timeout_seconds=600)

    return ToolchainProbePlan(
        workspace=str(workspace), commands=tuple(commands),
        status="detected" if commands else "unsupported", evidence=tuple(evidence),
    )


def _append_command(
    commands: list[CommandSpec],
    action: ToolchainAction,
    command: Tuple[str, ...],
    *,
    timeout_seconds: int = 120,
) -> None:
    if any(item.action is action for item in commands):
        return
    commands.append(CommandSpec(action=action, command=command, timeout_seconds=timeout_seconds))


def _read_json_object(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON manifest: {path.name}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON manifest must contain an object: {path.name}")
    return value


def _read_toml_object(path: Path) -> Mapping[str, object]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid TOML manifest: {path.name}") from exc
    return value


__all__ = [
    "CommandSpec", "DEFAULT_ALLOWED_EXECUTABLES", "ToolchainAction",
    "ToolchainProbePlan", "ToolchainRunner", "detect_toolchain",
]
