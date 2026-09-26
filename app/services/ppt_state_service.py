"""SQL persistence for PPT outlines, quality reports and task metadata."""

import asyncio
from typing import Any, AsyncIterator, Optional

from datetime import timezone
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.ppt_agent import PPTAgent, PresentationOutline, SlideOutline
from app.core.time import utcnow_naive
from app.models.file import File
from app.models.ppt_state import PPTOutline, PPTQualityReport
from app.models.task import Task
from app.schema.ppt_outline import OutlineCreateRequest, OutlineDraft, OutlineSlide, OutlineUpdateRequest
from app.services.unified_state_service import StateNotFoundError, StateOwnershipError
from app.utils.aicloud.knowledge_processor import parse_document
from app.utils.web_search import FreeWebSearch
from app.utils.pptx.commercial_content import build_commercial_page_blueprint, key_message_repeats_body
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

OUTLINE_STREAM_STAGES = (
    ("analyzing", "分析主题与受众"),
    ("retrieving", "检索参考资料"),
    ("drafting", "起草页面结构"),
    ("assembling", "整理可编辑大纲"),
)


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
        key_message = (slide.key_message or "").strip()
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
                "key_message": key_message,
                "content_blocks": content_blocks,
                "asset_intent": asset_intent,
                "narrative_role": slide.narrative_role or "opportunity_map",
                "evidence_sources": [],
                "speaker_notes": slide.notes,
            }
        )
    return slides


def _editable_agent_slides(outline: PresentationOutline) -> list[dict[str, Any]]:
    """Keep editable pages while the renderer owns the presentation cover."""
    slides = _agent_slides(outline)
    if slides and slides[0]["slide_type"] == "cover":
        slides = slides[1:]
    slides = [slide for slide in slides if not _is_closing_slide(slide)]
    if not slides:
        slides = _blueprint_slides(outline.title, 5)
    return _sanitize_editable_slides(slides, outline.title)


def _is_closing_slide(slide: dict[str, Any]) -> bool:
    if slide.get("slide_type") in {"closing", "end"}:
        return True
    text = f"{slide.get('title') or ''} {slide.get('key_message') or ''}"
    return any(marker in text for marker in ("谢谢", "感谢聆听", "谢谢观看"))


_CHART_MARKERS = (
    "饼图",
    "柱状图",
    "折线图",
    "甘特图",
    "热力图",
    "矩阵图",
    "示意图",
    "架构图",
    "趋势图",
    "对比图",
    "分布图",
    "流程图",
    "结构图",
)

_VISUAL_SUFFIXES = (
    "数据表格",
    "分布表",
    "对比表",
    "增长曲线",
    "时间轴",
    "路径图",
    "曲线",
    "列表",
    "表格",
    "模型",
    "矩阵",
    "清单",
)

_CLAIM_MARKERS = (
    "将",
    "已从",
    "已将",
    "已经",
    "已把",
    "需要",
    "必须",
    "应当",
    "完成",
    "导致",
    "引发",
    "提升",
    "降低",
    "升级",
    "实现",
    "建立",
    "打破",
    "超过",
    "达到",
    "可以",
    "能够",
    "建议",
    "优先",
    "聚焦",
)


def _contains_chart_marker(text: str) -> bool:
    return any(marker in (text or "") for marker in _CHART_MARKERS)


def _looks_like_visual_placeholder(text: str) -> bool:
    raw = _strip_instruction_prefix(text).rstrip("。；！、 ")
    if not raw:
        return True
    if _contains_chart_marker(raw):
        return True
    if any(raw.endswith(suffix) for suffix in _VISUAL_SUFFIXES) and len(raw) <= 24:
        return True
    if raw.endswith("图") and len(raw) <= 24:
        return True
    if len(raw) < 12:
        return True
    if ("，" in raw or "、" in raw or "," in raw) and len(raw) >= 12:
        return False
    return len(raw) <= 18 and not any(marker in raw for marker in _CLAIM_MARKERS)


