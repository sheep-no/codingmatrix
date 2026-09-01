import pytest

from app.agent.capabilities import Capability
from app.agent.framework_profiles import DEFAULT_PROFILES, ProfileStatus


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
