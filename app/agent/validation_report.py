"""Structured cloud validation results and bounded repair evidence."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .repair_router import RepairBudget, RepairRoute, RepairRouter


class ValidationCategory(str, Enum):
    SYNTAX = "syntax"
    IMPORT = "import"
    DEPENDENCY = "dependency"
    EXPORT = "export"
    SIGNATURE = "signature"
    ASYNC = "async"
    TYPE = "type"
    FRAMEWORK = "framework"
    TEST = "test"
    PERSISTENCE = "persistence"
    BUSINESS = "business"
    UNKNOWN = "unknown"


class ValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ValidationCategory
    message: str = Field(min_length=1)
    file_path: Optional[str] = None
    scope: str = "cloud_syntax"
    code: Optional[str] = None
    context_hash: str = Field(min_length=64, max_length=64)


class RepairEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ValidationCategory
    repairer: str
    attempt: int = Field(ge=1)
    context_hash: str = Field(min_length=64, max_length=64)
    candidate_hash: str = Field(min_length=64, max_length=64)
    applied: bool


class ValidationReport(BaseModel):
    """One report for a validation pass and its bounded repair history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = "cloud"
    findings: Tuple[ValidationFinding, ...] = ()
    repair_evidence: Tuple[RepairEvidence, ...] = ()
    report_hash: str = Field(min_length=64, max_length=64)

    @classmethod
    def create(
        cls,
        findings: Iterable[ValidationFinding] = (),
        repair_evidence: Iterable[RepairEvidence] = (),
        *,
        source: str = "cloud",
    ) -> "ValidationReport":
        normalized_findings = tuple(findings)
        normalized_repairs = tuple(repair_evidence)
        return cls(
            source=source,
            findings=normalized_findings,
            repair_evidence=normalized_repairs,
            report_hash=_hash_payload(
                source,
                [item.model_dump(mode="json") for item in normalized_findings],
                [item.model_dump(mode="json") for item in normalized_repairs],
            ),
        )

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def scopes(self) -> Tuple[str, ...]:
        return tuple(sorted({finding.scope for finding in self.findings}))

    def with_finding(
        self,
        message: str,
        *,
        category: Optional[ValidationCategory] = None,
        file_path: Optional[str] = None,
        scope: str = "cloud_syntax",
        code: Optional[str] = None,
    ) -> "ValidationReport":
        resolved = category or ValidationCategory(RepairRouter.route(error_message=message).category)
        finding = ValidationFinding(
            category=resolved,
            message=message,
            file_path=file_path,
            scope=scope,
            code=code,
            context_hash=_hash_payload(scope, file_path, message),
        )
        return self.create(
            self.findings + (finding,),
            self.repair_evidence,
            source=self.source,
        )

    def authorize_repair(
        self,
        finding: ValidationFinding,
        candidate: str,
        budget: RepairBudget,
    ) -> tuple[RepairRoute, Optional[RepairEvidence]]:
        route = RepairRouter.route(finding.category.value, finding.message)
        if not route.auto_apply or not budget.consume(finding.category.value):
            return route, None
        evidence = RepairEvidence(
            category=finding.category,
            repairer=route.repairer,
            attempt=budget.used_by_category[finding.category.value],
            context_hash=finding.context_hash,
            candidate_hash=_hash_payload(candidate),
            applied=True,
        )
        return route, evidence


def _hash_payload(*values: Any) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
