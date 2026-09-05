import pytest

from app.agent.capabilities import Capability
from app.agent.framework_profiles import DEFAULT_PROFILES, FrameworkProfile, ProfileRegistry, ProfileScope, ProfileStatus
from app.agent.framework_profiles.validation import validate_project_profile
from app.agent.framework_profiles.workspace import (
    WorkspaceProfileDocument,
    WorkspaceProfileProbeResult,
    load_workspace_profile,
    probe_workspace_profile,
    promote_workspace_profile,
)


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
        DEFAULT_PROFILES.require("go", "unknown")


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
        workspace_id="workspace-1",
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


def test_go_stdlib_profile_declares_build_and_test_gate():
    profile = DEFAULT_PROFILES.require("go", "stdlib")

    assert profile.build_command == ("go", "build", "./...")
    assert profile.test_command == ("go", "test", "./...")
    assert profile.lint_command == ("go", "vet", "./...")
    assert profile.validation_steps == ("lint", "build", "test")


@pytest.mark.parametrize(
    ("language", "framework", "build_command", "test_command"),
    [
        ("python", "fastapi", ("python3", "-m", "compileall", "."), ("python3", "-m", "pytest")),
        ("python", "flask", ("python3", "-m", "compileall", "."), ("python3", "-m", "pytest")),
        ("typescript", "express", ("npm", "run", "build"), ("npm", "test")),
        ("typescript", "nestjs", ("npm", "run", "build"), ("npm", "test")),
        ("java", "spring-boot", ("mvn", "-q", "-DskipTests", "package"), ("mvn", "-q", "test")),
    ],
)
def test_builtin_profiles_declare_build_and_test_gates(
    language, framework, build_command, test_command
):
    profile = DEFAULT_PROFILES.require(language, framework)

    assert profile.build_command == build_command
    assert profile.test_command == test_command
    assert profile.validation_steps == ("build", "test")


def test_registry_resolves_the_only_validation_profile_for_a_language():
    profile = DEFAULT_PROFILES.validation_profile("go")

    assert profile is not None
    assert profile.name == "stdlib"


def test_registry_uses_language_validation_profile_when_framework_is_unregistered():
    profile = DEFAULT_PROFILES.validation_profile("go", "unknown")

    assert profile is not None
    assert profile.name == "stdlib"


@pytest.mark.parametrize(
    ("language", "framework"),
    [
        ("python", "django"),
        ("python", "stdlib-cli"),
        ("typescript", "react-vite"),
        ("typescript", "nextjs"),
        ("go", "gin"),
        ("go", "echo"),
        ("rust", "rust-cli"),
        ("rust", "axum"),
        ("rust", "actix-web"),
        ("java", "spring-boot-gradle"),
    ],
)
def test_high_frequency_builtin_profiles_are_registered(language, framework):
    profile = DEFAULT_PROFILES.require(language, framework)

    assert profile.validation_steps
    assert profile.build_command
    assert profile.test_command


def test_profile_commands_reject_shell_operators():
    with pytest.raises(ValueError, match="shell operators"):
        FrameworkProfile(
            name="unsafe", language="python", version="1",
            status=ProfileStatus.EXPERIMENTAL, capabilities={},
            build_command=("python3", "-m", "compileall", ".", "&&", "whoami"),
        )


def test_profile_rejects_standard_validation_step_without_command():
    with pytest.raises(ValueError, match="requires a command"):
        FrameworkProfile(
            name="incomplete", language="python", version="1",
            status=ProfileStatus.EXPERIMENTAL, capabilities={},
            validation_steps=("typecheck",),
        )


def test_profile_rejects_unknown_validation_step():
    with pytest.raises(ValueError, match="unsupported validation step"):
        FrameworkProfile(
            name="incomplete", language="python", version="1",
            status=ProfileStatus.EXPERIMENTAL, capabilities={},
            validation_steps=("compile",),
        )


def test_builtin_profile_defaults_are_unique_per_language():
    defaults = {}
    for profile in DEFAULT_PROFILES.all():
        if profile.default_for_language:
            assert profile.language not in defaults
            defaults[profile.language] = profile.name

    assert defaults == {"go": "stdlib", "rust": "rust-cli"}


def test_frontend_and_cli_profiles_declare_domain_capabilities():
    assert DEFAULT_PROFILES.require("typescript", "react-vite").capabilities.supports(
        Capability.FRONTEND_UI
    )
    assert DEFAULT_PROFILES.require("python", "stdlib-cli").capabilities.supports(
        Capability.COMMAND_LINE
    )


def test_rust_default_profile_is_deterministic():
    profile = DEFAULT_PROFILES.validation_profile("rust", "unknown")

    assert profile is not None
    assert profile.name == "rust-cli"


@pytest.mark.asyncio
async def test_profile_validation_runs_declared_commands(tmp_path):
    profile = FrameworkProfile(
        name="test", language="python", version="1", status=ProfileStatus.SUPPORTED,
        capabilities={}, build_command=("python3", "-c", "pass"),
        validation_steps=("build",),
    )

    result = await validate_project_profile(tmp_path, profile)

    assert result == {"passed": True, "status": "completed", "diagnostics": []}


