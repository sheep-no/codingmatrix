"""framework_profiles 校验与工作区探针的边界补测。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.framework_profiles import validation as validation_module
from app.agent.framework_profiles import workspace as workspace_module
from app.agent.framework_profiles.types import (
    FrameworkProfile,
    ProfileScope,
    ProfileStatus,
)
from app.agent.framework_profiles.validation import (
    validate_project_profile,
    validate_workflow_profiles,
    validation_targets_for_workflow,
)
from app.agent.framework_profiles.workspace import (
    WorkspaceProfileDocument,
    WorkspaceProfileProbeResult,
    load_workspace_profile,
    probe_workspace_profile,
    promote_workspace_profile,
)


def _profile(**overrides):
    base = dict(
        name="p", language="python", version="1", status=ProfileStatus.SUPPORTED,
        capabilities={}, build_command=("python3", "-c", "pass"),
        validation_steps=("build",),
    )
    base.update(overrides)
    return FrameworkProfile(**base)


def _workspace_profile(status=ProfileStatus.CUSTOM_PENDING, **overrides):
    commands = {"syntax": ("python3", "-m", "py_compile", "app.py")}
    base = dict(
        name="internal", language="python", version="1", status=status,
        capabilities={}, scope=ProfileScope.WORKSPACE, owner_id="owner-1",
        workspace_id="workspace-1", probe_commands=commands,
        command_allowlist=tuple(commands.values()),
    )
    base.update(overrides)
    return FrameworkProfile(**base)


def _workflow(*technologies):
    return SimpleNamespace(
        nodes=[SimpleNamespace(technology=tech) for tech in technologies]
    )


class _Registry:
    def __init__(self, profiles):
        self.profiles = profiles
        self.calls = []

    def validation_profile(self, language, framework):
        self.calls.append((language, framework))
        return self.profiles.get((language, framework))


def test_validation_targets_skip_missing_and_unregistered_profiles():
    technology = SimpleNamespace(language="python", framework="fastapi")
    registry = _Registry({("python", "fastapi"): _profile(name="fastapi")})
    workflow = SimpleNamespace(
        nodes=[
            SimpleNamespace(technology=None),
            SimpleNamespace(technology=SimpleNamespace(language="", framework="x")),
            SimpleNamespace(technology=SimpleNamespace(language="js", framework="react")),
            SimpleNamespace(technology=technology),
        ]
    )

    targets = validation_targets_for_workflow(workflow, registry)

    assert [key for key, _ in targets] == [("python", "fastapi")]
    assert registry.calls == [
        ("js", "react"),
        ("python", "fastapi"),
    ]


def test_validation_targets_default_name_and_language():
    profile = SimpleNamespace()
    registry = _Registry({("python", "x"): profile})
    workflow = _workflow(SimpleNamespace(language="python", framework="x"))

    targets = validation_targets_for_workflow(workflow, registry)

    assert targets[0][0] == ("python", "x")


async def test_validate_workflow_single_profile_returns_result(monkeypatch):
    profile = _profile(name="only")
    monkeypatch.setattr(
        validation_module,
        "validation_targets_for_workflow",
        lambda w, r: ((("python", "only"), profile),),
    )

    async def fake_validate(_dir, _profile, *, timeout_seconds=120.0):
        return {"passed": True}

    monkeypatch.setattr(validation_module, "validate_project_profile", fake_validate)

    assert await validate_workflow_profiles(Path("."), None, None) == {"passed": True}


async def test_validate_workflow_single_profile_failure_returns_directly(monkeypatch):
    profile = _profile(name="only")
    monkeypatch.setattr(
        validation_module,
        "validation_targets_for_workflow",
        lambda w, r: ((("python", "only"), profile),),
    )

    async def fake_validate(*_args, **_kwargs):
        return {"passed": False, "diagnostics": ["boom"]}

    monkeypatch.setattr(validation_module, "validate_project_profile", fake_validate)

    result = await validate_workflow_profiles(Path("."), None, None)

    assert result == {"passed": False, "diagnostics": ["boom"]}


async def test_validate_workflow_retries_without_timeout_on_type_error(monkeypatch):
    profiles = (
        (("python", "a"), _profile(name="a")),
        (("js", "b"), _profile(name="b", language="js")),
    )
    monkeypatch.setattr(
        validation_module, "validation_targets_for_workflow", lambda w, r: profiles
    )
    calls = []

    async def fake_validate(_dir, profile, *, timeout_seconds=120.0):
        calls.append((profile.name, timeout_seconds))
        if len(calls) == 1 and timeout_seconds != 120.0:
            raise TypeError("timeout_seconds not supported")
        return {"passed": True}

    monkeypatch.setattr(validation_module, "validate_project_profile", fake_validate)

    result = await validate_workflow_profiles(Path("."), None, None, timeout_seconds=30.0)

    assert result == {"passed": True, "profiles": {"a": {"passed": True}, "b": {"passed": True}}}
    assert calls[0] == ("a", 30.0)
    assert calls[1] == ("a", 120.0)


async def test_validate_workflow_reraises_unrelated_type_error(monkeypatch):
    profile = _profile(name="a")
    monkeypatch.setattr(
        validation_module, "validation_targets_for_workflow",
        lambda w, r: ((("python", "a"), profile),),
    )

    async def fake_validate(*_args, **_kwargs):
        raise TypeError("unrelated bug")

    monkeypatch.setattr(validation_module, "validate_project_profile", fake_validate)

    with pytest.raises(TypeError, match="unrelated bug"):
        await validate_workflow_profiles(Path("."), None, None)


async def test_validate_workflow_multi_profile_failure_reports_failed_profile(monkeypatch):
    profiles = (
        (("python", "a"), _profile(name="a")),
        (("js", "b"), _profile(name="b", language="js")),
    )
    monkeypatch.setattr(
        validation_module, "validation_targets_for_workflow", lambda w, r: profiles
    )

    async def fake_validate(_dir, profile, **_kwargs):
        return {"passed": profile.name == "a"}

    monkeypatch.setattr(validation_module, "validate_project_profile", fake_validate)

    result = await validate_workflow_profiles(Path("."), None, None)

    assert result == {
        "passed": False,
        "profiles": {"a": {"passed": True}, "b": {"passed": False}},
        "failed_profile": "b",
    }


async def test_validate_project_profile_skips_unknown_and_missing_steps(tmp_path):
    profile = _profile()
    profile = FrameworkProfile.model_construct(**{
        **profile.__dict__, "validation_steps": ("unknown-stage", "lint")
    })

    result = await validate_project_profile(tmp_path, profile)

    assert result == {"passed": True, "status": "completed", "diagnostics": []}


async def test_validate_project_profile_runs_multiple_steps(tmp_path):
    profile = _profile(
        validation_steps=("build", "test"),
        test_command=("python3", "-c", "pass"),
    )

    result = await validate_project_profile(tmp_path, profile)

    assert result["passed"] is True


def test_workspace_document_rejects_reused_or_mismatched_scope(tmp_path):
    profile = _workspace_profile()
    document = WorkspaceProfileDocument.build(
        workspace_id="workspace-1", owner_id="owner-1", profile=profile
    )
    path = tmp_path / "profile.json"
    path.write_text(document.model_dump_json(), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be reused"):
        load_workspace_profile(
            path, workspace=tmp_path, workspace_id="workspace-1", owner_id="owner-2"
        )


def test_load_workspace_profile_rejects_escape_and_invalid_json(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="stay inside workspace"):
        load_workspace_profile(
            outside, workspace=workspace, workspace_id="w", owner_id="o"
        )

    invalid = workspace / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_workspace_profile(
            invalid, workspace=workspace, workspace_id="w", owner_id="o"
        )

    binary = workspace / "binary.json"
    binary.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_workspace_profile(
            binary, workspace=workspace, workspace_id="w", owner_id="o"
        )


def test_workspace_document_rejects_digest_and_scope_tampering():
    profile = _workspace_profile()
    document = WorkspaceProfileDocument.build(
        workspace_id="workspace-1", owner_id="owner-1", profile=profile
    )

    with pytest.raises(ValueError, match="digest"):
        WorkspaceProfileDocument(
            workspace_id="workspace-1", owner_id="owner-1",
            profile=profile, digest="0" * 64,
        )


async def test_probe_rejects_non_workspace_and_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="workspace scope"):
        await probe_workspace_profile(tmp_path, _profile())

    with pytest.raises(ValueError, match="existing directory"):
        await probe_workspace_profile(tmp_path / "missing", _workspace_profile())


async def test_probe_reports_missing_and_disallowed_commands(tmp_path):
    profile = _workspace_profile(probe_commands={}, command_allowlist=())

    result = await probe_workspace_profile(
        tmp_path, profile, required_checks=("syntax", "custom")
    )

    assert result.passed is False
    assert any("probe command is required" in failure for failure in result.failures)


async def test_probe_reports_command_outside_allowlist(tmp_path):
    command = ("python3", "-m", "py_compile", "app.py")
    profile = _workspace_profile()
    profile = FrameworkProfile.model_construct(**{
        **profile.__dict__,
        "probe_commands": {"syntax": command},
        "command_allowlist": (),
    })

    result = await probe_workspace_profile(
        tmp_path, profile, required_checks=("syntax",)
    )

    assert result.failures == ("syntax: probe command is outside command_allowlist",)


class _Runner:
    def __init__(self, results):
        self.results = list(results)
        self.specs = []

    async def run(self, spec, workspace):
        self.specs.append(spec)
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def test_probe_handles_start_failure_and_nonzero_exit(tmp_path):
    command = ("python3", "-m", "py_compile", "app.py")
    profile = _workspace_profile(
        probe_commands={"syntax": command, "install": command},
        command_allowlist=(command,),
    )
    runner = _Runner([
        OSError("cannot spawn"),
        (1, "stdout text", "stderr text"),
    ])

    result = await probe_workspace_profile(
        tmp_path, profile, required_checks=("syntax", "install"), runner=runner
    )

    assert result.passed is False
    assert any("could not start" in failure for failure in result.failures)
    assert any("exit 1" in failure for failure in result.failures)
    assert runner.specs[1].timeout_seconds == 600


async def test_probe_requires_at_least_one_completed_check(tmp_path):
    profile = _workspace_profile()

    result = await probe_workspace_profile(
        tmp_path, profile, required_checks=(), runner=_Runner([])
    )

    assert result.passed is False
    assert result.checks == ()


def test_promote_rejects_wrong_target_and_status():
    profile = _workspace_profile(status=ProfileStatus.EXPERIMENTAL)
    result = WorkspaceProfileProbeResult(passed=True, checks=("syntax",))

    with pytest.raises(ValueError, match="only custom_pending"):
        promote_workspace_profile(
            profile, result, required_checks=("syntax",)
        )

    custom = _workspace_profile()
    with pytest.raises(ValueError, match="only experimental"):
        promote_workspace_profile(
            custom, result, required_checks=("syntax",),
            target=ProfileStatus.SUPPORTED,
        )

    with pytest.raises(ValueError, match="target is unsupported"):
        promote_workspace_profile(
            custom, result, required_checks=("syntax",),
            target=ProfileStatus.CUSTOM_PENDING,
        )


# --- 文档校验器与注册表边界 ---

def _document_kwargs():
    profile = _workspace_profile()
    document = WorkspaceProfileDocument.build(
        workspace_id="workspace-1", owner_id="owner-1", profile=profile
    )
    return document


def test_workspace_document_rejects_unsupported_schema_version():
    document = _document_kwargs()
    with pytest.raises(ValueError, match="schema version"):
        WorkspaceProfileDocument(
            schema_version=2, workspace_id=document.workspace_id,
            owner_id=document.owner_id, profile=document.profile, digest=document.digest,
        )


def test_workspace_document_rejects_system_scope():
    document = _document_kwargs()
    system_profile = _profile()
    with pytest.raises(ValueError, match="workspace scope"):
        WorkspaceProfileDocument(
            workspace_id=document.workspace_id, owner_id=document.owner_id,
            profile=system_profile, digest=document.digest,
        )


def test_workspace_document_rejects_promoted_status():
    document = _document_kwargs()
    promoted = document.profile.model_copy(update={"status": ProfileStatus.EXPERIMENTAL})
    from app.agent.framework_profiles.workspace import _document_digest

    digest = _document_digest(1, document.workspace_id, document.owner_id, promoted)
    with pytest.raises(ValueError, match="custom_pending"):
        WorkspaceProfileDocument(
            workspace_id=document.workspace_id, owner_id=document.owner_id,
            profile=promoted, digest=digest,
        )


def test_workspace_document_rejects_scope_mismatch():
    document = _document_kwargs()
    other = document.profile.model_copy(update={"owner_id": "owner-2"})
    from app.agent.framework_profiles.workspace import _document_digest

    digest = _document_digest(1, document.workspace_id, document.owner_id, other)
    with pytest.raises(ValueError, match="scope does not match"):
        WorkspaceProfileDocument(
            workspace_id=document.workspace_id, owner_id=document.owner_id,
            profile=other, digest=digest,
        )


def _construct_profile(**overrides):
    base = _workspace_profile()
    return FrameworkProfile.model_construct(**{**base.__dict__, **overrides})


def test_workspace_profile_requires_owner_and_workspace():
    with pytest.raises(ValueError, match="owner_id"):
        _construct_profile(owner_id=None).validate_workspace_contract()
    with pytest.raises(ValueError, match="workspace_id"):
        _construct_profile(workspace_id=None).validate_workspace_contract()


def test_workspace_profile_rejects_empty_allowlist_entry():
    from app.agent.framework_profiles.types import _validate_workspace_command

    with pytest.raises(ValueError, match="empty commands"):
        _construct_profile(command_allowlist=((),)).validate_workspace_contract()
    with pytest.raises(ValueError, match="not allowlisted"):
        _validate_workspace_command(("curl", "https://example.test"))
    with pytest.raises(ValueError, match="inline interpreter"):
        _validate_workspace_command(("node", "-e", "1"))
    with pytest.raises(ValueError, match="inside workspace"):
        _validate_workspace_command(("python3", "/etc/passwd"))


def test_workspace_profile_rejects_dependencies_outside_allowlist():
    with pytest.raises(ValueError, match="dependency_allowlist"):
        _construct_profile(
            dependencies=("requests",), dependency_allowlist=()
        ).validate_workspace_contract()


def test_custom_pending_requires_owner():
    with pytest.raises(ValueError, match="owner_id"):
        FrameworkProfile.custom_pending(name="p", language="python", owner_id="   ")


def test_registry_register_rejects_workspace_profile_without_owner():
    from app.agent.framework_profiles import ProfileRegistry

    profile = _construct_profile(owner_id=None)
    with pytest.raises(ValueError, match="owner_id"):
        ProfileRegistry().register(profile)


def test_registry_command_check_for_system_profile():
    from app.agent.framework_profiles import ProfileRegistry

    registry = ProfileRegistry()
    assert registry.validate_workspace_command(_profile(), ("python3",)) is False


def test_registry_get_workspace_by_explicit_version():
    from app.agent.framework_profiles import ProfileRegistry

    registry = ProfileRegistry()
    profile = _workspace_profile()
    registry.register_workspace(profile, "owner-1", "workspace-1")

    assert registry.get_workspace(
        "python", "internal", owner_id="owner-1", workspace_id="workspace-1", version="1"
    ) == profile
    assert registry.get_workspace(
        "python", "internal", owner_id="owner-1", workspace_id="workspace-1", version="2"
    ) is None


def test_registry_validation_profile_prefers_framework_and_single_candidate():
    from app.agent.framework_profiles import ProfileRegistry

    framework_profile = _profile(name="framework", validation_steps=("build",))
    fallback = _profile(name="fallback", validation_steps=("test",), test_command=("python3", "-c", "pass"))

    assert ProfileRegistry([framework_profile, fallback]).validation_profile(
        "python", "framework"
    ) is framework_profile
    assert ProfileRegistry([fallback]).validation_profile("python") is fallback


def test_registry_validation_profile_returns_none_when_ambiguous():
    from app.agent.framework_profiles import ProfileRegistry

    first = _profile(name="one", validation_steps=("build",))
    second = _profile(name="two", validation_steps=("build",))
    registry = ProfileRegistry([first, second])

    assert registry.validation_profile("python") is None
