"""StrategyRouter 未覆盖策略分支补测。"""

from app.agent.code_synthesis_contracts import (
    ArtifactSpec,
    GenerationStrategy,
    ProjectModel,
)
from app.agent.strategy_router import StrategyRouter


def _artifact(path="src/api.py", *, strategy=GenerationStrategy.LLM, owner="stack-adapter", operation="create"):
    return ArtifactSpec(
        path=path,
        role="module",
        owner=owner,
        operation=operation,
        strategy=strategy,
        validation_profile="python",
        source="request",
    )


def test_delete_and_rename_route_to_patch():
    router = StrategyRouter()
    project = ProjectModel(language="python")

    for operation in ("delete", "rename"):
        decision = router.decide(project, _artifact(operation=operation))
        assert decision.strategy is GenerationStrategy.PATCH
        assert decision.capability_evidence == ("transactional-edit",)


def test_existing_artifact_without_structural_editor_degrades_to_llm():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("src/api.xyz", strategy=GenerationStrategy.LLM),
        existing_paths=("src/api.xyz",),
    )

    assert decision.strategy is GenerationStrategy.LLM
    assert decision.degraded is True
    assert decision.capability_evidence == ("generic-text-edit",)


def test_scaffold_contract_hint_without_capability_uses_contract_evidence():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("package.json", strategy=GenerationStrategy.SCAFFOLD),
        contracts={"scaffolder": "custom"},
    )

    assert decision.strategy is GenerationStrategy.SCAFFOLD
    assert decision.capability_evidence == ("contract-scaffolder",)
    assert decision.degraded is False


def test_scaffold_without_capability_or_contract_degrades():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("package.json", strategy=GenerationStrategy.SCAFFOLD),
    )

    assert decision.strategy is GenerationStrategy.LLM
    assert decision.degraded is True
    assert "scaffolder" in decision.capability_evidence


def test_schema_codegen_with_data_contract_succeeds():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("generated/models.py", strategy=GenerationStrategy.SCHEMA_CODEGEN),
        contracts={"data": {"tables": []}},
    )

    assert decision.strategy is GenerationStrategy.SCHEMA_CODEGEN
    assert decision.capability_evidence == ("schema-contract",)


def test_template_without_deterministic_owner_degrades():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("src/template.py", strategy=GenerationStrategy.TEMPLATE, owner="model"),
    )

    assert decision.strategy is GenerationStrategy.LLM
    assert decision.degraded is True
    assert decision.capability_evidence == ("template-provider",)


def test_template_with_deterministic_owner_succeeds():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("src/template.py", strategy=GenerationStrategy.TEMPLATE),
    )

    assert decision.strategy is GenerationStrategy.TEMPLATE
    assert decision.capability_evidence == ("template-provider",)


def test_patch_with_structural_editor_succeeds():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="python"),
        _artifact("src/api.py", strategy=GenerationStrategy.PATCH),
    )

    assert decision.strategy is GenerationStrategy.PATCH
    assert decision.degraded is False
    assert decision.capability_evidence


def test_plain_llm_artifact_keeps_bounded_reasoning():
    router = StrategyRouter()

    decision = router.decide(
        ProjectModel(language="unknown"),
        _artifact("src/api.xyz", strategy=GenerationStrategy.LLM),
    )

    assert decision.strategy is GenerationStrategy.LLM
    assert decision.degraded is False
    assert decision.capability_evidence == ("bounded-llm-edit",)