@pytest.mark.asyncio
async def test_profile_validation_reports_command_failure(tmp_path):
    profile = FrameworkProfile(
        name="test", language="python", version="1", status=ProfileStatus.SUPPORTED,
        capabilities={}, build_command=("python3", "-c", "raise SystemExit('broken')"),
        validation_steps=("build",),
    )

    result = await validate_project_profile(tmp_path, profile)

    assert result["passed"] is False
    assert result["status"] == "failed"
    assert result["step"] == "build"
    assert "broken" in result["diagnostics"][0]


@pytest.mark.asyncio
async def test_profile_validation_reports_missing_command(tmp_path):
    profile = FrameworkProfile(
        name="test", language="python", version="1", status=ProfileStatus.SUPPORTED,
        capabilities={}, build_command=("command-that-does-not-exist",),
        validation_steps=("build",),
    )

    result = await validate_project_profile(tmp_path, profile)

    assert result["passed"] is False
    assert "could not start" in result["diagnostics"][0]


@pytest.mark.asyncio
async def test_profile_validation_reports_timeout(tmp_path):
    profile = FrameworkProfile(
        name="test", language="python", version="1", status=ProfileStatus.SUPPORTED,
        capabilities={}, build_command=("python3", "-c", "import time; time.sleep(1)"),
        validation_steps=("build",),
    )

    result = await validate_project_profile(tmp_path, profile, timeout_seconds=0.01)

    assert result["passed"] is False
    assert result["status"] == "timed_out"


def _workspace_profile(status=ProfileStatus.CUSTOM_PENDING):
    commands = {
        "syntax": ("python3", "-m", "py_compile", "app.py"),
        "install": ("python3", "-m", "pip", "--version"),
        "startup": ("python3", "-m", "py_compile", "app.py"),
        "crud": ("python3", "-m", "pytest", "tests/test_crud.py", "-q"),
        "persistence": ("python3", "-m", "pytest", "tests/test_persistence.py", "-q"),
    }
    return FrameworkProfile(
        name="internal-web", language="python", version="1", status=status,
        capabilities={}, scope=ProfileScope.WORKSPACE, owner_id="owner-1",
        workspace_id="workspace-1", probe_commands=commands,
        command_allowlist=tuple(commands.values()),
    )


def test_workspace_profile_document_enforces_owner_workspace_and_digest(tmp_path):
    profile = _workspace_profile()
    document = WorkspaceProfileDocument.build(
        workspace_id="workspace-1", owner_id="owner-1", profile=profile
    )
    path = tmp_path / "profile.json"
    path.write_text(document.model_dump_json(), encoding="utf-8")

    loaded = load_workspace_profile(
        path, workspace=tmp_path, workspace_id="workspace-1", owner_id="owner-1"
    )

    assert loaded.profile == profile
    with pytest.raises(ValueError, match="reused"):
        load_workspace_profile(
            path, workspace=tmp_path, workspace_id="workspace-2", owner_id="owner-1"
        )


def test_registry_isolates_workspace_profiles_by_owner_and_workspace():
    registry = ProfileRegistry()
    profile = _workspace_profile()
    registry.register_workspace(profile, "owner-1", "workspace-1")

    assert registry.get_workspace(
        "python", "internal-web", owner_id="owner-1", workspace_id="workspace-1"
    ) == profile
    assert registry.get_workspace(
        "python", "internal-web", owner_id="owner-2", workspace_id="workspace-1"
    ) is None


def test_workspace_profile_rejects_declared_command_outside_allowlist():
    with pytest.raises(ValueError, match="command_allowlist"):
        FrameworkProfile(
            name="unsafe", language="python", version="1",
            status=ProfileStatus.CUSTOM_PENDING, capabilities={},
            scope=ProfileScope.WORKSPACE, owner_id="owner-1", workspace_id="workspace-1",
            build_command=("python3", "-m", "compileall", "."),
        )


def test_workspace_profile_rejects_inline_interpreter_commands():
    command = ("python3", "-c", "import os")
    with pytest.raises(ValueError, match="inline interpreter"):
        FrameworkProfile(
            name="unsafe", language="python", version="1",
            status=ProfileStatus.CUSTOM_PENDING, capabilities={},
            scope=ProfileScope.WORKSPACE, owner_id="owner-1", workspace_id="workspace-1",
            probe_commands={"syntax": command}, command_allowlist=(command,),
        )


@pytest.mark.asyncio
async def test_workspace_profile_advances_only_after_real_probe_checks(tmp_path):
    profile = _workspace_profile()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests_dir / "test_crud.py").write_text("def test_crud(): assert True\n", encoding="utf-8")
    (tests_dir / "test_persistence.py").write_text(
        "def test_persistence(): assert True\n", encoding="utf-8"
    )

    result = await probe_workspace_profile(tmp_path, profile)
    experimental = promote_workspace_profile(profile, result)
    supported = promote_workspace_profile(
        experimental, result, target=ProfileStatus.SUPPORTED
    )

    assert result.passed
    assert experimental.status is ProfileStatus.EXPERIMENTAL
    assert supported.status is ProfileStatus.SUPPORTED


def test_workspace_profile_rejects_incomplete_promotion_evidence():
    result = WorkspaceProfileProbeResult(passed=True, checks=("syntax",))

    with pytest.raises(ValueError, match="complete passing"):
        promote_workspace_profile(_workspace_profile(), result)
