"""Tests for technology-neutral constrained synthesis contracts."""

import pytest

from app.agent.capabilities import Capability, CapabilitySet
from app.agent.code_synthesis_contracts import (
    ArtifactSpec,
    ChangePlanIR,
    GenerationStrategy,
    ModelCapabilityProfile,
    ProjectModel,
    StrategyDecision,
    ValidationProfile,
)
from app.agent.strategy_router import StrategyRouter
from app.agent.synthesis_protocol import (
    ComparableSynthesisInput,
    ModelOperation,
    ModelOperationKind,
)
from app.agent.stack_adapters import (
    ExpressStackAdapter,
    FastAPIStackAdapter,
    GoStackAdapter,
    SpringStackAdapter,
    StackContractRule,
    StackContractValidator,
    StackRepairStrategy,
    StackRepairStrategyRegistry,
    fastapi_crud_repair_applies,
    RepairContext,
    repair_contract_digest,
)
from app.agent.contract_index import ContractIndex
from app.agent.generation_plan import GenerationPlan as ProjectGenerationPlan
from app.agent.interface_registry import InterfaceRegistry
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


def test_repair_contract_digest_is_stable_for_same_inputs():
    assert repair_contract_digest("build an API", ["app.py", "tests/test_app.py"]) == repair_contract_digest(
        "build an API", ("app.py", "tests/test_app.py")
    )


def test_repair_strategy_registry_can_filter_by_explicit_context():
    registry = StackRepairStrategyRegistry((
        StackRepairStrategy(
            "python-only",
            lambda path: "fixed" if path == "main.py" else None,
            applies=lambda context: context.requirement.startswith("python"),
        ),
    ))

    assert registry.select("main.py", RepairContext(requirement="python API")) is not None
    assert registry.select("main.py", RepairContext(requirement="go API")) is None


def test_fastapi_crud_repair_predicate_uses_context_file_scope():
    assert fastapi_crud_repair_applies(RepairContext(
        requirement="repair the existing python fastapi crud service",
        file_entries=("app/main.py", "app/models.py"),
    ))
    assert not fastapi_crud_repair_applies(RepairContext(
        requirement="repair the existing python fastapi crud service",
        file_entries=("app.py", "app/models.py"),
    ))


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


def test_model_capability_profile_is_strict_and_round_trips() -> None:
    profile = ModelCapabilityProfile(
        name="structured-provider",
        supports_structured_output=True,
        supports_json_schema=True,
        supports_tool_calls=True,
        supports_streaming=True,
        max_context_tokens=16_000,
        max_output_tokens=4_000,
    )

    assert ModelCapabilityProfile.model_validate_json(profile.model_dump_json()) == profile

    with pytest.raises(ValueError, match="JSON Schema"):
        ModelCapabilityProfile(name="invalid", supports_json_schema=True)

    with pytest.raises(ValueError, match="max_output_tokens"):
        ModelCapabilityProfile(name="invalid", max_context_tokens=100, max_output_tokens=101)


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


def test_model_operation_enforces_operation_shape_and_path_scope() -> None:
    operation = ModelOperation(
        operation=ModelOperationKind.FILE_SLOT,
        target_path="src/api.py",
        allowed_paths=("src/api.py", "src/model.py"),
        depends_on=("src/model.py",),
        contract_refs=("todo.read",),
        content="def read():\n    return []\n",
    )

    assert ModelOperation.model_validate_json(operation.model_dump_json()) == operation

    with pytest.raises(ValueError, match="outside the allowed path"):
        ModelOperation(
            operation=ModelOperationKind.PATCH,
            target_path="src/other.py",
            allowed_paths=("src/api.py",),
            patch="replace",
        )

    with pytest.raises(ValueError, match="requires target_path and content"):
        ModelOperation(operation=ModelOperationKind.FILE_SLOT, content="source")


def test_contract_index_freezes_shared_contracts() -> None:
    index = ContractIndex.build(
        [
            {"name": "todo.read", "kind": "api", "owner": "routes", "schema": {"method": "GET"}},
            {"name": "todo.entity", "kind": "data", "owner": "models", "schema": {"id": "int"}},
        ]
    )

    assert index.get("todo.read").owner == "routes"
    assert ContractIndex.model_validate_json(index.model_dump_json()) == index

    with pytest.raises(ValueError, match="unique"):
        ContractIndex.build(
            [
                {"name": "duplicate", "kind": "api", "owner": "a"},
                {"name": "duplicate", "kind": "data", "owner": "b"},
            ]
        )


