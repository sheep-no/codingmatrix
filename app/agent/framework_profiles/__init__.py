"""Versioned framework profiles used by planning and validation."""

from enum import Enum
from typing import Dict, Iterable, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.agent.capabilities import Capability, CapabilitySet


class ProfileStatus(str, Enum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    CUSTOM_PENDING = "custom_pending"


class FrameworkProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    language: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: ProfileStatus
    capabilities: CapabilitySet
    dependencies: Tuple[str, ...] = ()
    install_command: Tuple[str, ...] = ()
    build_command: Tuple[str, ...] = ()
    test_command: Tuple[str, ...] = ()
    start_command: Tuple[str, ...] = ()
    health_path: str = "/health"


class ProfileRegistry:
    """Resolve profiles by language, framework name, and version."""

    def __init__(self, profiles: Iterable[FrameworkProfile] = ()) -> None:
        self._profiles: Dict[tuple[str, str, str], FrameworkProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: FrameworkProfile) -> None:
        key = (profile.language.lower(), profile.name.lower(), profile.version)
        self._profiles[key] = profile

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
        ]
        return candidates[0] if candidates else None

    def require(self, language: str, framework: str, version: str = "latest") -> FrameworkProfile:
        profile = self.get(language, framework, version)
        if profile is None:
            raise LookupError(f"framework profile not found: {language}/{framework}/{version}")
        return profile

    def all(self) -> Tuple[FrameworkProfile, ...]:
        return tuple(self._profiles.values())


def default_profile_registry() -> ProfileRegistry:
    common = (Capability.HTTP_API, Capability.DATABASE, Capability.TEST_CLIENT)
    return ProfileRegistry([
        FrameworkProfile(
            name="fastapi", language="python", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.DEPENDENCY_INJECTION, Capability.MIGRATIONS)),
            dependencies=("fastapi", "uvicorn"), install_command=("python3", "-m", "pip", "install", "-r", "requirements.txt"),
            test_command=("python3", "-m", "pytest"), start_command=("uvicorn", "app.main:app"),
        ),
        FrameworkProfile(
            name="flask", language="python", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.MIGRATIONS)),
            dependencies=("flask",), install_command=("python3", "-m", "pip", "install", "-r", "requirements.txt"),
            test_command=("python3", "-m", "pytest"), start_command=("flask", "run"),
        ),
        FrameworkProfile(
            name="express", language="typescript", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.AUTHENTICATION, Capability.WEBSOCKET)),
            dependencies=("express",), install_command=("npm", "install"), test_command=("npm", "test"), start_command=("npm", "start"),
        ),
        FrameworkProfile(
            name="nestjs", language="typescript", version="latest", status=ProfileStatus.SUPPORTED,
            capabilities=CapabilitySet.from_values((*common, Capability.ORM, Capability.AUTHENTICATION, Capability.WEBSOCKET, Capability.DEPENDENCY_INJECTION, Capability.MIGRATIONS)),
            dependencies=("@nestjs/common",), install_command=("npm", "install"), test_command=("npm", "test"), start_command=("npm", "run", "start"),
        ),
    ])


DEFAULT_PROFILES = default_profile_registry()

__all__ = ["FrameworkProfile", "ProfileRegistry", "ProfileStatus", "DEFAULT_PROFILES", "default_profile_registry"]
