"""Tests for technology-neutral constrained synthesis contracts."""

import pytest

from app.agent.capabilities import Capability, CapabilitySet
from app.agent.code_synthesis_contracts import (
    ArtifactSpec,
    ChangePlanIR,
    GenerationStrategy,
    ProjectModel,
    StrategyDecision,
    ValidationProfile,
)
from app.agent.strategy_router import StrategyRouter
from app.agent.orchestration.ir_projection import (
    UnsupportedArtifactOperation,
    project_change_plan,
)
from app.agent.framework_profiles import FrameworkProfile, ProfileStatus, ValidationStage
from app.agent.orchestration.profile_bridge import (
    project_model_from_profile,
    validation_plan_from_framework,
    validation_profile_from_framework,
)
from app.agent.synthesis_capabilities import SynthesisCapabilityRegistry


def _project() -> ProjectModel:
    return ProjectModel(
        language="python",
        framework="fastapi",
        runtime="3.11",
        capabilities=CapabilitySet.from_values(
            (Capability.HTTP_API, Capability.DATABASE, Capability.TEST_CLIENT)
        ),
    )


def _artifact(
    path: str,
    *,
    dependencies=(),
    depends_on=None,
    strategy=GenerationStrategy.TEMPLATE,
    operation="create",
) -> ArtifactSpec:
    return ArtifactSpec(
        path=path,
        role="module",
        owner="stack-adapter",
        operation=operation,
        strategy=strategy,
        depends_on=tuple(dependencies if depends_on is None else depends_on),
        validation_profile="python",
        source="request",
    )


def test_change_plan_supports_dynamic_artifact_count_and_round_trip() -> None:
    plan = ChangePlanIR.build(
        _project(),
        [
            _artifact("src/api.py", dependencies=("src/model.py",)),
            _artifact("src/model.py"),
            _artifact("tests/test_api.py", dependencies=("src/api.py",), strategy=GenerationStrategy.LLM),
        ],
        {"api": {"path": "/items"}},
    )

    assert [item.path for item in plan.artifacts] == [
        "src/api.py",
        "src/model.py",
        "tests/test_api.py",
    ]
    assert ChangePlanIR.model_validate_json(plan.model_dump_json()) == plan
    assert plan.artifact("src/api.py").depends_on == ("src/model.py",)


def test_change_plan_rejects_missing_dependency_and_cycle() -> None:
    with pytest.raises(ValueError, match="missing artifact dependencies"):
        ChangePlanIR.build(_project(), [_artifact("api.py", dependencies=("missing.py",))])

    with pytest.raises(ValueError, match="cycle"):
        ChangePlanIR.build(
            _project(),
            [_artifact("a.py", dependencies=("b.py",)), _artifact("b.py", dependencies=("a.py",))],
        )


def test_change_plan_digest_detects_tampering() -> None:
    plan = ChangePlanIR.build(_project(), [_artifact("main.py")])
    payload = plan.model_dump(mode="json")
    payload["artifacts"][0]["role"] = "changed"

    with pytest.raises(ValueError, match="digest"):
        ChangePlanIR.model_validate(payload)


def test_contracts_are_strict_and_strategy_decision_is_serializable() -> None:
    with pytest.raises(ValueError, match="extra"):
        ProjectModel(language="python", unexpected=True)

    profile = ValidationProfile(name="python", required_scopes=("compile", "test"))
    decision = StrategyDecision(
        strategy=GenerationStrategy.PATCH,
        reason="existing source requires a local edit",
        capability_evidence=("python-parser",),
    )

    assert profile.required_scopes == ("compile", "test")
    assert decision.model_dump(mode="json")["strategy"] == "patch"


def test_strategy_router_routes_dynamic_plan_without_framework_specific_rules() -> None:
    plan = ChangePlanIR.build(
        ProjectModel(language="go", runtime="1.23"),
        [
            _artifact("cmd/server/main.go", strategy=GenerationStrategy.SCAFFOLD),
            _artifact("internal/api.go", strategy=GenerationStrategy.TEMPLATE),
            _artifact("internal/api_test.go", strategy=GenerationStrategy.LLM),
        ],
        {"api": {"paths": ["/items"]}, "scaffolder": "go-init"},
    )

    decisions = StrategyRouter().route_plan(plan)

    assert decisions["cmd/server/main.go"].strategy is GenerationStrategy.SCAFFOLD
    assert decisions["internal/api.go"].strategy is GenerationStrategy.TEMPLATE
    assert decisions["internal/api_test.go"].strategy is GenerationStrategy.LLM


