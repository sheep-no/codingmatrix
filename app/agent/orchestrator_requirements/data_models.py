from dataclasses import dataclass, field
from typing import List


@dataclass
class AssociationItem:
    content: str
    category: str
    source: str
    confidence: float
    sub_category: str = ""
    impact: str = ""
    user_action: str = ""
    rejection_reason: str = ""
    dual_model_agreement: str = ""
    devil_review: str = ""


@dataclass
class AssociationResult:
    items: List[AssociationItem] = field(default_factory=list)
    enhanced_requirement: str = ""
    domain_matched: str = ""
    domains_matched: List[str] = field(default_factory=list)
    history_matched_count: int = 0
    llm_called: bool = False
    dual_model_used: bool = False
    devil_review_items: List[dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
