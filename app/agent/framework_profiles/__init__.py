"""Versioned framework profiles used by planning and validation."""

from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.capabilities import Capability, CapabilitySet


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


class ProfileRegistry:
    """Resolve profiles by language, framework name, and version."""

    def __init__(self, profiles: Iterable[FrameworkProfile] = ()) -> None:
        self._profiles: Dict[tuple[str, str, str], FrameworkProfile] = {}
        self._workspace_profiles: Dict[tuple[str, str, str, str, str], FrameworkProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: FrameworkProfile) -> None:
        key = (profile.language.lower(), profile.name.lower(), profile.version)
        if profile.scope is ProfileScope.WORKSPACE and not profile.owner_id:
            raise ValueError("workspace profile requires owner_id")
        if profile.scope is ProfileScope.WORKSPACE:
            workspace_key = (
                profile.owner_id or "", profile.workspace_id or "",
                profile.language.lower(), profile.name.lower(), profile.version,
            )
            self._workspace_profiles[workspace_key] = profile
        else:
            self._profiles[key] = profile

    def register_workspace(
        self, profile: FrameworkProfile, owner_id: str, workspace_id: str | None = None
    ) -> None:
        expected_workspace = workspace_id or profile.workspace_id
        if (
            profile.scope is not ProfileScope.WORKSPACE
            or profile.owner_id != owner_id
            or profile.workspace_id != expected_workspace
        ):
            raise ValueError("workspace profile owner does not match registration scope")
        self.register(profile)

    def validate_workspace_command(self, profile: FrameworkProfile, command: Tuple[str, ...]) -> bool:
        if profile.scope is not ProfileScope.WORKSPACE:
            return False
        return command in profile.command_allowlist

    def get(self, language: str, framework: str, version: str = "latest") -> FrameworkProfile | None:
        language_key = {"js": "typescript", "javascript": "typescript"}.get(
            language.lower(), language.lower()
        )
        framework_key = framework.lower()
        exact = self._profiles.get((language_key, framework_key, version))
        if exact is not None:
            return exact
        candidates = [
            profile for (item_language, item_framework, _), profile in self._profiles.items()
            if item_language == language_key and item_framework == framework_key
            and profile.scope is ProfileScope.SYSTEM
            and (version == "latest" or profile.version == version)
        ]
        return candidates[0] if candidates else None

    def get_workspace(
        self, language: str, framework: str, *, owner_id: str,
        workspace_id: str, version: str = "latest",
    ) -> FrameworkProfile | None:
        language_key = {"js": "typescript", "javascript": "typescript"}.get(
            language.lower(), language.lower()
        )
        prefix = (owner_id, workspace_id, language_key, framework.lower())
        if version != "latest":
            return self._workspace_profiles.get((*prefix, version))
        candidates = [
            profile for key, profile in self._workspace_profiles.items()
            if key[:4] == prefix
        ]
        return candidates[0] if len(candidates) == 1 else None

    def require(self, language: str, framework: str, version: str = "latest") -> FrameworkProfile:
        profile = self.get(language, framework, version)
        if profile is None:
            raise LookupError(f"framework profile not found: {language}/{framework}/{version}")
        return profile

    def validation_profile(self, language: str, framework: str = "") -> FrameworkProfile | None:
        """Resolve the profile that declares executable project validation."""
        if framework:
            profile = self.get(language, framework)
            if profile is not None and profile.validation_steps:
                return profile
        language_key = {"js": "typescript", "javascript": "typescript"}.get(
            language.lower(), language.lower()
        )
        candidates = [
            profile for (item_language, _, _), profile in self._profiles.items()
            if item_language == language_key
            and profile.scope is ProfileScope.SYSTEM
            and profile.validation_steps
        ]
        defaults = [profile for profile in candidates if profile.default_for_language]
        if len(defaults) == 1:
            return defaults[0]
        return candidates[0] if len(candidates) == 1 else None

    def all(self) -> Tuple[FrameworkProfile, ...]:
        return tuple((*self._profiles.values(), *self._workspace_profiles.values()))


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


