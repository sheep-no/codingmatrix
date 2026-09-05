"""Select constrained generation strategies from project and artifact facts."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .code_synthesis_contracts import (
    ArtifactSpec,
    ChangePlanIR,
    GenerationStrategy,
    ProjectModel,
    StrategyDecision,
)
from .synthesis_capabilities import SynthesisCapabilityRegistry


class StrategyRouter:
    """Route each artifact to the narrowest available generation strategy."""

    def __init__(self, capabilities: SynthesisCapabilityRegistry | None = None) -> None:
        self.capabilities = capabilities or SynthesisCapabilityRegistry()

    def decide(
        self,
        project: ProjectModel,
        artifact: ArtifactSpec,
        *,
        existing_paths: Iterable[str] = (),
        contracts: Mapping[str, Any] | None = None,
    ) -> StrategyDecision:
        existing = set(existing_paths)
        contract_data = contracts or {}
        capabilities = self.capabilities.inspect(project)

        if artifact.operation in {"delete", "rename"}:
            return StrategyDecision(
                strategy=GenerationStrategy.PATCH,
                reason="file lifecycle changes require transactional structural edits",
                capability_evidence=("transactional-edit",),
            )

        if artifact.operation == "modify" or artifact.path in existing:
            if capabilities.structural_editor:
                return StrategyDecision(
                    strategy=GenerationStrategy.PATCH,
                    reason="an existing artifact should receive a bounded local edit",
                    capability_evidence=capabilities.evidence,
                )
            return StrategyDecision(
                strategy=GenerationStrategy.LLM,
                reason="existing artifact has no registered structural editor",
                capability_evidence=("generic-text-edit",),
                degraded=True,
            )

        if artifact.strategy is GenerationStrategy.SCAFFOLD:
            if "scaffolder" in contract_data or capabilities.scaffolder:
                return StrategyDecision(
                    strategy=GenerationStrategy.SCAFFOLD,
                    reason="artifact requests a registered project scaffolder",
                    capability_evidence=(
                        capabilities.evidence
                        if capabilities.scaffolder
                        else ("contract-scaffolder",)
                    ),
                )
            return self._degraded_decision(
                "requested scaffolding capability is unavailable", "scaffolder"
            )

        if artifact.strategy is GenerationStrategy.SCHEMA_CODEGEN:
            if contract_data.get("api") or contract_data.get("data") or contract_data.get("schema"):
                return StrategyDecision(
                    strategy=GenerationStrategy.SCHEMA_CODEGEN,
                    reason="a declared schema contract is available for deterministic derivation",
                    capability_evidence=("schema-contract",),
                )
            return self._degraded_decision(
                "schema code generation has no declared source contract", "schema-contract"
            )

        if artifact.strategy is GenerationStrategy.TEMPLATE:
            if artifact.owner and artifact.owner != "model":
                return StrategyDecision(
                    strategy=GenerationStrategy.TEMPLATE,
                    reason="artifact is owned by a deterministic stack or template provider",
                    capability_evidence=("template-provider",),
                )
            return self._degraded_decision(
                "template artifact has no deterministic owner", "template-provider"
            )

        if artifact.strategy is GenerationStrategy.PATCH:
            if capabilities.structural_editor:
                return StrategyDecision(
                    strategy=GenerationStrategy.PATCH,
                    reason="artifact explicitly requests a supported structural patch",
                    capability_evidence=capabilities.evidence,
                )
            return self._degraded_decision(
                "requested structural patch capability is unavailable",
                "language-structural-editor",
            )

        return StrategyDecision(
            strategy=GenerationStrategy.LLM,
            reason="artifact requires bounded model reasoning after deterministic strategies are unavailable",
            capability_evidence=("bounded-llm-edit",),
        )

    def route_plan(
        self,
        plan: ChangePlanIR,
        *,
        existing_paths: Iterable[str] = (),
    ) -> dict[str, StrategyDecision]:
        """Return decisions for every dynamic artifact in a plan."""
        return {
            artifact.path: self.decide(
                plan.project,
                artifact,
                existing_paths=existing_paths,
                contracts=plan.contracts,
            )
            for artifact in plan.artifacts
        }

    @staticmethod
    def _degraded_decision(reason: str, evidence: str) -> StrategyDecision:
        return StrategyDecision(
            strategy=GenerationStrategy.LLM,
            reason=reason,
            capability_evidence=(evidence,),
            degraded=True,
        )


__all__ = ["StrategyRouter"]
