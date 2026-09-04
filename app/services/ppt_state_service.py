"""SQL persistence for PPT outlines, quality reports and task metadata."""

import asyncio

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.ppt_agent import PPTAgent, PresentationOutline
from app.models.file import File
from app.models.ppt_state import PPTOutline, PPTQualityReport
from app.models.task import Task
from app.schema.ppt_outline import OutlineCreateRequest, OutlineDraft, OutlineSlide, OutlineUpdateRequest
from app.services.unified_state_service import StateNotFoundError, StateOwnershipError
from app.utils.aicloud.knowledge_processor import parse_document
from app.utils.web_search import FreeWebSearch
from app.utils.pptx.commercial_content import build_commercial_page_blueprint
from app.utils.pptx.scenario import classify_scenario


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


_SEMANTIC_SLIDE_TYPES = {
    "title": "cover",
    "chapter": "section",
    "content": "key_points",
    "bullet": "key_points",
    "image": "image_text",
    "chart": "data",
    "end": "closing",
}


async def _load_materials(
    db: AsyncSession,
    user_id: int,
    material_file_ids: list[int],
) -> list[dict[str, Any]]:
    unique_ids = list(dict.fromkeys(material_file_ids))
    if not unique_ids:
        return []

    rows = (
        await db.scalars(
            select(File).where(
                File.id.in_(unique_ids),
                File.user_id == user_id,
                File.is_deleted == 0,
            )
        )
    ).all()
    rows_by_id = {row.id: row for row in rows}
    if any(file_id not in rows_by_id for file_id in unique_ids):
        raise StateNotFoundError("素材文件不存在")

    materials = []
    for file_id in unique_ids:
        row = rows_by_id[file_id]
        try:
            content = row.parsed_content if row.is_parse_cache_valid() else await asyncio.to_thread(
                parse_document, row.file_path
            )
        except Exception as exc:
            raise ValueError(f"无法解析素材文件: {row.filename}") from exc

        content = content.strip()
        if not content:
            raise ValueError(f"素材文件没有可提取的文本: {row.filename}")
        if not row.is_parse_cache_valid():
            row.update_parse_cache(content)
        materials.append({"id": row.id, "filename": row.filename, "content": content[:12000]})
    return materials


def _agent_slides(outline: PresentationOutline) -> list[dict[str, Any]]:
    slides = []
    for index, slide in enumerate(outline.slides):
        key_message = next((item.strip() for item in slide.bullets if item.strip()), slide.title.strip())
        content_blocks = slide.content_blocks or [
            {"type": "text", "content": item, "metadata": {}}
            for item in slide.bullets
            if item.strip()
        ]
        if not content_blocks:
            content_blocks = [{"type": "text", "content": key_message or outline.title, "metadata": {}}]
        asset_intent = None
        if slide.image_keywords:
            asset_intent = {
                "description": f"{slide.title}配图",
                "keywords": slide.image_keywords[:12],
                "asset_type": "illustration",
            }
        slides.append(
            {
                "id": f"slide-{index + 1}",
                "position": index,
                "slide_type": _SEMANTIC_SLIDE_TYPES.get(slide.type, slide.type),
                "title": slide.title or outline.title,
                "key_message": key_message or outline.title,
                "content_blocks": content_blocks,
                "asset_intent": asset_intent,
                "narrative_role": slide.narrative_role or "opportunity_map",
                "evidence_sources": [],
                "speaker_notes": slide.notes,
            }
        )
    return slides


def _blueprint_slides(topic: str, count: int) -> list[dict[str, Any]]:
    blueprint = build_commercial_page_blueprint(topic)
    return [
        {
            "id": f"slide-{index + 1}",
            "position": index,
            "slide_type": blueprint[index % len(blueprint)]["slide_type"],
            "title": blueprint[index % len(blueprint)]["title"],
            "key_message": blueprint[index % len(blueprint)]["key_message"],
            "content_blocks": blueprint[index % len(blueprint)]["blocks"],
            "asset_intent": blueprint[index % len(blueprint)]["asset_intent"],
            "narrative_role": blueprint[index % len(blueprint)]["role"],
            "evidence_sources": [],
            "speaker_notes": "",
        }
        for index in range(count)
    ]


def _apply_material_evidence(slides: list[dict[str, Any]], materials: list[dict[str, Any]]) -> None:
    content_slides = [slide for slide in slides if slide["slide_type"] not in {"cover", "closing"}] or slides
    for index, material in enumerate(materials):
        slide = content_slides[index % len(content_slides)]
        excerpt = " ".join(material["content"].split())[:500]
        source = {
            "source_type": "uploaded_file",
            "material_file_id": material["id"],
            "title": material["filename"],
        }
        slide["evidence_sources"] = [source, *slide.get("evidence_sources", [])][:6]
        if slide["content_blocks"]:
            slide["content_blocks"][0] = {
                "type": "evidence",
                "content": excerpt,
                "metadata": {"material_file_id": material["id"], "source": material["filename"]},
            }


async def _build_outline_slides(
    request: OutlineCreateRequest,
    materials: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    topic = request.topic.strip()
    slides = _blueprint_slides(topic, request.num_slides)
    title = topic
    if request.api_key_token:
        material_context = "\n\n".join(
            f"[{material['filename']}]\n{material['content']}" for material in materials
        )
        description = "\n\n".join(part for part in (request.description.strip(), material_context) if part)
        outline = await PPTAgent(model=request.model or None).generate_outline(
            topic=topic,
            description=description[:24000],
            num_slides=request.num_slides,
            api_key_token=request.api_key_token,
        )
        title = outline.title or topic
        slides = _agent_slides(outline)
    _apply_material_evidence(slides, materials)
    return title, slides


async def create_ppt_outline(db: AsyncSession, user_id: str, request: OutlineCreateRequest) -> OutlineDraft:
    numeric_user_id = _user_id(user_id)
    outline_id = str(uuid4())
    now = datetime.utcnow()
    topic = request.topic.strip()
    materials = await _load_materials(db, numeric_user_id, request.material_file_ids)
    evidence_sources = []
    try:
        evidence_sources = [
            result.to_dict()
            for result in await FreeWebSearch().search(f"{topic} 行业市场数据案例趋势", count=5)
            if result.url
        ]
    except Exception:
        evidence_sources = []
    title, slides = await _build_outline_slides(request, materials)
    for index, slide in enumerate(slides):
        slide["evidence_sources"] = [
            *slide.get("evidence_sources", []),
            *(evidence_sources[index:index + 1] if index < len(evidence_sources) else []),
        ][:6]
    row = PPTOutline(
        record_id=str(uuid4()),
        outline_id=outline_id,
        user_id=numeric_user_id,
        version=1,
        status="draft",
        title=title,
        scenario=request.scenario or classify_scenario(f"{topic} {request.description}").scenario,
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


async def delete_ppt_outline(db: AsyncSession, user_id: str, outline_id: str) -> None:
    numeric_user_id = _user_id(user_id)
    await get_ppt_outline(db, user_id, outline_id)
    await db.execute(
        delete(PPTOutline).where(
            PPTOutline.outline_id == outline_id,
            PPTOutline.user_id == numeric_user_id,
        )
    )
    await db.commit()


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
        or not any(block.content.strip() for block in slide.content_blocks)
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
