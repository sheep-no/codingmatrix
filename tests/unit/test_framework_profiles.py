import pytest

from app.agent.capabilities import Capability
from app.agent.framework_profiles import DEFAULT_PROFILES, FrameworkProfile, ProfileRegistry, ProfileScope, ProfileStatus


@pytest.mark.parametrize(
    ("language", "framework"),
    [("python", "fastapi"), ("python", "flask"), ("typescript", "express"), ("typescript", "nestjs")],
)
def test_builtin_profile_supports_minimum_crud_capabilities(language, framework):
    profile = DEFAULT_PROFILES.require(language, framework)

    assert profile.status is ProfileStatus.SUPPORTED
    assert profile.capabilities.supports(Capability.HTTP_API)
    assert profile.capabilities.supports(Capability.DATABASE)
    assert profile.capabilities.supports(Capability.TEST_CLIENT)
    assert profile.install_command
    assert profile.test_command
    assert profile.start_command


def test_profile_registry_rejects_unknown_framework():
    with pytest.raises(LookupError):
        DEFAULT_PROFILES.require("go", "gin")


def test_javascript_alias_resolves_typescript_profile():
    profile = DEFAULT_PROFILES.require("javascript", "express")

    assert profile.language == "typescript"


def test_workspace_profile_requires_matching_owner_and_stays_pending():
    registry = ProfileRegistry()
    profile = FrameworkProfile.custom_pending(
        name="internal-web", language="python", owner_id="workspace-1"
    )

    registry.register_workspace(profile, "workspace-1")

    assert profile.status is ProfileStatus.CUSTOM_PENDING
    assert profile.scope is ProfileScope.WORKSPACE
    assert registry.get("python", "internal-web") is None

    with pytest.raises(ValueError):
        registry.register_workspace(profile, "workspace-2")


def test_workspace_profile_requires_dependency_and_command_allowlists():
    registry = ProfileRegistry()
    profile = FrameworkProfile(
        name="internal-web", language="python", version="1",
        status=ProfileStatus.CUSTOM_PENDING, capabilities={},
        dependencies=("fastapi",), scope=ProfileScope.WORKSPACE, owner_id="workspace-1",
        command_allowlist=(("python3", "-m", "pytest"),), dependency_allowlist=("fastapi",),
    )
    registry.register_workspace(profile, "workspace-1")

    assert registry.validate_workspace_command(profile, ("python3", "-m", "pytest"))
    assert not registry.validate_workspace_command(profile, ("sh", "run.sh"))


def test_profile_registry_does_not_fallback_to_incompatible_version():
    registry = ProfileRegistry([FrameworkProfile(
        name="custom", language="python", version="2", status=ProfileStatus.EXPERIMENTAL,
        capabilities={},
    )])

    assert registry.get("python", "custom", "1") is None
