import logging
import time
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException

from app.utils.security import verify_token

from .schemas import (
    RequirementAssociationRequest,
    RequirementAssociationConfirmRequest,
    RequirementAssociationHelpfulnessRequest,
    RequirementAssociationResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/requirement-association", response_model=RequirementAssociationResponse)
async def requirement_association(
    request: RequirementAssociationRequest,
    token: dict = Depends(verify_token),
):
    if request.skip_association:
        return RequirementAssociationResponse(
            skipped=True,
            skip_reason="用户主动跳过联想环节"
        )

    from app.agent.orchestrator_requirements import RequirementAssociationMixin
    from app.agent.complexity import ComplexityAnalyzer

    complexity_level = request.complexity_level
    if not complexity_level:
        analyzer = ComplexityAnalyzer()
        analysis = analyzer.analyze(request.requirement)
        complexity_level = analysis.level.value

    mixin = RequirementAssociationMixin()
    mixin.callback = None
    mixin._start_time = time.time()
    mixin._current_phase = "requirement_association"

    result = await mixin._generate_requirement_associations(
        request.requirement, complexity_level
    )

    classified = mixin._classify_items_for_display(result.items) if result.items else {}

    items_dicts = []
    for item in result.items:
        items_dicts.append({
            "content": item.content,
            "category": item.category,
            "source": item.source,
            "confidence": item.confidence,
            "sub_category": item.sub_category,
            "impact": item.impact,
            "dual_model_agreement": item.dual_model_agreement,
            "devil_review": item.devil_review,
        })

    return RequirementAssociationResponse(
        skipped=result.skipped,
        skip_reason=result.skip_reason if result.skipped else None,
        domain_matched=result.domain_matched,
        domains_matched=result.domains_matched,
        items=items_dicts,
        classified_items=classified,
        enhanced_requirement=result.enhanced_requirement,
        devil_review_items=result.devil_review_items,
        elapsed_seconds=result.elapsed_seconds
    )


@router.post("/requirement-association/confirm")
async def requirement_association_confirm(
    association_id: int,
    token: dict = Depends(verify_token),
):
    from app.agent.orchestrator_requirements import AssociationFeedbackTracker
    from datetime import datetime

    tracker = AssociationFeedbackTracker()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    tracker.record_feedback(association_id, "accepted")

    return {
        "success": True,
        "association_id": association_id,
    }


@router.post("/requirement-association/helpfulness")
async def requirement_association_helpfulness(
    association_id: int,
    helpful: bool,
    token: dict = Depends(verify_token),
):
    from app.agent.orchestrator_requirements import AssociationFeedbackTracker

    tracker = AssociationFeedbackTracker()
    tracker.record_helpfulness(association_id, helpful)

    return {
        "success": True,
        "association_id": association_id,
        "helpful": helpful,
    }


@router.get("/requirement-association/stats")
async def requirement_association_stats(
    token: dict = Depends(verify_token),
):
    from app.agent.orchestrator_requirements import AssociationFeedbackTracker

    tracker = AssociationFeedbackTracker()
    stats = tracker.get_feedback_stats()
    rejection_reasons = tracker.get_rejection_reason_stats()

    return {
        "feedback_stats": stats,
        "rejection_reason_stats": rejection_reasons,
    }