def _strip_instruction_prefix(text: str) -> str:
    raw = (text or "").strip()
    for prefix in ("列出", "展示"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):].lstrip("：:，, ")
            break
    return raw.strip("，, ：:、 ")


def _noun_phrase_core(text: str) -> str:
    raw = (text or "").strip().rstrip("。；！、 ")
    for suffix in _VISUAL_SUFFIXES:
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    if raw.endswith("图"):
        raw = raw[:-1]
    for marker in _CHART_MARKERS:
        raw = raw.replace(marker, "")
    return raw.strip("，, ：:、 ")


def _normalize_claim_text(text: str) -> str:
    raw = (text or "").strip().rstrip("。；！、 ")
    for marker in _CLAIM_MARKERS:
        raw = raw.replace(marker, "")
    for token in ("的", "与", "和", "及", " "):
        raw = raw.replace(token, "")
    for suffix in ("成果", "情况", "分析", "建设", "案例"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    return raw


def _is_redundant_core(core: str, claim: str) -> bool:
    left = _normalize_claim_text(core)
    right = _normalize_claim_text(claim)
    if not left or not right:
        return True
    return left in right or right in left


def _expand_visual_placeholder(text: str, title: str, fallback: str) -> str:
    """Turn a chart or label placeholder into a page-specific statement.

    The page conclusion is deliberately kept out of the rewritten body, otherwise
    it would be rendered twice on the same page.
    """
    raw = (text or "").strip()
    remainder = ""
    for sep in ("，", ",", "：", ":"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            visual_left = (
                _contains_chart_marker(left)
                or left.endswith("图")
                or any(left.endswith(suffix) for suffix in _VISUAL_SUFFIXES)
            )
            if visual_left:
                remainder = _strip_instruction_prefix(right)
            break
    cleaned = _strip_instruction_prefix(raw)
    for marker in _CHART_MARKERS:
        cleaned = cleaned.replace(marker, "")
    cleaned = cleaned.strip("，, ：:、 ")
    if remainder and not _contains_chart_marker(remainder) and len(remainder) >= 16:
        return remainder if remainder.endswith(("。", "；", "！")) else f"{remainder}。"
    if remainder and not _contains_chart_marker(remainder) and len(remainder) >= 8:
        return f"{title}已能用{remainder}说明本页判断。"
    core = _noun_phrase_core(cleaned)
    if core and not _is_redundant_core(core, title):
        return f"{title}要把{core}转成可验收结果。"
    if fallback and len(fallback) >= 16:
        return fallback
    return f"{title}需要用可量化证据支撑下一阶段决策。"


def _sanitize_editable_slides(slides: list[dict[str, Any]], topic: str) -> list[dict[str, Any]]:
    blueprint = build_commercial_page_blueprint(topic)
    for index, slide in enumerate(slides):
        page = blueprint[index % len(blueprint)]
        fallback_blocks = page["blocks"]
        blocks = list(slide.get("content_blocks") or [])
        title = str(slide.get("title") or page["title"])
        key_message = str(slide.get("key_message") or "").strip()
        if key_message.startswith(("列出", "展示")):
            stripped = _strip_instruction_prefix(key_message)
            if stripped:
                key_message = stripped
        block_texts = [str(block.get("content") or "") for block in blocks]
        if (
            not key_message
            or _looks_like_visual_placeholder(key_message)
            or key_message_repeats_body(key_message, block_texts)
        ):
            key_message = page["key_message"]
        slide["key_message"] = key_message
        sanitized: list[dict[str, Any]] = []
        target = max(len(blocks), 4)
        for i in range(target):
            fallback = fallback_blocks[i % len(fallback_blocks)]
            block = dict(blocks[i]) if i < len(blocks) else dict(fallback)
            content = str(block.get("content") or "").strip()
            if content.startswith(("列出", "展示")):
                stripped = _strip_instruction_prefix(content)
                if stripped:
                    content = stripped
                    block["content"] = content
            if _looks_like_visual_placeholder(content):
                block["content"] = _expand_visual_placeholder(
                    content, title, str(fallback.get("content") or "")
                )
            sanitized.append(block)
        slide["content_blocks"] = sanitized[:6]
        if not slide.get("asset_intent"):
            slide["asset_intent"] = page.get("asset_intent")
    return slides


def _stage_event(index: int) -> dict[str, Any]:
    key, label = OUTLINE_STREAM_STAGES[index]
    return {"type": "stage", "stage": key, "label": label, "index": index}


def _preview_from_raw_agent_slide(raw: dict[str, Any], index: int) -> Optional[dict[str, Any]]:
    slide_type = str(raw.get("type") or "content")
    if slide_type in {"title", "end"}:
        return None
    bullets = [item for item in (raw.get("bullets") or []) if str(item).strip()][:6]
    content_blocks = raw.get("content_blocks") or [
        {"type": "text", "content": item, "metadata": {}} for item in bullets
    ]
    outline = PresentationOutline(
        title=str(raw.get("title") or "PPT"),
        slides=[
            SlideOutline(
                type=slide_type,
                title=str(raw.get("title") or "").strip(),
                key_message=str(raw.get("key_message") or ""),
                bullets=bullets,
                image_keywords=list(raw.get("image_keywords") or [])[:3],
                notes=str(raw.get("notes") or ""),
                narrative_role=str(raw.get("narrative_role") or ""),
                content_blocks=content_blocks,
            )
        ],
    )
    if not outline.slides[0].title:
        return None
    converted = _agent_slides(outline)
    if not converted:
        return None
    slide = converted[0]
    if _is_closing_slide(slide):
        return None
    slide["id"] = f"slide-{index + 1}"
    slide["position"] = index
    return slide


def _attach_evidence(slides: list[dict[str, Any]], evidence_sources: list[dict[str, Any]]) -> None:
    for index, slide in enumerate(slides):
        slide["evidence_sources"] = [
            *slide.get("evidence_sources", []),
            *(evidence_sources[index:index + 1] if index < len(evidence_sources) else []),
        ][:6]


async def _persist_new_outline(
    db: AsyncSession,
    numeric_user_id: int,
    request: OutlineCreateRequest,
    title: str,
    slides: list[dict[str, Any]],
) -> OutlineDraft:
    topic = request.topic.strip()
    row = PPTOutline(
        record_id=str(uuid4()),
        outline_id=str(uuid4()),
        user_id=numeric_user_id,
        version=1,
        status="draft",
        title=title,
        scenario=request.scenario or classify_scenario(f"{topic} {request.description}").scenario,
        template_id=request.template_id,
        slide_limit=request.num_slides or max(1, len(slides) + 1),
        slides_json=slides,
        created_at=utcnow_naive(),
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return _to_contract(row)


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
    if not slides:
        return
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
    if request.num_slides is None:
        content_count = len(build_commercial_page_blueprint(topic))
    else:
        content_count = max(0, request.num_slides - 1)
    slides = _blueprint_slides(topic, content_count)
    title = topic
    if request.api_key_token:
        material_context = "\n\n".join(
            f"[{material['filename']}]\n{material['content']}" for material in materials
        )
        description = "\n\n".join(part for part in (request.description.strip(), material_context) if part)
        outline = await PPTAgent(model=request.model or None).generate_outline(
            topic=topic,
            description=description[:24000],
            num_slides=request.num_slides or 0,
            api_key_token=request.api_key_token,
        )
        title = outline.title or topic
        slides = _editable_agent_slides(outline)
    _apply_material_evidence(slides, materials)
    return title, slides


async def create_ppt_outline(db: AsyncSession, user_id: str, request: OutlineCreateRequest) -> OutlineDraft:
    numeric_user_id = _user_id(user_id)
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
    _attach_evidence(slides, evidence_sources)
    return await _persist_new_outline(db, numeric_user_id, request, title, slides)


async def stream_ppt_outline(
    db: AsyncSession, user_id: str, request: OutlineCreateRequest
) -> AsyncIterator[dict[str, Any]]:
    numeric_user_id = _user_id(user_id)
    topic = request.topic.strip()
    yield _stage_event(0)
    materials = await _load_materials(db, numeric_user_id, request.material_file_ids)
    yield _stage_event(1)
    evidence_sources: list[dict[str, Any]] = []
    try:
        evidence_sources = [
            result.to_dict()
            for result in await FreeWebSearch().search(f"{topic} 行业市场数据案例趋势", count=5)
            if result.url
        ]
    except Exception:
        evidence_sources = []
    yield _stage_event(2)

    title = topic
    slides: list[dict[str, Any]] = []
    if request.api_key_token:
        material_context = "\n\n".join(
            f"[{material['filename']}]\n{material['content']}" for material in materials
        )
        description = "\n\n".join(part for part in (request.description.strip(), material_context) if part)
        agent = PPTAgent(model=request.model or None)
        outline = None
        preview_index = 0
        async for event in agent.stream_outline(
            topic=topic,
            description=description[:24000],
            num_slides=request.num_slides,
            api_key_token=request.api_key_token,
        ):
            if event.get("type") == "retry":
                preview_index = 0
                yield event
                continue
            if event.get("type") == "slide":
                preview = _preview_from_raw_agent_slide(event.get("slide") or {}, preview_index)
                if preview:
                    yield {"type": "slide", "slide": preview, "index": preview_index}
                    preview_index += 1
                continue
            if event.get("type") == "complete":
                outline = event.get("outline")
        if isinstance(outline, PresentationOutline):
            title = outline.title or topic
            slides = _editable_agent_slides(outline)
        else:
            title, slides = await _build_outline_slides(request, materials)
    else:
        title, slides = await _build_outline_slides(request, materials)
        for index, slide in enumerate(slides):
            yield {"type": "slide", "slide": slide, "index": index}

    yield _stage_event(3)
    _attach_evidence(slides, evidence_sources)
    draft = await _persist_new_outline(db, numeric_user_id, request, title, slides)
    yield {"type": "done", "draft": draft.model_dump(mode="json")}


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
        created_at=utcnow_naive(),
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return _to_contract(row)


async def revise_ppt_slide(
    db: AsyncSession, user_id: str, outline_id: str, version: int, slide_id: str, slide: OutlineSlide
) -> OutlineDraft:
    """Branch an approved snapshot, retaining all other pages and prior versions."""
    base = await get_ppt_outline(db, user_id, outline_id, version)
    if base.status != "approved":
        raise ValueError("请先批准基准大纲")
    target = next((index for index, page in enumerate(base.slides) if page.id == slide_id), None)
    if target is None:
        raise StateNotFoundError("目标页面不存在")
    if not slide.title.strip() or not slide.key_message.strip() or not any(
        block.content.strip() for block in slide.content_blocks
    ):
        raise ValueError("请填写页面标题、核心结论和正文")
    pages = [page.model_dump(mode="json") for page in base.slides]
    pages[target] = slide.model_dump(mode="json")
    pages[target].update(id=slide_id, position=base.slides[target].position)
    latest = await get_ppt_outline(db, user_id, outline_id)
    row = PPTOutline(
        record_id=str(uuid4()), outline_id=outline_id, user_id=_user_id(user_id),
        version=latest.version + 1, status="approved", title=base.title,
        scenario=base.scenario, template_id=base.template_id, slide_limit=base.slide_limit,
        slides_json=pages, created_at=utcnow_naive(), approved_at=utcnow_naive(),
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
    row.approved_at = utcnow_naive()
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