@pytest.mark.parametrize("collection", ["routes", "endpoints"])
def test_http_body_contract_index_roundtrip_and_digest(collection):
    from app.agent.code_synthesis_contracts import HttpContract

    plan = ProjectGenerationPlan.build([{"path": "client.py"}])
    legacy = {"method": "PATCH", "path": "/inventory/{sku}", "status_code": 202}
    body = {
        "request_body_schema": {"type": "object", "properties": {"quantity": {"type": "integer"}}},
        "response_body_schema": {"type": "array", "items": {"type": "string"}},
        "serialization_guidance": "Serialize domain objects with the configured JSON encoder.",
    }
    old = ContractIndex.from_generation_plan(plan, contracts={collection: [legacy]})
    assert old.entries[0].schema == legacy
    contract = HttpContract(**legacy, **body)
    index = ContractIndex.from_generation_plan(
        plan, contracts={collection: [contract.model_dump(exclude_unset=True)]},
    )
    assert index.entries[0].schema == {**legacy, **body}
    assert index.digest != old.digest
    assert ContractIndex.model_validate_json(index.model_dump_json()) == index
    for field, value in (("request_body_schema", False), ("response_body_schema", True),
                         ("serialization_guidance", "Use another encoder.")):
        changed = ContractIndex.from_generation_plan(
            plan, contracts={collection: [{**legacy, **body, field: value}]},
        )
        assert changed.digest != index.digest


def test_contract_index_freezes_plan_interfaces_file_and_http_contracts() -> None:
    plan = ProjectGenerationPlan.build(
        [{
            "path": "src/api.py",
            "file_type": "entry",
            "contract": {"name": "api.module", "exports": ["app"]},
            "contract_refs": ["todo.read"],
        }],
        interfaces=InterfaceRegistry.build([{
            "module": "src/api.py",
            "owner": "src/api.py",
            "symbols": [{"name": "create_app", "return_type": "FastAPI"}],
        }]),
    )

    index = ContractIndex.from_generation_plan(
        plan,
        contracts={
            "routes": [{
                "operation_id": "todo.read",
                "method": "GET",
                "path": "/todos",
            }],
        },
    )

    assert tuple(entry.name for entry in index.entries) == (
        "api.module",
        "create_app",
        "todo.read",
    )
    assert index.get("create_app").schema["return_type"] == "FastAPI"
    assert plan.file_entries()[0]["contract_refs"] == ["todo.read"]


def test_model_replacement_uses_the_same_frozen_synthesis_input() -> None:
    plan = ChangePlanIR.build(_project(), [_artifact("src/api.py")])
    contracts = ContractIndex.build(
        [{"name": "todo.read", "kind": "api", "owner": "routes"}]
    )
    first = ComparableSynthesisInput.build("create an API", plan, contracts, "a" * 64)
    replacement = ComparableSynthesisInput.build("create an API", plan, contracts, "a" * 64)

    first.assert_compatible(replacement)
    assert first.required_paths == ("src/api.py",)

    with pytest.raises(ValueError, match="not comparable"):
        first.assert_compatible(
            ComparableSynthesisInput.build("different request", plan, contracts, "a" * 64)
        )


def test_stack_contract_validator_aggregates_stack_owned_rules() -> None:
    validator = StackContractValidator(
        (
            StackContractRule(
                name="python",
                stack_ids=frozenset({"fastapi"}),
                extensions=frozenset({".py"}),
                roles=frozenset({"entry"}),
                callback=lambda path, content: (f"{path}:python",),
            ),
            StackContractRule(
                name="empty",
                stack_ids=frozenset({"fastapi"}),
                extensions=frozenset({".py"}),
                callback=lambda _path, content: ("empty",) if not content else (),
            ),
        )
    )

    assert validator.validate("app.py", "value = 1\n", stack_id="fastapi", role="entry") == (
        "app.py:python",
    )
    assert validator.validate("app.py", "", stack_id="fastapi", role="model") == ("empty",)
    assert validator.validate("app.py", "value = 1\n", stack_id="express") == ()


def test_builtin_stack_adapters_declare_contract_scopes() -> None:
    scopes = {
        adapter.stack_id: adapter.contract_scope()
        for adapter in (
            FastAPIStackAdapter(),
            ExpressStackAdapter(),
            GoStackAdapter(),
            SpringStackAdapter(),
        )
    }

    assert scopes["fastapi"][1] == frozenset({".py"})
    assert scopes["express"][1] == frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
    assert scopes["go-stdlib"][1] == frozenset({".go"})
    assert scopes["spring"][1] == frozenset({".java", ".xml"})


def test_stack_repair_strategy_registry_preserves_order_and_rejects_duplicates() -> None:
    registry = StackRepairStrategyRegistry(
        (
            StackRepairStrategy("first", lambda path: None),
            StackRepairStrategy("second", lambda path: "fixed" if path == "main.py" else None),
        )
    )

    selected = registry.select("main.py")
    assert selected is not None
    assert selected[0].name == "second"
    assert selected[1] == "fixed"
    assert registry.names() == ("first", "second")

    with pytest.raises(ValueError, match="unique"):
        StackRepairStrategyRegistry(
            (StackRepairStrategy("same", lambda _path: None), StackRepairStrategy("same", lambda _path: None))
        )
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
