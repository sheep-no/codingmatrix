"""Versioned framework profiles used by planning and validation."""

from typing import Dict, Iterable, Tuple

from app.agent.capabilities import Capability, CapabilitySet

from .types import FrameworkProfile, ProfileScope, ProfileStatus, ValidationStage
from .workspace import (
    DEFAULT_CONFORMANCE_CHECKS,
    PROFILE_SCHEMA_VERSION,
    WorkspaceProfileDocument,
    WorkspaceProfileProbeResult,
    load_workspace_profile,
    probe_workspace_profile,
    promote_workspace_profile,
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

__all__ = [
    "DEFAULT_CONFORMANCE_CHECKS", "DEFAULT_PROFILES", "FrameworkProfile",
    "PROFILE_SCHEMA_VERSION", "ProfileRegistry", "ProfileScope", "ProfileStatus",
    "ValidationStage", "WorkspaceProfileDocument", "WorkspaceProfileProbeResult",
    "default_profile_registry", "load_workspace_profile", "probe_workspace_profile",
    "promote_workspace_profile",
]