def default_profile_registry() -> ProfileRegistry:
    common = (Capability.HTTP_API, Capability.DATABASE, Capability.TEST_CLIENT)
    return ProfileRegistry([
        FrameworkProfile(
            name="fastapi", language="python", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.DEPENDENCY_INJECTION, Capability.MIGRATIONS)),
            dependencies=("fastapi", "uvicorn"), install_command=("python3", "-m", "pip", "install", "-r", "requirements.txt"),
            build_command=("python3", "-m", "compileall", "."),
            test_command=("python3", "-m", "pytest"), start_command=("uvicorn", "app.main:app"),
            validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="flask", language="python", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.MIGRATIONS)),
            dependencies=("flask",), install_command=("python3", "-m", "pip", "install", "-r", "requirements.txt"),
            build_command=("python3", "-m", "compileall", "."),
            test_command=("python3", "-m", "pytest"), start_command=("flask", "run"),
            validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="django", language="python", version="latest", status=ProfileStatus.EXPERIMENTAL,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.MIGRATIONS)),
            dependencies=("django",), install_command=("python3", "-m", "pip", "install", "-r", "requirements.txt"),
            build_command=("python3", "-m", "compileall", "."),
            test_command=("python3", "-m", "pytest"),
            smoke_command=("python3", "manage.py", "check"),
            start_command=("python3", "manage.py", "runserver"),
            validation_steps=("build", "test", "smoke"),
        ),
        FrameworkProfile(
            name="stdlib-cli", language="python", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((Capability.COMMAND_LINE, Capability.TEST_CLIENT)),
            build_command=("python3", "-m", "compileall", "."),
            test_command=("python3", "-m", "pytest"),
            validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="express", language="typescript", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.AUTHENTICATION, Capability.WEBSOCKET)),
            dependencies=("express",), install_command=("npm", "install"),
            build_command=("npm", "run", "build"), test_command=("npm", "test"),
            start_command=("npm", "start"), validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="nestjs", language="typescript", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.WEBSOCKET, Capability.DEPENDENCY_INJECTION, Capability.MIGRATIONS)),
            dependencies=("@nestjs/common",), install_command=("npm", "install"),
            build_command=("npm", "run", "build"), test_command=("npm", "test"),
            start_command=("npm", "run", "start"), validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="react-vite", language="typescript", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((Capability.FRONTEND_UI, Capability.TEST_CLIENT)),
            dependencies=("react", "vite"), install_command=("npm", "ci"),
            lint_command=("npm", "run", "lint"), typecheck_command=("npm", "run", "typecheck"),
            build_command=("npm", "run", "build"), test_command=("npm", "test"),
            smoke_command=("npm", "run", "preview", "--", "--host", "127.0.0.1"),
            start_command=("npm", "run", "dev"), health_path="/",
            validation_steps=("lint", "typecheck", "build", "test"),
        ),
        FrameworkProfile(
            name="nextjs", language="typescript", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((Capability.FRONTEND_UI, Capability.HTTP_API, Capability.TEST_CLIENT)),
            dependencies=("next", "react"), install_command=("npm", "ci"),
            lint_command=("npm", "run", "lint"), typecheck_command=("npm", "run", "typecheck"),
            build_command=("npm", "run", "build"), test_command=("npm", "test"),
            smoke_command=("npm", "run", "start"), start_command=("npm", "run", "dev"),
            health_path="/", validation_steps=("lint", "typecheck", "build", "test"),
        ),
        FrameworkProfile(
            name="spring-boot", language="java", version="latest", status=ProfileStatus.EXPERIMENTAL,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.DEPENDENCY_INJECTION, Capability.MIGRATIONS)),
            dependencies=("spring-boot",), install_command=("mvn", "dependency:go-offline"),
            build_command=("mvn", "-q", "-DskipTests", "package"), test_command=("mvn", "-q", "test"),
            start_command=("mvn", "spring-boot:run"), health_path="/actuator/health",
            validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="spring-boot-gradle", language="java", version="latest", status=ProfileStatus.EXPERIMENTAL,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.DEPENDENCY_INJECTION, Capability.MIGRATIONS)),
            dependencies=("spring-boot",), install_command=("./gradlew", "dependencies"),
            typecheck_command=("./gradlew", "compileJava"),
            build_command=("./gradlew", "build", "-x", "test"), test_command=("./gradlew", "test"),
            smoke_command=("./gradlew", "bootRun"), start_command=("./gradlew", "bootRun"),
            health_path="/actuator/health", validation_steps=("typecheck", "build", "test"),
        ),
        FrameworkProfile(
            name="pygame", language="python", version="latest", status=ProfileStatus.EXPERIMENTAL,
            capabilities=CapabilitySet(),
            dependencies=("pygame",),
            build_command=("python3", "-m", "compileall", "."),
            test_command=("python3", "-m", "pytest"),
            file_role_patterns={
                "entrypoint": ("main.py", "src/main.py", "**/__main__.py"),
                "renderer": ("**/renderer.py", "**/render*.py"),
                "input": ("**/input*.py", "**/event*.py"),
                "rules": ("**/rules.py", "**/game*.py"),
            },
            contract_rules={"public_symbols": ("Game", "render_game", "handle_input")},
            validation_steps=("build", "test"),
        ),
        FrameworkProfile(
            name="stdlib", language="go", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((Capability.HTTP_API, Capability.TEST_CLIENT)),
            install_command=("go", "mod", "download"), lint_command=("go", "vet", "./..."),
            build_command=("go", "build", "./..."),
            test_command=("go", "test", "./..."),
            validation_steps=("lint", "build", "test"), default_for_language=True,
        ),
        FrameworkProfile(
            name="gin", language="go", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common,)),
            dependencies=("github.com/gin-gonic/gin",), install_command=("go", "mod", "download"),
            lint_command=("go", "vet", "./..."), build_command=("go", "build", "./..."),
            test_command=("go", "test", "./..."), smoke_command=("go", "run", "."),
            start_command=("go", "run", "."), validation_steps=("lint", "build", "test"),
        ),
        FrameworkProfile(
            name="echo", language="go", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common,)),
            dependencies=("github.com/labstack/echo/v4",), install_command=("go", "mod", "download"),
            lint_command=("go", "vet", "./..."), build_command=("go", "build", "./..."),
            test_command=("go", "test", "./..."), smoke_command=("go", "run", "."),
            start_command=("go", "run", "."), validation_steps=("lint", "build", "test"),
        ),
        FrameworkProfile(
            name="rust-cli", language="rust", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((Capability.COMMAND_LINE, Capability.TEST_CLIENT)),
            install_command=("cargo", "fetch"), lint_command=("cargo", "clippy", "--all-targets", "--", "-D", "warnings"),
            typecheck_command=("cargo", "check"), build_command=("cargo", "build"),
            test_command=("cargo", "test"), smoke_command=("cargo", "run", "--", "--help"),
            validation_steps=("lint", "typecheck", "build", "test"), default_for_language=True,
        ),
        FrameworkProfile(
            name="axum", language="rust", version="latest", status=ProfileStatus.EXPERIMENTAL,
            capabilities=CapabilitySet.from_values((Capability.HTTP_API, Capability.TEST_CLIENT)),
            dependencies=("axum",), install_command=("cargo", "fetch"),
            lint_command=("cargo", "clippy", "--all-targets", "--", "-D", "warnings"),
            typecheck_command=("cargo", "check"), build_command=("cargo", "build"),
            test_command=("cargo", "test"), smoke_command=("cargo", "run"),
            start_command=("cargo", "run"), validation_steps=("lint", "typecheck", "build", "test"),
        ),
        FrameworkProfile(
            name="actix-web", language="rust", version="latest", status=ProfileStatus.EXPERIMENTAL,
            capabilities=CapabilitySet.from_values((Capability.HTTP_API, Capability.TEST_CLIENT)),
            dependencies=("actix-web",), install_command=("cargo", "fetch"),
            lint_command=("cargo", "clippy", "--all-targets", "--", "-D", "warnings"),
            typecheck_command=("cargo", "check"), build_command=("cargo", "build"),
            test_command=("cargo", "test"), smoke_command=("cargo", "run"),
            start_command=("cargo", "run"), validation_steps=("lint", "typecheck", "build", "test"),
        ),
    ])


DEFAULT_PROFILES = default_profile_registry()

from .workspace import (  # noqa: E402
    DEFAULT_CONFORMANCE_CHECKS,
    PROFILE_SCHEMA_VERSION,
    WorkspaceProfileDocument,
    WorkspaceProfileProbeResult,
    load_workspace_profile,
    probe_workspace_profile,
    promote_workspace_profile,
)

__all__ = [
    "DEFAULT_CONFORMANCE_CHECKS", "DEFAULT_PROFILES", "FrameworkProfile",
    "PROFILE_SCHEMA_VERSION", "ProfileRegistry", "ProfileScope", "ProfileStatus",
    "ValidationStage", "WorkspaceProfileDocument", "WorkspaceProfileProbeResult",
    "default_profile_registry", "load_workspace_profile", "probe_workspace_profile",
    "promote_workspace_profile",
]
