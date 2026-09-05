"""Capability registry for technology-neutral synthesis strategy selection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .code_synthesis_contracts import ProjectModel
from .languages import get_language_adapter, get_language_capabilities
from .scaffolding import ScaffoldRequest, official_scaffold_request, supports_official_scaffold


class SynthesisCapabilitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parser: bool = False
    structural_editor: bool = False
    signatures: bool = False
    compiler: bool = False
    test_runner: bool = False
    scaffolder: bool = False
    evidence: tuple[str, ...] = ()


class SynthesisCapabilityRegistry:
    """Resolve language and scaffold capabilities through existing registries."""

    def inspect(self, project: ProjectModel) -> SynthesisCapabilitySnapshot:
        language = get_language_capabilities(project.language)
        adapter = get_language_adapter(project.language)
        dedicated_adapter = language.language != "generic" and adapter.language != "generic"
        scaffolder = supports_official_scaffold(project.language, project.framework)
        evidence = []
        if dedicated_adapter:
            evidence.append(f"language-adapter:{adapter.language}")
        if language.supports_ast and dedicated_adapter:
            evidence.append("parser")
        if language.supports_signatures and dedicated_adapter:
            evidence.append("signatures")
        if language.supports_compile:
            evidence.append("compiler")
        if language.supports_tests:
            evidence.append("test-runner")
        if scaffolder:
            evidence.append(f"official-scaffolder:{project.framework}")
        return SynthesisCapabilitySnapshot(
            parser=language.supports_ast and dedicated_adapter,
            structural_editor=language.supports_ast and dedicated_adapter,
            signatures=language.supports_signatures and dedicated_adapter,
            compiler=language.supports_compile,
            test_runner=language.supports_tests,
            scaffolder=scaffolder,
            evidence=tuple(evidence),
        )

    def scaffold_request(self, project: ProjectModel, target_dir: str) -> ScaffoldRequest:
        """Return the reviewed fixed-version command for a supported project stack."""
        return official_scaffold_request(project.language, project.framework, target_dir)


__all__ = ["SynthesisCapabilityRegistry", "SynthesisCapabilitySnapshot"]
