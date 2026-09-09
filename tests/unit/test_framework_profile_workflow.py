from types import SimpleNamespace

import pytest

from app.agent.framework_profiles import DEFAULT_PROFILES
from app.agent.framework_profiles.validation import (
    validate_workflow_profiles,
    validation_targets_for_workflow,
)
from app.agent.workflow_ir import TechnologyProfile


def workflow(*profiles):
    return SimpleNamespace(
        nodes=tuple(
            SimpleNamespace(technology=TechnologyProfile(**profile))
            for profile in profiles
        )
    )


def test_validation_targets_deduplicate_same_stack():
    targets = validation_targets_for_workflow(
        workflow(
            {"language": "python", "framework": "fastapi"},
            {"language": "python", "framework": "fastapi"},
            {"language": "go", "framework": "stdlib"},
        ),
        DEFAULT_PROFILES,
    )

    assert [(key, profile.name) for key, profile in targets] == [
        (("go", "stdlib"), "stdlib"),
        (("python", "fastapi"), "fastapi"),
    ]


@pytest.mark.asyncio
async def test_validate_workflow_profiles_stops_at_first_failed_profile(tmp_path, monkeypatch):
    calls = []

    async def validate(project_dir, profile, *, timeout_seconds):
        calls.append(profile.name)
        return {"passed": profile.name == "stdlib"}

    monkeypatch.setattr(
        "app.agent.framework_profiles.validation.validate_project_profile",
        validate,
    )
    result = await validate_workflow_profiles(
        tmp_path,
        workflow(
            {"language": "go", "framework": "stdlib"},
            {"language": "python", "framework": "fastapi"},
        ),
        DEFAULT_PROFILES,
    )

    assert result["passed"] is False
    assert result["failed_profile"] == "fastapi"
    assert calls == ["stdlib", "fastapi"]
