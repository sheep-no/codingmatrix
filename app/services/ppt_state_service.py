"""SQL persistence for PPT outlines, quality reports and task metadata."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ppt_state import PPTOutline, PPTQualityReport
from app.models.task import Task
from app.schema.ppt_outline import OutlineCreateRequest, OutlineDraft, OutlineSlide, OutlineUpdateRequest
from app.services.unified_state_service import StateNotFoundError, StateOwnershipError
from app.utils.web_search import FreeWebSearch
from app.utils.pptx.commercial_content import build_commercial_page_blueprint


def _user_id(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise StateOwnershipError("用户身份无法用于持久化 PPT 状态") from exc


def _to_contract(row: PPTOutline) -> OutlineDraft:
    return OutlineDraft(
        id=row.outline_id,
        user_id=str(row.user_id),
        version=row.version,
        status=row.status,
        title=row.title,
        scenario=row.scenario,
        template_id=row.template_id,
        slide_limit=row.slide_limit,
        slides=[OutlineSlide.model_validate(slide) for slide in row.slides_json],
        created_at=row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        approved_at=(row.approved_at.replace(tzinfo=timezone.utc).isoformat() if row.approved_at else None),
    )


async def create_ppt_outline(db: AsyncSession, user_id: str, request: OutlineCreateRequest) -> OutlineDraft:
    numeric_user_id = _user_id(user_id)
    outline_id = str(uuid4())
    now = datetime.utcnow()
    topic = request.topic.strip()
    evidence_sources = []
    try:
        evidence_sources = [
            result.to_dict()
            for result in await FreeWebSearch().search(f"{topic} 行业市场数据案例趋势", count=5)
            if result.url
        ]
    except Exception:
        evidence_sources = []
    page_blueprint = build_commercial_page_blueprint(topic)
    slides = [
        {
            "id": f"slide-{index + 1}",
            "position": index,
            "slide_type": page_blueprint[index % len(page_blueprint)]["slide_type"],
            "title": page_blueprint[index % len(page_blueprint)]["title"],
            "key_message": page_blueprint[index % len(page_blueprint)]["key_message"],
            "content_blocks": page_blueprint[index % len(page_blueprint)]["blocks"],
            "asset_intent": page_blueprint[index % len(page_blueprint)]["asset_intent"],
            "narrative_role": page_blueprint[index % len(page_blueprint)]["role"],
            "evidence_sources": evidence_sources[index:index + 1] if index < len(evidence_sources) else [],
            "speaker_notes": "",
        }
        for index in range(request.num_slides)
    ]
    row = PPTOutline(
        record_id=str(uuid4()),
        outline_id=outline_id,
        user_id=numeric_user_id,
        version=1,
        status="draft",
        title=topic,
        scenario=request.scenario,
        template_id=request.template_id,
        slide_limit=request.num_slides,
        slides_json=slides,
        created_at=now,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return _to_contract(row)


async def get_ppt_outline(
    db: AsyncSession, user_id: str, outline_id: str, version: Optional[int] = None
) -> OutlineDraft:
    query = select(PPTOutline).where(
        PPTOutline.outline_id == outline_id,
        PPTOutline.user_id == _user_id(user_id),
    )
    query = query.where(PPTOutline.version == version) if version else query.order_by(desc(PPTOutline.version))
    row = await db.scalar(query)
    if not row:
        raise StateNotFoundError("大纲不存在")
    return _to_contract(row)


async def update_ppt_outline(
    db: AsyncSession, user_id: str, outline_id: str, request: OutlineUpdateRequest
) -> OutlineDraft:
    current = await get_ppt_outline(db, user_id, outline_id)
    next_data: dict[str, Any] = current.model_dump()
    next_data.update(request.model_dump(exclude_unset=True))
    next_data["version"] = current.version + 1
    next_data["status"] = "draft"
    next_data["approved_at"] = None
    row = PPTOutline(
        record_id=str(uuid4()),
        outline_id=outline_id,
        user_id=_user_id(user_id),
        version=next_data["version"],
        status="draft",
        title=next_data["title"],
        scenario=next_data["scenario"],
        template_id=next_data["template_id"],
        slide_limit=current.slide_limit,
        slides_json=[
            OutlineSlide.model_validate(slide).model_dump(mode="json")
            for slide in next_data["slides"]
        ],
        created_at=datetime.utcnow(),
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return _to_contract(row)


async def approve_ppt_outline(db: AsyncSession, user_id: str, outline_id: str) -> OutlineDraft:
    current = await get_ppt_outline(db, user_id, outline_id)
    invalid = [
        slide.id
        for slide in current.slides
        if not slide.title.strip()
        or not slide.key_message.strip()
        or (not slide.content_blocks and not slide.asset_intent)
    ]
    if invalid:
        raise ValueError(f"大纲包含未完成页面: {','.join(invalid)}")
    row = await db.scalar(
        select(PPTOutline).where(
            PPTOutline.outline_id == outline_id,
            PPTOutline.user_id == _user_id(user_id),
            PPTOutline.version == current.version,
        )
    )
    row.status = "approved"
    row.approved_at = datetime.utcnow()
    await db.flush()
    await db.commit()
    return _to_contract(row)


async def save_ppt_quality_report(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    outline_id: str,
    outline_version: int,
    quality_mode: str,
    template_id: str,
    template_version: str,
    overall_score: int,
    slide_scores: dict[str, float],
    issues: list[dict[str, Any]],
    reflow_attempts: dict[str, int],
    degraded_stage: Optional[str] = None,
) -> PPTQualityReport:
    task = await db.scalar(select(Task).where(Task.task_id == task_id, Task.user_id == int(user_id)))
    if not task:
        raise StateNotFoundError("任务不存在")
    report = PPTQualityReport(
        id=str(uuid4()),
        task_id=task_id,
        user_id=int(user_id),
        outline_id=outline_id,
        outline_version=outline_version,
        quality_mode=quality_mode,
        template_id=template_id,
        template_version=template_version,
        overall_score=max(0, min(100, int(overall_score))),
        slide_scores_json=slide_scores,
        issues_json=issues,
        reflow_attempts_json=reflow_attempts,
        degraded_stage=degraded_stage,
    )
    task.outline_id = outline_id
    task.outline_version = outline_version
    task.quality_mode = quality_mode
    db.add(report)
    await db.flush()
    await db.commit()
    return report


async def get_ppt_quality_report(db: AsyncSession, task_id: str, user_id: int) -> PPTQualityReport:
    report = await db.scalar(
        select(PPTQualityReport)
        .where(PPTQualityReport.task_id == task_id, PPTQualityReport.user_id == int(user_id))
        .order_by(desc(PPTQualityReport.version))
    )
    if not report:
        raise StateNotFoundError("质量报告不存在")
    return report