def test_strategy_router_prefers_patch_for_existing_artifacts() -> None:
    artifact = _artifact("src/service.ts", strategy=GenerationStrategy.LLM)

    decision = StrategyRouter().decide(
        ProjectModel(language="typescript"),
        artifact,
        existing_paths=("src/service.ts",),
    )

    assert decision.strategy is GenerationStrategy.PATCH
    assert decision.degraded is False


def test_strategy_router_degrades_when_deterministic_capability_is_missing() -> None:
    artifact = _artifact("generated/client.py", strategy=GenerationStrategy.SCHEMA_CODEGEN)

    decision = StrategyRouter().decide(ProjectModel(language="python"), artifact)

    assert decision.strategy is GenerationStrategy.LLM
    assert decision.degraded is True


def test_ir_projection_preserves_strategy_provenance_for_core_scheduler() -> None:
    plan = ChangePlanIR.build(
        ProjectModel(language="python", framework="generic"),
        [
            _artifact("src/models.py", strategy=GenerationStrategy.SCHEMA_CODEGEN),
            _artifact(
                "src/routes.py",
                strategy=GenerationStrategy.LLM,
                depends_on=("src/models.py",),
            ),
        ],
        {"schema": {"entities": ["Item"]}},
    )

    projected = project_change_plan(plan)

    routes = next(item for item in projected.files if item.path == "src/routes.py")
    assert routes.strategy == "llm"
    assert routes.strategy_reason
    assert routes.dependencies == ("src/models.py",)
    assert projected.digest


def test_ir_projection_rejects_lifecycle_operations_until_core_supports_them() -> None:
    plan = ChangePlanIR.build(
        ProjectModel(language="python"),
        [_artifact("src/old.py", operation="delete")],
    )

    with pytest.raises(UnsupportedArtifactOperation, match="delete"):
        project_change_plan(plan)


def test_framework_profile_bridges_to_project_and_validation_contracts() -> None:
    profile = FrameworkProfile(
        name="generic-python",
        language="python",
        version="3.11",
        status=ProfileStatus.SUPPORTED,
        capabilities=CapabilitySet.from_values((Capability.HTTP_API,)),
        test_command=("python3", "-m", "pytest"),
        validation_steps=(ValidationStage.TEST.value,),
    )

    project = project_model_from_profile(profile, entrypoints=("app.py",))
    contract = validation_profile_from_framework(profile)
    plan = validation_plan_from_framework(profile)

    assert project.framework == "generic-python"
    assert project.entrypoints == ("app.py",)
    assert contract.required_scopes == ("test",)
    assert plan.ready is True
    assert plan.commands[0].command == ("python3", "-m", "pytest")


def test_synthesis_registry_connects_language_adapter_and_official_scaffolder() -> None:
    project = ProjectModel(language="typescript", framework="express")

    registry = SynthesisCapabilityRegistry()
    capabilities = registry.inspect(project)
    request = registry.scaffold_request(project, "service")

    assert capabilities.parser is True
    assert capabilities.structural_editor is True
    assert capabilities.scaffolder is True
    assert "language-adapter:javascript" in capabilities.evidence
    assert request.target_dir == "service"
    assert request.command[0] == "npx"


def test_strategy_router_uses_registered_scaffolder_without_contract_hint() -> None:
    artifact = _artifact("package.json", strategy=GenerationStrategy.SCAFFOLD)

    decision = StrategyRouter().decide(
        ProjectModel(language="typescript", framework="express"), artifact
    )

    assert decision.strategy is GenerationStrategy.SCAFFOLD
    assert decision.degraded is False
    assert "official-scaffolder:express" in decision.capability_evidence


def test_unknown_language_has_explicit_patch_degradation() -> None:
    artifact = _artifact("src/module.xyz", strategy=GenerationStrategy.PATCH)

    decision = StrategyRouter().decide(ProjectModel(language="unknown"), artifact)

    assert decision.strategy is GenerationStrategy.LLM
    assert decision.degraded is True
