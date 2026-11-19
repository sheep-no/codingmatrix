"""
PPT 生成 API - 统一增强版

功能整合：
1. 合并原 aiGeneratorPptx.py 和 ppt_enhanced.py 的功能。
2. 支持会话历史、素材上传绑定、文件权限验证。
3. 支持视觉决策与智能布局 (Visual Decision & Layout)。
4. 支持多种输出格式 (PPTX, PDF, HTML, Markdown)。
5. 支持模板系统、在线预览、代码审查集成。
6. 提供同步/异步生成、下载、预览、幻灯片详情接口。
"""
import asyncio
import html
import json
import logging
import os
import re
import uuid
from datetime import datetime
from enum import Enum
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi import File as FastAPIFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import DEFAULT_PPT_MODEL
from app.celery_app import celery_app
from app.core.config import BASE_DIR
from app.db.database import async_session, get_db
from app.models.file import File
from app.models.task import Task
from app.schema.ppt_outline import (
    OutlineCreateRequest,
    OutlineDraft,
    OutlineGenerateRequest,
    OutlineUpdateRequest,
    SlideRegenerateRequest,
)
from app.schema.task_schema import TaskResponse
from app.services.ppt_generation_persistence import (
    build_ppt_trace_context,
    persist_ppt_generation_result,
    save_ppt_stage_checkpoint,
    serialize_quality_report,
)
from app.services.ppt_quality_orchestrator import run_quality_pipeline
from app.services.ppt_state_service import (
    approve_ppt_outline as persist_approve_ppt_outline,
)
from app.services.ppt_state_service import (
    create_ppt_outline as persist_create_ppt_outline,
)
from app.services.ppt_state_service import (
    delete_ppt_outline as persist_delete_ppt_outline,
)
from app.services.ppt_state_service import (
    get_ppt_outline as persist_get_ppt_outline,
)
from app.services.ppt_state_service import (
    get_ppt_quality_report as persist_get_ppt_quality_report,
)
from app.services.ppt_state_service import (
    revise_ppt_slide,
)
from app.services.ppt_state_service import (
    stream_ppt_outline as persist_stream_ppt_outline,
)
from app.services.ppt_state_service import (
    update_ppt_outline as persist_update_ppt_outline,
)
from app.services.unified_state_service import (
    StateNotFoundError,
    StateOwnershipError,
    get_owned_task,
    transition_task,
)
from app.utils.aicloud.llm_caller import LLMCallError
from app.utils.pptx.commercial_content import (
    NARRATIVE_ROLES,
    build_expanded_commercial_page_blueprint,
    key_message_repeats_body,
    resolve_topic_template,
)
from app.utils.pptx.composition_pool import select_cover_variant, select_layout_variants
from app.utils.pptx.ppt_style import PPT_TEMPLATES, PPTStyle, apply_design_tokens
from app.utils.pptx.semantic_renderer import build_render_metadata
from app.utils.pptx.templates.manager import TemplateManager

# PPT 工具模块
from app.utils.pptx.text_processor import (
    prevent_text_overflow as prevent_text_overflow_v2,
)
from app.utils.security import verify_token, verify_token_ws
from app.utils.task_manager import task_manager

# 视觉决策模块
from app.utils.visual import (
    ImageType,
    image_manager,
    visual_analyzer,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["PPT 生成 (增强版)"])
PPT_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post("/pptx/outlines", response_model=OutlineDraft, status_code=201)
async def create_ppt_outline(
    req: OutlineCreateRequest,
    http_request: Request,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """创建用户作用域的 PPT 大纲草稿。"""
    accept = (http_request.headers.get("accept") or "").lower()
    if "text/event-stream" in accept:
        async def event_stream():
            try:
                async for event in persist_stream_ppt_outline(
                    db, str(token.get("sub", "anonymous")), req
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            except StateNotFoundError:
                yield f"data: {json.dumps({'type': 'error', 'message': '素材文件不存在'}, ensure_ascii=False)}\n\n"
            except ValueError as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
            except LLMCallError as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
            except Exception:
                logger.exception("PPT outline stream failed")
                yield f"data: {json.dumps({'type': 'error', 'message': '大纲生成失败'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers=PPT_STREAM_HEADERS,
        )
    try:
        return await persist_create_ppt_outline(db, str(token.get("sub", "anonymous")), req)
    except StateNotFoundError:
        raise HTTPException(status_code=404, detail="素材文件不存在")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LLMCallError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/pptx/outlines/{outline_id}", response_model=OutlineDraft)
async def get_ppt_outline(
    outline_id: str,
    version: Optional[int] = Query(default=None, ge=1),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await persist_get_ppt_outline(db, str(token.get("sub", "anonymous")), outline_id, version)
    except (StateNotFoundError, StateOwnershipError):
        raise HTTPException(status_code=404, detail="大纲不存在")


@router.patch("/pptx/outlines/{outline_id}", response_model=OutlineDraft)
async def update_ppt_outline(
    outline_id: str,
    req: OutlineUpdateRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await persist_update_ppt_outline(db, str(token.get("sub", "anonymous")), outline_id, req)
    except (StateNotFoundError, StateOwnershipError):
        raise HTTPException(status_code=404, detail="大纲不存在")


@router.delete("/pptx/outlines/{outline_id}")
async def delete_ppt_outline(
    outline_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        await persist_delete_ppt_outline(db, str(token.get("sub", "anonymous")), outline_id)
    except (StateNotFoundError, StateOwnershipError):
        raise HTTPException(status_code=404, detail="大纲不存在")
    return {"deleted": True}


@router.post("/pptx/outlines/{outline_id}/approve", response_model=OutlineDraft)
async def approve_ppt_outline(
    outline_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await persist_approve_ppt_outline(db, str(token.get("sub", "anonymous")), outline_id)
    except (StateNotFoundError, StateOwnershipError):
        raise HTTPException(status_code=404, detail="大纲不存在")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/pptx/outlines/{outline_id}/generate", response_model=TaskResponse)
async def generate_ppt_from_approved_outline(
    outline_id: str,
    req: OutlineGenerateRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a generation task from an approved outline snapshot."""
    try:
        outline = await persist_get_ppt_outline(
            db,
            str(token.get("sub", "anonymous")),
            outline_id,
            req.outline_version,
        )
    except (StateNotFoundError, StateOwnershipError):
        raise HTTPException(status_code=404, detail="大纲不存在")
    if outline.status != "approved":
        raise HTTPException(status_code=409, detail="大纲尚未批准")

    outline_prompt = {
        "id": outline.id,
        "version": outline.version,
        "status": outline.status,
        "title": outline.title,
        "scenario": outline.scenario,
        "template_id": outline.template_id,
        "slides": [slide.model_dump(mode="json") for slide in outline.slides],
    }
    generation_request = PPTGenerationRequest(
        topic=outline.title,
        template=outline.template_id,
        slide_count=1 + len(outline.slides),
        quality="high",
        api_key_token=req.api_key_token,
        output_format=req.output_format,
        options={
            "auto_images": req.auto_images,
            "enable_animation": req.enable_animation,
            "quality_mode": req.quality_mode,
            "outline_id": outline.id,
            "outline_version": outline.version,
            "approved_outline": outline_prompt,
        },
    )
    return await generate_ppt_task(generation_request, token=token, db=db)


@router.post("/pptx/outlines/{outline_id}/slides/{slide_id}/regenerate", response_model=TaskResponse)
async def regenerate_ppt_slide(
    outline_id: str,
    slide_id: str,
    req: SlideRegenerateRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Save a targeted revision and export the entire deck as a new artifact."""
    user_id = str(token.get("sub", "anonymous"))
    try:
        revised = await revise_ppt_slide(
            db, user_id, outline_id, req.outline_version, slide_id, req.slide
        )
    except (StateNotFoundError, StateOwnershipError):
        raise HTTPException(status_code=404, detail="大纲版本或目标页面不存在")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="大纲版本保存冲突，请重试")

    generation = OutlineGenerateRequest.model_validate({
        **req.model_dump(exclude={"slide"}), "outline_version": revised.version,
    })
    try:
        return await generate_ppt_from_approved_outline(outline_id, generation, token=token, db=db)
    except Exception:
        await db.rollback()
        logger.exception("创建定向修改导出任务失败")
        return JSONResponse(status_code=503, content={
            "code": "SERVICE_UNAVAILABLE",
            "message": f"修改已保存为 v{revised.version}，导出任务创建失败，可重试导出。",
            "details": {"outline_id": outline_id, "outline_version": revised.version},
        })


@router.get("/pptx/{task_id}/quality-report")
async def get_ppt_quality_report(
    task_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        report = await persist_get_ppt_quality_report(db, task_id, int(token.get("sub")))
    except StateNotFoundError:
        raise HTTPException(status_code=404, detail="质量报告不存在")
    return {
        "id": report.id,
        "task_id": report.task_id,
        "outline_id": report.outline_id,
        "outline_version": report.outline_version,
        "quality_mode": report.quality_mode,
        "overall_score": report.overall_score,
        "slide_scores": report.slide_scores_json,
        "issues": report.issues_json,
        "reflow_attempts": report.reflow_attempts_json,
        "degraded_stage": report.degraded_stage,
        "status": report.status,
    }

# =============================================================================
# PPT 全局常量
# =============================================================================

PPT_DEFAULT_MODEL = DEFAULT_PPT_MODEL
PPT_MAX_SLIDES = 50
# 单个请求最多引用的素材数量：素材上下文按 ID 逐条查库并可能解析文件，
# 不设上限时请求体可携带海量 ID 放大数据库与解析开销。
PPT_MAX_MATERIAL_FILES = 50
# 锚定仓库根目录，避免相对路径随进程 CWD 漂移导致产物写到意外位置。
PPT_OUTPUT_DIR = BASE_DIR / "pptx_output"
PPT_OWNER_DIR = PPT_OUTPUT_DIR / ".owners"


def _register_ppt_owner(ppt_id: str, user_id: str) -> None:
    """Register the owner of a generated PPT artifact."""
    PPT_OWNER_DIR.mkdir(parents=True, exist_ok=True)
    with open(PPT_OWNER_DIR / f"{ppt_id}.json", "w", encoding="utf-8") as owner_file:
        json.dump({"ppt_id": ppt_id, "user_id": str(user_id)}, owner_file)


def _verify_ppt_owner(ppt_id: str, user_id: str) -> None:
    """Reject access when an artifact has a different registered owner."""
    owner_path = PPT_OWNER_DIR / f"{ppt_id}.json"
    if not owner_path.exists():
        raise HTTPException(status_code=404, detail="PPT 任务不存在或已过期")
    try:
        with open(owner_path, "r", encoding="utf-8") as owner_file:
            owner = json.load(owner_file)
    except (OSError, ValueError, TypeError):
        raise HTTPException(status_code=404, detail="PPT 任务状态不可用")
    if str(owner.get("user_id")) != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此 PPT")


def _ppt_history_record(
    ppt_id: str,
    json_path: Path,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Build one history record, returning None when the user cannot read it."""
    owner_path = PPT_OWNER_DIR / f"{ppt_id}.json"
    if not owner_path.exists():
        return None
    try:
        with open(owner_path, "r", encoding="utf-8") as owner_file:
            owner = json.load(owner_file)
    except (OSError, ValueError, TypeError):
        return None
    if str(owner.get("user_id")) != str(user_id):
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as slides_file:
            raw_data = json.load(slides_file)
    except (OSError, ValueError, TypeError):
        return None

    # 兼容新格式（dict）和旧格式（list）
    if isinstance(raw_data, dict):
        slides_list = raw_data.get("slides", [])
        record_user_id = raw_data.get("user_id")
        record_title = str(raw_data.get("title") or "").strip()
    else:
        slides_list = raw_data
        record_user_id = None
        record_title = ""
    if not isinstance(slides_list, list):
        slides_list = []
    if record_user_id and str(record_user_id) != str(user_id):
        return None

    if not record_title and slides_list:
        first = slides_list[0] if isinstance(slides_list[0], dict) else {}
        record_title = str(first.get("title") or "").strip()
    record_title = record_title or "未命名"

    pptx_path = PPT_OUTPUT_DIR / f"{ppt_id}.pptx"
    has_file = pptx_path.exists()
    file_size_bytes = 0
    if has_file:
        try:
            file_size_bytes = pptx_path.stat().st_size
        except OSError:
            has_file = False
    download_url = (
        f"/api/v1/pptx/download/{ppt_id}?format=pptx" if has_file else None
    )
    try:
        created_at = datetime.fromtimestamp(json_path.stat().st_mtime).isoformat()
    except OSError:
        return None

    return {
        "id": ppt_id,
        "ppt_id": ppt_id,
        "task_id": ppt_id,
        "title": record_title,
        "topic": record_title,
        "slide_count": len(slides_list),
        "file_size_bytes": file_size_bytes,
        "has_file": has_file,
        "status": "completed" if has_file else "failed",
        "created_at": created_at,
        "download_url": download_url,
        "detail_url": f"/api/v1/pptx/history/{ppt_id}",
        "preview_url": (
            f"/api/v1/pptx/preview/{ppt_id}?format=pptx" if has_file else None
        ),
    }


def _preview_url(ppt_id: str, output_format: "OutputFormat") -> str:
    """Return a preview URL that preserves the generated artifact format."""
    return f"/api/v1/pptx/preview/{ppt_id}?format={output_format.value}"

# 所有合法模板 ID（前端、后端、配置文件共用此列表）
VALID_TEMPLATE_IDS = [
    "modern", "business", "creative", "minimal",
    "academic", "tech", "education", "medical", "elegant",
]


# =============================================================================
# 安全校验函数
# =============================================================================

# 合法的 task_id/ppt_id 格式：UUID 或 UUID 前缀
_ID_PATTERN = re.compile(r'^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$', re.IGNORECASE)


def _validate_ppt_id(ppt_id: str) -> str:
    """校验 ppt_id/task_id，防止路径穿越。

    只允许 UUID 格式的 ID，拒绝包含 /、.. 等特殊字符的输入。
    """
    if not ppt_id or not _ID_PATTERN.match(ppt_id):
        raise HTTPException(status_code=400, detail="无效的 PPT ID 格式")
    return ppt_id


# =============================================================================
# 模型定义
# =============================================================================

class OutputFormat(str, Enum):
    """输出格式枚举"""
    PPTX = "pptx"
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"

class PPTGenerationRequest(BaseModel):
    """统一的 PPT 生成请求"""
    # 基础信息
    topic: str = Field(..., description="PPT 主题/提示词", max_length=5000, alias="prompt")
    model: str = Field(default=PPT_DEFAULT_MODEL, description="AI 模型")
    conversation_id: Optional[int] = Field(None, description="会话 ID (用于携带历史上下文)")
    session_id: Optional[str] = Field(None, description="会话 ID (用于素材隔离)")
    material_file_ids: Optional[List[int]] = Field(
        None,
        max_length=PPT_MAX_MATERIAL_FILES,
        description="已上传素材的文件 ID 列表",
    )
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token（用于从 Redis 获取用户自定义 Key）")
    
    # 增强选项
    template: str = Field(default="modern", description="模板风格")
    slide_count: int = Field(default=10, ge=1, le=PPT_MAX_SLIDES, description="页数")
    output_format: OutputFormat = Field(default=OutputFormat.PPTX, description="输出格式")
    language: str = Field(default="zh-CN", description="语言")
    quality: str = Field(default="high", description="内容质量")
    options: Dict[str, Any] = Field(default_factory=dict, description="高级选项")
    skills: List[str] = Field(default_factory=list, description="Skill 提示词列表")

    class Config:
        populate_by_name = True

class PPTModifyRequest(BaseModel):
    """PPT 修改请求"""
    user_input: str = Field(..., description="用户修改需求（自然语言）", max_length=2000)
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token")
    analyze_before_modify: bool = Field(default=True, description="修改前是否分析当前状态")

    class Config:
        populate_by_name = True


class PPTGenerationResponse(BaseModel):
    """PPT 生成响应"""
    id: str
    status: str
    topic: str
    slide_count: int
    output_format: str
    created_at: str
    download_url: str
    preview_url: Optional[str] = None
    slides: Optional[List[Dict[str, Any]]] = None

# =============================================================================
# 模板与样式配置（已提取到 app/utils/pptx/ppt_style.py）
# =============================================================================

# PPT_TEMPLATES 和 PPTStyle 从 app.utils.pptx.ppt_style 导入（见文件顶部）




# 导入 Aicode 的会话压缩函数
from app.api.v1.Aicode import compress_conversation_history
from app.api.v1.ppt_slide_renderer import (  # noqa: F401
    _add_academic_note,
    _add_clinical_card,
    _add_creative_block,
    _add_cropped_picture,
    _add_editorial_card,
    _add_editorial_text,
    _add_elegant_note,
    _add_learning_card,
    _add_minimal_rule,
    _add_modern_tile,
    _add_tech_panel,
    _apply_paragraph_font,
    _chrome,
    _commercial_slide_items,
    _cover_kicker,
    _cover_tagline,
    _fit_editorial_text,
    _is_zh_style,
    _item_at,
    _modern_variant_base,
    _normalize_slide_items,
    _render_modern_full_bleed_variant,
    _render_modern_grid_variant,
    _render_modern_matrix_variant,
    _render_modern_metric_variant,
    _render_modern_quote_variant,
    _render_modern_rail_variant,
    _render_modern_split_variant,
    _render_modern_statement_variant,
    _render_modern_timeline_variant,
    _render_slide_academic,
    _render_slide_creative,
    _render_slide_default,
    _render_slide_education,
    _render_slide_elegant,
    _render_slide_medical,
    _render_slide_minimal,
    _render_slide_modern,
    _render_slide_modern_variant,
    _render_slide_tech,
    _role_kicker,
    _slide_role,
    _soften_rounded_rect,
    _split_commercial_item,
    add_page_number,
    add_slide_background,
)
from app.utils import call_llm

# =============================================================================
# 辅助函数：大纲生成、多格式导出、预览
# =============================================================================


def _extract_json_payload(content: str) -> str:
    """从 LLM 响应中提取首个完整 JSON 文本。

    优先取 markdown 代码块内容；否则从首个 ``{`` 或 ``[`` 起用
    ``raw_decode`` 解析到第一个完整 JSON 值为止，避免贪婪正则跨越
    多段 JSON 把整段拼成一个无法解析的字符串，最终静默回退模板大纲。
    """
    fenced = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if fenced:
        return fenced.group(1)

    starts = [index for index in (content.find("{"), content.find("[")) if index != -1]
    if not starts:
        raise ValueError("响应中未找到 JSON")
    start = min(starts)
    _, end = json.JSONDecoder().raw_decode(content[start:])
    return content[start:start + end]


# 单个素材正文进入 prompt 的上限（字符），与 ppt_state_service._load_materials 对齐
_MATERIAL_CONTENT_LIMIT = 12000


async def _read_material_text(file_record: File, limit: int = _MATERIAL_CONTENT_LIMIT) -> str:
    """读取素材正文：优先使用解析缓存，未命中则解析并回填缓存。

    此前只把文件名拼进 prompt，素材正文（`parsed_content`）从未被消费，
    与 ppt_state_service._load_materials 的行为不一致。
    """
    if file_record.is_parse_cache_valid():
        return (file_record.parsed_content or "").strip()[:limit]

    from app.utils.aicloud.knowledge_processor import parse_document

    try:
        content = await asyncio.to_thread(parse_document, str(file_record.file_path))
    except Exception as exc:
        logger.warning("素材解析失败 | file=%s | error=%s", file_record.filename, exc)
        return ""

    content = (content or "").strip()
    if content:
        file_record.update_parse_cache(content)
    return content[:limit]


async def _build_material_context(
    db: AsyncSession,
    user_id: str,
    material_file_ids: List[int],
    session_id: Optional[str] = None,
) -> str:
    """按 file_id 读取素材正文，返回可直接拼进 prompt 的 `[参考素材]` 段。

    原先只记录文件名（`- name.pdf`），素材正文从未进入 LLM。无可用素材时返回空串。

    每个 ID 都要查库并可能解析文件，因此超过 `PPT_MAX_MATERIAL_FILES` 的部分
    直接忽略；该函数也会被 `prompt` 内联素材等非模型校验入口调用。
    """
    material_info = []
    for file_id in list(material_file_ids)[:PPT_MAX_MATERIAL_FILES]:
        try:
            result = await db.execute(
                select(File).where(File.id == file_id, File.user_id == int(user_id))
            )
            file_record = result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("查询素材失败 | file_id=%s | error=%s", file_id, exc)
            continue

        if not file_record:
            continue
        # conversation_id 是 Integer，session_id 是 str：直接比较恒不相等，会误过滤全部素材
        if session_id and str(file_record.conversation_id) != str(session_id):
            continue

        try:
            content = await _read_material_text(file_record)
        except Exception as exc:
            logger.warning("读取素材正文失败 | file=%s | error=%s", file_record.filename, exc)
            content = ""

        if content:
            material_info.append(f"[素材：{file_record.filename}]\n{content}")
        else:
            material_info.append(f"- {file_record.filename}")

    if not material_info:
        return ""
    return "\n[参考素材]\n" + "\n\n".join(material_info)


async def generate_ppt_outline(req: PPTGenerationRequest, user_id: str = None) -> Dict[str, Any]:
    """使用 AI 生成 PPT 大纲 (支持 Skills 和多参数)"""
    # 构建 prompt
    skill_prompts = []
    for skill in req.skills:
        skill_prompts.append(f"- 遵循 {skill} 最佳实践")
    
    skill_context = "\n".join(skill_prompts) if skill_prompts else ""
    
    # 构建内容上下文
    content_context = req.topic
    if req.material_file_ids:
        content_context += f"\n\n参考素材 ID: {req.material_file_ids}"
    
    role_schema = " | ".join(NARRATIVE_ROLES)
    content_slide_count = max(0, req.slide_count - 1)
    domain_guidance = ""
    if "游戏" in req.topic and any(signal in req.topic.lower() for signal in ("ai", "人工智能", "智能")):
        domain_guidance = """
- 这是游戏行业主题。必须围绕玩家体验、AI NPC 与智能体、程序化内容、研发管线、UGC、实时运营、商业模式、版权安全和组织能力展开。
- 每页至少出现一个游戏行业概念或可验证的游戏业务判断，禁止使用泛化的企业流程、重复录入、端到端工具、试点闭环等 SaaS 话术替代主题分析。
- 论点需要体现游戏与 AI 的因果关系，并区分辅助生产、增强体验、AI 原生玩法三个阶段。
"""
    prompt = f"""
请根据以下要求生成一个专业的 PPT 大纲，返回 JSON 格式：

{{
    "title": "PPT 标题",
    "slides": [
        {{
            "slide_number": 1,
            "title": "幻灯片标题",
            "key_message": "本页唯一核心结论",
            "content": ["兼容正文 1", "兼容正文 2"],
            "content_blocks": [
                {{
                    "type": "signal|evidence|case|implication|option|recommendation|criteria|stage|gate|decision|action|request|success_metric",
                    "content": "20 到 40 字的完整论点，含对象、变化和依据",
                    "metadata": {{"metric": "指标名称", "target": "目标值"}}
                }}
            ],
            "slide_type": "key_points|data|comparison|timeline|summary",
            "narrative_role": "{role_schema}",
            "notes": "演讲者备注（可选）"
        }}
    ]
}}

要求：
- 主题：{content_context}
- 内容页数：{content_slide_count}页，封面由系统单独生成
- 语言：{req.language}
- 质量：{req.quality}
- 模板风格：{req.template}
{skill_context if skill_context else ""}
- 内容页按 opportunity_map、evidence_story、strategic_choice、execution_roadmap、decision_close 形成完整商业叙事；页数超过 5 时循环使用并保持相邻页面角色不同
- opportunity_map 的 metadata 提供 roi、priority、validation_period、metric、target
- evidence_story 的 metadata 提供 metric、target、validation_period，并用公开来源可验证的数据表达
- strategic_choice 的两个 option 提供 cost、timeframe、risk，recommendation 提供 rationale
- execution_roadmap 的三个 stage 提供 deliverable、metric、target、gate
- decision_close 的 decision、action、request 提供 owner、deadline、priority，success_metric 提供 metric、target
- 每页输出 4 个 content_blocks，并让 content 与 content_blocks 的 content 保持一致
- 正文必须是可宣讲的完整句子，禁止用「分布图」「热力图」「甘特图」「矩阵」等图表标题代替论点
{domain_guidance}

请直接返回 JSON 格式，不要有多余解释。
"""
    
    try:
        response = await call_llm(
            model=req.model,
            prompt=prompt,
            api_key_token=req.api_key_token
        )

        # 从 API 响应中提取 content
        if isinstance(response, dict):
            choices = response.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '')
            else:
                content = str(response)
        else:
            content = str(response)

        outline = json.loads(_extract_json_payload(content))
        if isinstance(outline, dict) and isinstance(outline.get("slides"), list):
            _ensure_commercial_role_diversity(outline["slides"])
            _ensure_content_diversity(outline["slides"], req.topic)
        return outline
        
    except Exception as e:
        logger.warning("AI 大纲生成失败，使用领域化回退大纲：%s", e)
        page_blueprint = build_expanded_commercial_page_blueprint(
            req.topic, content_slide_count
        )
        first_pass = min(5, content_slide_count)
        layout_variants = [0] * first_pass + select_layout_variants(
            req.topic,
            max(0, content_slide_count - first_pass),
            recent_variants=(0,),
        )
        slides = []
        for index in range(content_slide_count):
            page = page_blueprint[index % len(page_blueprint)]
            slides.append({
                "slide_number": index + 1,
                "title": page["title"],
                "key_message": page["key_message"],
                "content": [block["content"] for block in page["blocks"]],
                "content_blocks": page["blocks"],
                "slide_type": page["slide_type"],
                "narrative_role": page["role"],
                "asset_intent": page["asset_intent"],
                "layout_variant": layout_variants[index],
                "notes": "",
            })
        return {
            "title": req.topic[:50],
            "slides": slides,
        }


def _normalize_approved_outline(outline: Dict[str, Any]) -> Dict[str, Any]:
    """Convert reviewed semantic slides into the legacy renderer contract."""
    preserve_content = outline.get("status") == "approved" or outline.get("preserve_content", False)
    normalized_slides = []
    source_slides = outline.get("slides", [])
    roles = [slide.get("narrative_role") for slide in source_slides if isinstance(slide, dict)]
    has_repeated_roles = len(roles) != len(set(roles))
    first_pass = min(5, len(source_slides)) if has_repeated_roles else len(source_slides)
    layout_variants = [0] * first_pass + select_layout_variants(
        str(outline.get("title", "PPT")),
        max(0, len(source_slides) - first_pass),
        recent_variants=(0,),
    )
    source_slides = outline.get("slides", [])
    for index, slide in enumerate(outline.get("slides", []), 1):
        content = slide.get("content", "")
        if not content and slide.get("content_blocks"):
            content = [
                block.get("content", "")
                for block in slide["content_blocks"]
                if block.get("content", "")
            ]
        key_message = slide.get("key_message", "")
        body_texts = [
            str(block.get("content") or "")
            for block in (slide.get("content_blocks") or [])
            if isinstance(block, dict)
        ] or ([content] if isinstance(content, list) else [content])
        if key_message_repeats_body(key_message, body_texts):
            # The page conclusion is already carried by the body; keep it out of the render.
            key_message = ""
        normalized_slides.append({
            "id": slide.get("id", f"slide-{index}"),
            "position": slide.get("position", index - 1),
            "preserve_content": preserve_content,
            "slide_number": slide.get("slide_number", index),
            "title": slide.get("title", f"第 {index} 页"),
            "content": content,
            "content_blocks": slide.get("content_blocks", []),
            "key_message": key_message,
            "slide_type": slide.get("slide_type", "content"),
            "notes": slide.get("notes", slide.get("speaker_notes", "")),
            "asset_intent": slide.get("asset_intent"),
            "narrative_role": slide.get("narrative_role", "opportunity_map"),
            "layout_variant": slide.get("layout_variant", layout_variants[index - 1]),
            "evidence_sources": slide.get("evidence_sources", outline.get("evidence_sources", [])),
        })
    if not preserve_content and normalized_slides and all(
        isinstance(slide, dict) and slide.get("narrative_role") for slide in source_slides
    ):
        _ensure_commercial_role_diversity(normalized_slides)
        _ensure_content_diversity(normalized_slides, outline.get("title", "PPT"))
    return {
        "title": outline.get("title", "PPT 标题"),
        "subtitle": outline.get("subtitle", ""),
        "tagline": outline.get("tagline", ""),
        "summary": outline.get("summary", ""),
        "slides": normalized_slides,
        "preserve_content": preserve_content,
    }


def _ensure_commercial_role_diversity(slides: List[Dict[str, Any]]) -> None:
    """Repair generic AI output that assigns one commercial role to every page."""
    if len(slides) < 2:
        return

    roles = [slide.get("narrative_role") for slide in slides]
    if len(set(roles)) != 1 or roles[0] not in NARRATIVE_ROLES:
        return

    role_sequence = NARRATIVE_ROLES
    type_by_role = {
        "opportunity_map": "key_points",
        "evidence_story": "data",
        "strategic_choice": "comparison",
        "execution_roadmap": "timeline",
        "decision_close": "summary",
    }
    for index, slide in enumerate(slides):
        role = role_sequence[index % len(role_sequence)]
        slide["narrative_role"] = role
        if slide.get("slide_type") in {None, "", "content", "key_points"}:
            slide["slide_type"] = type_by_role[role]


def _ensure_content_diversity(slides: List[Dict[str, Any]], topic: str) -> None:
    """Replace exact duplicate content pages with topic-specific fallback pages."""
    if len(slides) < 2:
        return

    blueprint = build_expanded_commercial_page_blueprint(topic, len(slides))
    seen = set()
    for index, slide in enumerate(slides):
        signature = (
            slide.get("title", "").strip(),
            tuple(slide.get("content", []) or []),
            tuple(block.get("content", "") for block in slide.get("content_blocks", []) or []),
        )
        if signature not in seen:
            seen.add(signature)
            continue
        page = blueprint[index % len(blueprint)]
        slide.update({
            "title": page["title"],
            "key_message": page["key_message"],
            "content": [block["content"] for block in page["blocks"]],
            "content_blocks": page["blocks"],
            "slide_type": page["slide_type"],
            "narrative_role": page["role"],
            "asset_intent": page["asset_intent"],
        })
        seen.add((
            page["title"],
            tuple(slide["content"]),
            tuple(block["content"] for block in page["blocks"]),
        ))


def _content_slides_for_total(
    slides: List[Dict[str, Any]],
    total_slides: Optional[int],
) -> List[Dict[str, Any]]:
    """Fit editable pages beside the single cover owned by the renderer."""
    content_slides = list(slides)
    if content_slides:
        first_type = content_slides[0].get("slide_type", content_slides[0].get("type", ""))
        if first_type in {"cover", "title"}:
            content_slides = content_slides[1:]
    if isinstance(total_slides, int):
        content_slides = content_slides[:max(0, total_slides - 1)]
    return content_slides

async def generate_pptx_file_enhanced(filepath: Path, outline: Dict[str, Any], req: PPTGenerationRequest, update_progress=None, user_id=None):
    """生成 PPTX 文件 (增强版：包含视觉决策和模板支持)"""
    outline = _normalize_approved_outline(outline)
    outline["slides"] = _content_slides_for_total(
        outline.get("slides", []),
        getattr(req, "slide_count", None),
    )
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    requested_template = req.template
    fields_set = getattr(req, "model_fields_set", set())
    if isinstance(fields_set, set) and req.template == "modern" and "template" not in fields_set:
        requested_template = "auto"
    resolved_template = resolve_topic_template(req.topic, requested_template)
    style = PPTStyle(template_name=resolved_template)
    template_manager = TemplateManager()
    token_template_id = {"business": "business_report", "creative": "pitch_deck"}.get(resolved_template, resolved_template)
    try:
        tokens = template_manager.resolve_design_tokens(token_template_id)
        style = apply_design_tokens(style, tokens)
    except KeyError:
        tokens = None
        logger.warning("设计令牌模板不存在，沿用 PPTStyle: %s", req.template)
    language = getattr(req, "language", None)
    style.language = language.strip() if isinstance(language, str) and language.strip() else "zh-CN"
    total_slides = 1 + len(outline.get('slides', []))
    blank_layout = prs.slide_layouts[6]

    if update_progress: await update_progress(message="正在创建封面...")

    # === 1. 标题页（封面）===
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    cover_variant = select_cover_variant(outline.get("title", "PPT"))
    if style.template_name != "modern":
        if cover_variant == 1:
            accent = slide.shapes.add_shape(1, Inches(0.42), Inches(0.65), Inches(0.08), Inches(6.2))
            accent.fill.solid(); accent.fill.fore_color.rgb = style.ACCENT_COLOR; accent.line.fill.background()
        elif cover_variant == 2:
            accent = slide.shapes.add_shape(1, Inches(0.75), Inches(0.48), Inches(11.85), Inches(0.06))
            accent.fill.solid(); accent.fill.fore_color.rgb = style.ACCENT_COLOR; accent.line.fill.background()
        elif cover_variant == 3:
            accent = slide.shapes.add_shape(9, Inches(10.85), Inches(0.55), Inches(1.15), Inches(1.15))
            accent.fill.solid(); accent.fill.fore_color.rgb = style.ACCENT_LIGHT; accent.line.fill.background()

    if style.template_name == "education":
        _add_editorial_text(slide, f"{_cover_kicker(style)}  /  {datetime.now().year}", 0.78, 0.68, 3.8, 0.32, style, 10, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.78, 1.55, 9.7, 1.62, style, 42, style.TEXT_DARK, True)
        _add_editorial_text(slide, _cover_tagline(outline), 0.82, 3.5, 7.8, 0.42, style, 14, style.PRIMARY_DARK)
        for number, label in enumerate(("理解", "练习", "应用"), 1):
            left = 0.78 + (number - 1) * 4.05
            _add_learning_card(slide, _chrome(style, f"步骤 0{number}", f"STEP 0{number}"), label, left, 5.05, 3.55, 1.35, style, number == 3)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.75, 0.68, 1.75, 0.28, style, 9, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    elif style.template_name == "elegant":
        _add_editorial_text(slide, f"{_cover_kicker(style)}  /  {datetime.now().year}", 0.8, 0.7, 3.8, 0.3, style, 9, style.PRIMARY_COLOR, True)
        cover_rule = slide.shapes.add_shape(1, Inches(0.8), Inches(1.28), Inches(11.75), Inches(0.025))
        cover_rule.fill.solid(); cover_rule.fill.fore_color.rgb = style.PRIMARY_COLOR; cover_rule.line.fill.background()
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.8, 1.85, 9.5, 1.62, style, 41, style.TEXT_DARK, True)
        _add_editorial_text(slide, _cover_tagline(outline), 0.83, 4.08, 6.5, 0.34, style, 11, style.PRIMARY_DARK, True)
        _add_editorial_text(slide, "I", 10.75, 4.6, 1.55, 1.25, style, 66, style.PRIMARY_COLOR, True, PP_ALIGN.RIGHT)
        bottom_rule = slide.shapes.add_shape(1, Inches(0.8), Inches(6.2), Inches(11.75), Inches(0.025))
        bottom_rule.fill.solid(); bottom_rule.fill.fore_color.rgb = style.PRIMARY_LIGHT; bottom_rule.line.fill.background()
        _add_editorial_text(slide, _chrome(style, "高层备忘录", "EXECUTIVE MEMORANDUM"), 0.8, 6.42, 3.7, 0.28, style, 9, style.TEXT_GRAY, True)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.75, 6.42, 1.8, 0.28, style, 9, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    elif style.template_name == "medical":
        _add_editorial_text(slide, f"{_cover_kicker(style)}  /  {datetime.now().year}", 0.78, 0.68, 3.8, 0.32, style, 10, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.78, 1.55, 9.25, 1.5, style, 40, style.TEXT_DARK, True)
        _add_editorial_text(slide, _cover_tagline(outline), 0.82, 3.55, 7.8, 0.42, style, 14, style.PRIMARY_DARK)
        cover_rule = slide.shapes.add_shape(1, Inches(0.78), Inches(4.55), Inches(11.78), Inches(0.035))
        cover_rule.fill.solid(); cover_rule.fill.fore_color.rgb = style.PRIMARY_LIGHT; cover_rule.line.fill.background()
        for number, label in enumerate((_chrome(style, "信号", "SIGNAL"), _chrome(style, "路径", "PATHWAY"), _chrome(style, "行动", "ACTION")), 1):
            left = 0.78 + (number - 1) * 4.05
            _add_clinical_card(slide, f"0{number}", label, left, 5.18, 3.55, 1.28, style, number == 1)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.75, 0.68, 1.75, 0.28, style, 9, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    elif style.template_name == "academic":
        margin = slide.shapes.add_shape(1, Inches(0.72), Inches(0.68), Inches(0.09), Inches(6.15))
        margin.fill.solid(); margin.fill.fore_color.rgb = style.PRIMARY_COLOR; margin.line.fill.background()
        paper = slide.shapes.add_shape(1, Inches(1.18), Inches(0.68), Inches(11.42), Inches(6.15))
        paper.fill.solid(); paper.fill.fore_color.rgb = style.TEXT_WHITE; paper.line.color.rgb = style.PRIMARY_LIGHT
        _add_editorial_text(slide, f"{_cover_kicker(style)}  /  {datetime.now().year}", 1.65, 1.15, 4.2, 0.32, style, 10, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 1.65, 2.02, 9.75, 1.7, style, 39, style.PRIMARY_DARK, True)
        _add_editorial_text(slide, _cover_tagline(outline), 1.68, 4.2, 5.3, 0.42, style, 14, style.TEXT_GRAY)
        cover_rule = slide.shapes.add_shape(1, Inches(1.65), Inches(5.35), Inches(9.95), Inches(0.025))
        cover_rule.fill.solid(); cover_rule.fill.fore_color.rgb = style.PRIMARY_LIGHT; cover_rule.line.fill.background()
        _add_editorial_text(slide, _chrome(style, "卷一", "VOLUME 01"), 1.65, 5.62, 2.0, 0.28, style, 9, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 9.8, 5.62, 1.8, 0.28, style, 9, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    elif style.template_name == "creative":
        spine = slide.shapes.add_shape(1, Inches(0.75), Inches(0.78), Inches(0.12), Inches(5.95))
        spine.fill.solid(); spine.fill.fore_color.rgb = style.ACCENT_COLOR; spine.line.fill.background()
        _add_editorial_text(slide, f"{_cover_kicker(style)}  /  {datetime.now().year}", 1.3, 1.25, 4.0, 0.35, style, 12, style.ACCENT_COLOR, True)
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 1.3, 2.05, 8.2, 1.65, style, 41, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, _cover_tagline(outline), 1.32, 4.2, 5.7, 0.38, style, 13, style.TEXT_GRAY, True)
        _add_editorial_text(slide, _chrome(style, "想法", "IDEA"), 9.15, 0.65, 3.25, 1.2, style, 48, style.ACCENT_LIGHT, True, PP_ALIGN.RIGHT)
        footer_panel = slide.shapes.add_shape(1, Inches(8.1), Inches(4.75), Inches(5.233), Inches(2.75))
        footer_panel.fill.solid(); footer_panel.fill.fore_color.rgb = style.PRIMARY_COLOR; footer_panel.line.fill.background()
        _add_editorial_text(slide, _chrome(style, "01  洞察\n02  选择\n03  行动", "01  INSIGHT\n02  CHOICE\n03  ACTION"), 8.65, 5.12, 3.0, 1.35, style, 17, style.TEXT_WHITE, True)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 11.15, 6.6, 1.45, 0.3, style, 10, style.ACCENT_LIGHT, True, PP_ALIGN.RIGHT)
    elif style.template_name == "modern":
        if cover_variant == 0:
            _add_editorial_text(slide, _cover_kicker(style), 0.78, 0.72, 3.5, 0.35, style, 11, style.PRIMARY_COLOR, True)
            _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.78, 1.55, 9.4, 1.55, style, 42, style.TEXT_DARK, True)
            _add_editorial_text(slide, _cover_tagline(outline), 0.82, 3.48, 7.2, 0.45, style, 15, style.TEXT_GRAY)
            for number, label in enumerate(("洞察", "选择", "行动"), 1):
                left = 0.78 + (number - 1) * 4.15
                _add_modern_tile(slide, f"0{number}", label, left, 5.15, 3.65, 1.25, style, number == 1)
        elif cover_variant == 1:
            panel = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(4.25), prs.slide_height)
            panel.fill.solid(); panel.fill.fore_color.rgb = style.PRIMARY_COLOR; panel.line.fill.background()
            _add_editorial_text(slide, f"{_cover_kicker(style)}  /  {datetime.now().year}", 0.78, 0.82, 2.8, 0.32, style, 10, style.TEXT_WHITE, True)
            _add_editorial_text(slide, "01", 0.78, 5.62, 1.2, 0.7, style, 34, style.ACCENT_LIGHT, True)
            _add_editorial_text(slide, _chrome(style, "洞察", "INSIGHT"), 0.82, 6.38, 2.0, 0.28, style, 10, style.TEXT_WHITE, True)
            _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 5.15, 1.72, 7.3, 1.9, style, 42, style.TEXT_DARK, True)
            _add_editorial_text(slide, _cover_tagline(outline), 5.18, 4.18, 6.5, 0.45, style, 15, style.TEXT_GRAY)
            _add_minimal_rule(slide, 5.18, 5.2, 6.8, style)
        elif cover_variant == 2:
            band = slide.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(1.05))
            band.fill.solid(); band.fill.fore_color.rgb = style.PRIMARY_COLOR; band.line.fill.background()
            _add_editorial_text(slide, _cover_kicker(style), 0.78, 0.38, 3.5, 0.3, style, 10, style.TEXT_WHITE, True)
            _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 1.05, 2.05, 11.2, 1.65, style, 44, style.TEXT_DARK, True, PP_ALIGN.CENTER)
            _add_editorial_text(slide, _cover_tagline(outline), 1.4, 4.05, 10.5, 0.55, style, 16, style.TEXT_GRAY, False, PP_ALIGN.CENTER)
            _add_editorial_text(slide, _chrome(style, "洞察  /  选择  /  行动", "INSIGHT   /   CHOICE   /   ACTION"), 2.7, 4.75, 7.95, 0.38, style, 13, style.PRIMARY_COLOR, True, PP_ALIGN.CENTER)
            _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.8, 6.55, 1.7, 0.3, style, 10, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
        else:
            hero = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(8.6), prs.slide_height)
            hero.fill.solid(); hero.fill.fore_color.rgb = style.PRIMARY_COLOR; hero.line.fill.background()
            _add_editorial_text(slide, _cover_kicker(style), 0.82, 0.82, 3.8, 0.3, style, 11, style.TEXT_WHITE, True)
            _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.82, 2.0, 7.0, 1.9, style, 40, style.TEXT_WHITE, True)
            _add_editorial_text(slide, _cover_tagline(outline), 0.85, 5.55, 6.4, 0.42, style, 14, style.TEXT_WHITE)
            _add_editorial_text(slide, "01", 9.65, 1.7, 2.0, 0.75, style, 38, style.PRIMARY_COLOR, True)
            _add_editorial_text(slide, "洞察", 9.65, 2.55, 2.0, 0.3, style, 14, style.TEXT_GRAY, True)
            _add_editorial_text(slide, "02", 9.65, 3.45, 2.0, 0.75, style, 38, style.PRIMARY_COLOR, True)
            _add_editorial_text(slide, "选择", 9.65, 4.3, 2.0, 0.3, style, 14, style.TEXT_GRAY, True)
            _add_editorial_text(slide, "03", 9.65, 5.2, 2.0, 0.75, style, 38, style.PRIMARY_COLOR, True)
            _add_editorial_text(slide, "行动", 9.65, 6.05, 2.0, 0.3, style, 14, style.TEXT_GRAY, True)
    elif style.template_name == "minimal":
        _add_editorial_text(slide, _cover_kicker(style), 0.72, 0.68, 2.2, 0.3, style, 10, style.TEXT_GRAY, True)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.85, 0.68, 1.75, 0.3, style, 10, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
        _add_minimal_rule(slide, 0.72, 1.15, 11.88, style, 2)
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.72, 2.0, 10.45, 1.8, style, 44, style.TEXT_DARK, True)
        _add_editorial_text(slide, "01", 10.75, 4.62, 1.85, 1.0, style, 52, style.TEXT_DARK, True, PP_ALIGN.RIGHT)
        _add_minimal_rule(slide, 0.72, 6.1, 3.25, style)
        _add_editorial_text(slide, _cover_tagline(outline), 0.72, 6.3, 8.5, 0.3, style, 12, style.TEXT_GRAY, True)
    elif style.template_name == "tech":
        _add_editorial_text(slide, _cover_kicker(style), 0.78, 0.62, 4.2, 0.32, style, 10, style.ACCENT_LIGHT, True)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.7, 0.62, 1.8, 0.32, style, 10, style.ACCENT_LIGHT, True, PP_ALIGN.RIGHT)
        top_line = slide.shapes.add_shape(1, Inches(0.78), Inches(1.12), Inches(11.72), Inches(0.04))
        top_line.fill.solid(); top_line.fill.fore_color.rgb = style.ACCENT_COLOR; top_line.line.fill.background()
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.78, 1.72, 10.2, 1.55, style, 42, style.TEXT_WHITE, True)
        _add_editorial_text(slide, _cover_tagline(outline), 0.82, 3.65, 6.3, 0.42, style, 14, style.ACCENT_LIGHT)
        for number, label in enumerate((_chrome(style, "洞察", "INSIGHT"), _chrome(style, "选择", "CHOICE"), _chrome(style, "行动", "ACTION")), 1):
            _add_tech_panel(slide, _chrome(style, f"模块 / 0{number}", f"MODULE / 0{number}"), label, 0.78 + (number - 1) * 4.05, 5.05, 3.55, 1.18, style, number == 3)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 10.75, 6.72, 1.75, 0.28, style, 9, style.ACCENT_LIGHT, False, PP_ALIGN.RIGHT)
    else:
        hero = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(9.15), prs.slide_height)
        hero.fill.solid(); hero.fill.fore_color.rgb = style.PRIMARY_COLOR; hero.line.fill.background()
        accent = slide.shapes.add_shape(1, Inches(0.85), Inches(1.15), Inches(1.0), Inches(0.08))
        accent.fill.solid(); accent.fill.fore_color.rgb = style.ACCENT_COLOR; accent.line.fill.background()
        _add_editorial_text(slide, _cover_kicker(style), 0.85, 1.4, 4.0, 0.35, style, 12, style.TEXT_WHITE, True)
        _add_editorial_text(slide, outline.get('title', 'PPT 标题'), 0.85, 2.15, 7.55, 1.55, style, 40, style.TEXT_WHITE, True)
        _add_editorial_text(slide, _cover_tagline(outline), 0.88, 5.15, 6.5, 0.45, style, 14, style.TEXT_WHITE)
        _add_editorial_text(slide, datetime.now().strftime('%Y.%m.%d'), 0.88, 5.75, 6.5, 0.3, style, 12, style.TEXT_WHITE)
        _add_editorial_text(slide, "01", 10.1, 1.35, 1.8, 0.8, style, 34, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, "洞察", 10.1, 2.1, 1.8, 0.35, style, 14, style.TEXT_GRAY, True)
        _add_editorial_text(slide, "02", 10.1, 3.15, 1.8, 0.8, style, 34, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, "选择", 10.1, 3.9, 1.8, 0.35, style, 14, style.TEXT_GRAY, True)
        _add_editorial_text(slide, "03", 10.1, 4.95, 1.8, 0.8, style, 34, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, "行动", 10.1, 5.7, 1.8, 0.35, style, 14, style.TEXT_GRAY, True)
    
    # === 2. 视觉决策阶段 ===
    visual_plan = None
    if update_progress: await update_progress(message="正在分析视觉需求...")
    if req.api_key_token and req.options.get("auto_images", True):
        try:
            visual_plan = await visual_analyzer.analyze_ppt_content(
                title=outline.get("title", "PPT"),
                slides_content=outline.get("slides", []),
                theme=req.template,
                api_key_token=req.api_key_token,
            )
        except Exception as e:
            logger.warning("视觉分析失败，使用本地布局: %s", e)
    else:
        logger.info("未提供用户模型凭据，跳过视觉分析并使用本地布局")

    # === 3. 内容幻灯片 ===
    content_slides = [s for s in outline.get('slides', []) if s.get('slide_type') != 'cover']
    for idx, slide_data in enumerate(content_slides, 1):
        if update_progress: 
            await update_progress(progress=int(50 + 50 * idx / total_slides), message=f"正在生成第 {idx} 页...")
        
        # 如果视觉决策启用，尝试使用
        image_asset = None
        role = slide_data.get("narrative_role", "opportunity_map")
        needs_editorial_image = req.options.get("auto_images", True) and role == "opportunity_map"

        if needs_editorial_image and slide_data.get("asset_intent"):
            try:
                intent = slide_data["asset_intent"]
                image_asset = await image_manager.get_image_for_slide(
                    image_type=intent.get("asset_type", "illustration"),
                    description=intent.get("description", slide_data.get("title", "PPT 视觉素材")),
                    keywords=intent.get("keywords", []),
                    slide_index=idx,
                    style=f"{req.template} 风格",
                )
            except Exception as e:
                logger.warning("页面配图获取失败: %s", e)

        if needs_editorial_image and visual_plan and idx <= len(visual_plan.slides) and not image_asset:
            slide_decision = visual_plan.slides[idx - 1]
            main_image = slide_decision.get_main_image() if slide_decision.need_image else None

            if main_image and main_image.image_type != ImageType.NONE:
                try:
                    image_asset = await image_manager.get_image_for_slide(
                        image_type=main_image.image_type.value,
                        description=main_image.description,
                        keywords=main_image.keywords,
                        slide_index=idx,
                        style=f"{req.template} 风格"
                    )
                except Exception as e:
                    logger.warning(f"幻灯片 {idx} 配图获取失败: {e}")

        if image_asset and image_asset.local_path:
            slide_data = {**slide_data, "local_images": [image_asset.local_path]}
        _render_slide_default(prs, blank_layout, style, slide_data, idx, total_slides)
    
    if req.options.get("enable_animation", False):
        from app.utils.pptx.animation_engine import AnimationEngine, TransitionEffect

        AnimationEngine().set_default_transition(prs, TransitionEffect.FADE)
    prs.save(str(filepath))
    logger.info(f"PPTX 文件保存成功 | file: {filepath}")
    
    # 保存 JSON 数据（用于预览和历史记录）
    json_path = filepath.parent / f"{filepath.stem}_slides.json"
    json_data = {
        "user_id": user_id,
        "slides": outline.get('slides', []),
        "title": outline.get('title', ''),
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

async def generate_html_ppt(filepath: Path, outline: Dict[str, Any], req: PPTGenerationRequest):
    """生成 HTML 格式 PPT"""
    template = PPT_TEMPLATES.get(req.template, PPT_TEMPLATES["modern"])
    content_slides = _content_slides_for_total(
        outline.get("slides", []),
        getattr(req, "slide_count", None),
    )
    
    title = html.escape(str(outline.get('title', 'PPT')))
    language = html.escape(req.language, quote=True)
    html_content = f"""<!DOCTYPE html>
<html lang="{language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --primary-color: {template['primary_color']};
            --secondary-color: {template['secondary_color']};
            --font-family: {template['font_family']};
            --background: {template['background']};
        }}
        body {{
            font-family: var(--font-family);
            background: var(--background);
            margin: 0;
            padding: 20px;
        }}
        .slide {{
            background: white;
            border-radius: 8px;
            padding: 40px;
            margin: 20px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            page-break-after: always;
        }}
        .slide h1 {{ color: var(--primary-color); font-size: 32px; }}
        .slide h2 {{ color: var(--secondary-color); font-size: 24px; }}
        .slide-content {{ font-size: 18px; line-height: 1.6; white-space: pre-line; }}
        .slide-number {{ color: var(--secondary-color); font-size: 14px; text-align: right; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="slide">
        <h1>{title}</h1>
        <p style="color: var(--secondary-color);">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
"""
    
    for slide_data in content_slides:
        slide_title = html.escape(str(slide_data.get('title', '幻灯片标题')))
        slide_content = html.escape(str(slide_data.get('content', ''))).replace('\n', '<br>')
        slide_number = html.escape(str(slide_data.get('slide_number', 0)))
        html_content += f"""
    <div class="slide">
        <h2>{slide_title}</h2>
        <div class="slide-content">{slide_content}</div>
        <div class="slide-number">{slide_number}</div>
    </div>
"""
    
    html_content += """</body></html>"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"HTML PPT 保存成功 | file: {filepath}")

async def generate_markdown_ppt(filepath: Path, outline: Dict[str, Any], req: PPTGenerationRequest):
    """生成 Markdown 格式 PPT"""
    md_content = f"# {outline.get('title', 'PPT 标题')}\n\n"
    md_content += f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n---\n\n"
    
    content_slides = _content_slides_for_total(
        outline.get("slides", []),
        getattr(req, "slide_count", None),
    )
    for slide_data in content_slides:
        md_content += f"## {slide_data.get('title', '幻灯片标题')}\n\n"
        md_content += f"{slide_data.get('content', '')}\n\n"
        
        if slide_data.get('notes'):
            md_content += f"> **备注**: {slide_data.get('notes')}\n\n"
        
        md_content += "---\n\n"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    logger.info(f"Markdown PPT 保存成功 | file: {filepath}")

def generate_preview_html(ppt_id: str) -> str:
    """生成预览 HTML 页面"""
    safe_id = html_escape(ppt_id, quote=True)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PPT 预览 - {html.escape(ppt_id)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: white; padding: 20px 30px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 24px; color: #1e293b; }}
        .slides-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 20px; }}
        .slide-card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .slide-header {{ background: #2563eb; color: white; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }}
        .slide-number {{ font-size: 14px; font-weight: 600; }}
        .slide-type {{ font-size: 12px; padding: 4px 8px; background: rgba(255,255,255,0.2); border-radius: 4px; }}
        .slide-body {{ padding: 20px; }}
        .slide-title {{ font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 12px; }}
        .slide-content {{ font-size: 14px; color: #64748b; line-height: 1.6; white-space: pre-line; }}
        .download-section {{ background: white; padding: 20px 30px; border-radius: 8px; margin-top: 20px; text-align: center; }}
        .download-btn {{ display: inline-block; padding: 12px 24px; background: #2563eb; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 0 10px; }}
        .download-btn:hover {{ background: #1d4ed8; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>PPT 预览</h1>
            <p style="color: #64748b; margin-top: 8px;">PPT ID: {html.escape(ppt_id)}</p>
        </div>
        
        <div class="download-section">
            <h2 style="margin-bottom: 16px;">下载 PPT</h2>
            <a href="/api/v1/pptx/download/{safe_id}?format=pptx" class="download-btn">下载 PowerPoint</a>
        </div>
        
        <div id="slides-container" class="slides-container">
            <!-- Slides will be loaded here -->
        </div>
    </div>
    
    <script>
        fetch('/api/v1/pptx/{html.escape(ppt_id)}' + '/slides')
            .then(r => r.json())
            .then(data => {{
                const container = document.getElementById('slides-container');
                if (data.slides) {{
                    data.slides.forEach((slide, idx) => {{
                        const card = document.createElement('div');
                        card.className = 'slide-card';
                        card.innerHTML = `
                            <div class="slide-header">
                                <span class="slide-number"></span>
                                <span class="slide-type"></span>
                            </div>
                            <div class="slide-body">
                                <div class="slide-title"></div>
                                <div class="slide-content"></div>
                            </div>
                        `;
                        card.querySelector('.slide-number').textContent = idx + 1;
                        card.querySelector('.slide-type').textContent = slide.slide_type || 'content';
                        card.querySelector('.slide-title').textContent = slide.title || '';
                        card.querySelector('.slide-content').textContent = slide.content || '';
                        container.appendChild(card);
                    }});
                }}
            }})
            .catch(err => {{
                console.error('加载幻灯片失败:', err);
                const container = document.getElementById('slides-container');
                container.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444;">加载幻灯片数据失败，请刷新页面重试。</div>';
            }});
    </script>
</body>
</html>"""

# =============================================================================
# API 路由
# =============================================================================


async def _build_generation_context(
    db: AsyncSession,
    user_id: str,
    conversation_id,
    material_file_ids,
    session_id,
) -> str:
    """拼装会话历史与素材上下文，供生成任务使用。"""
    context_parts = []
    if conversation_id:
        try:
            history_context = await compress_conversation_history(
                db, int(user_id), int(conversation_id), max_messages=5
            )
            if history_context:
                context_parts.append(f"\n[对话历史]\n{history_context}")
        except Exception as e:
            logger.warning(f"获取会话历史失败: {e}")

    material_context = await _build_material_context(
        db, user_id, material_file_ids, session_id
    )
    if material_context:
        context_parts.append(material_context)
    return "".join(context_parts)


@router.post("/pptx/generate_task", response_model=TaskResponse)
async def generate_ppt_task(
    req: PPTGenerationRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    使用任务队列生成 PPT（统一增强版）
    
    功能：
    - 支持多种输出格式 (PPTX, HTML, Markdown)
    - 支持模板系统与 Skills
    - 支持会话历史与素材文件绑定
    - PPTX 格式支持高级视觉决策与布局
    """
    user_id = token.get("sub", "anonymous")
    conversation_id = req.conversation_id

    if os.getenv("PPT_USE_CELERY", "false").lower() in {"1", "true", "yes"}:
        from app.services.ppt_dispatch_service import dispatch_ppt_to_celery

        task_id, celery_task_id = await dispatch_ppt_to_celery(
            db,
            int(user_id),
            req.model_dump(mode="json"),
        )
        task_options = req.options or {}
        if task_options.get("outline_id"):
            task_record = await db.scalar(
                select(Task).where(Task.task_id == task_id, Task.user_id == int(user_id))
            )
            if task_record:
                task_record.outline_id = str(task_options["outline_id"])
                task_record.outline_version = int(task_options["outline_version"])
                task_record.quality_mode = task_options.get("quality_mode", "standard")
                await db.commit()
        _register_ppt_owner(task_id, str(user_id))
        return TaskResponse(
            task_id=task_id,
            celery_task_id=celery_task_id,
            task_type="ppt_generation",
            status="pending",
            progress=0,
            progress_message="等待 Celery worker...",
            created_at=datetime.now().isoformat(),
        )
    
    # 解析 material_file_ids (兼容旧版 prompt 格式)
    material_file_ids = req.material_file_ids or []
    if not material_file_ids:
        try:
            match = re.search(r'<material>\[(.*?)\]</material>', req.topic)
            if match:
                material_file_ids = [int(x.strip()) for x in match.group(1).split(',')]
        except Exception: pass

    async def run_ppt_generation(task_id: str, **kwargs):
        _register_ppt_owner(task_id, user_id)
        async def update_progress(progress: int = 0, message: str = "", status: str = None, result_data: str = None, **_kwargs):
            await task_manager.update_progress(
                task_id,
                progress,
                message,
                status=status,
                result_data=result_data,
                error_message=_kwargs.get("error_message"),
            )

        try:
            await update_progress(progress=5, message="正在准备上下文...")
            
            # 1. 构建完整 Prompt
            full_prompt = req.topic
            context = await _build_generation_context(
                db, user_id, conversation_id, material_file_ids, req.session_id
            )
            req.topic = f"{full_prompt}\n\n{context}" if context else full_prompt

            # 2. 生成大纲
            await update_progress(progress=20, message="正在生成 PPT 大纲...")
            approved_outline = (req.options or {}).get("approved_outline")
            outline = (
                _normalize_approved_outline(approved_outline)
                if approved_outline
                else await generate_ppt_outline(req, user_id=user_id)
            )

            # 立即保存大纲快照（用于恢复/增量生成/历史查询）
            output_dir = PPT_OUTPUT_DIR
            output_dir.mkdir(exist_ok=True)
            snapshot_path = output_dir / f"{task_id}_slides.json"
            snapshot_data = {
                "user_id": str(user_id),
                "title": outline.get("title", ""),
                "slides": outline.get("slides", []),
            }
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
            logger.info(f"保存大纲快照 | task_id={task_id} | slides={len(outline.get('slides', []))}")
            trace = build_ppt_trace_context(
                req.options,
                req.template,
                (req.options or {}).get("quality_mode", "standard"),
            )
            await save_ppt_stage_checkpoint(
                db,
                task_id,
                int(user_id),
                1,
                "planning",
                trace,
                {"slides": outline.get("slides", [])},
            )
            await db.commit()
            
            # 3. 根据格式生成文件
            output_dir = PPT_OUTPUT_DIR
            output_dir.mkdir(exist_ok=True)
            
            ext_map = {
                OutputFormat.PPTX: "pptx",
                OutputFormat.HTML: "html",
                OutputFormat.MARKDOWN: "md",
                OutputFormat.PDF: "pdf"
            }
            ext = ext_map.get(req.output_format, "pptx")

            filepath = output_dir / f"{task_id}.{ext}"
            slides_data = outline.get('slides', [])
            quality_mode = (req.options or {}).get("quality_mode", "standard")
            quality_slides = [
                {
                    **slide,
                    "id": slide.get("id", f"slide-{index + 1}"),
                    "elements": slide.get("elements", []),
                    "render_metadata": build_render_metadata(
                        slide,
                        token_version=str(trace["template_version"]),
                    ),
                }
                for index, slide in enumerate(slides_data)
            ]
            quality_slides, quality_report = await run_quality_pipeline(quality_slides, "standard")
            outline = {**outline, "slides": quality_slides}
            slides_data = quality_slides
            await save_ppt_stage_checkpoint(
                db,
                task_id,
                int(user_id),
                2,
                "rule_qa",
                trace,
                {"quality": serialize_quality_report(quality_report)},
            )
            await db.commit()

            if req.output_format == OutputFormat.PDF:
                pptx_filepath = output_dir / f"{task_id}.pptx"
                await generate_pptx_file_enhanced(pptx_filepath, outline, req, update_progress=update_progress)
                await _convert_pptx_to_pdf(pptx_filepath, filepath)
            elif req.output_format == OutputFormat.HTML:
                await update_progress(progress=60, message="正在生成 HTML 格式...")
                await generate_html_ppt(filepath, outline, req)
            elif req.output_format == OutputFormat.MARKDOWN:
                await update_progress(progress=60, message="正在生成 Markdown 格式...")
                await generate_markdown_ppt(filepath, outline, req)
            else:
                # PPTX 为默认输出，使用高级视觉决策逻辑
                await generate_pptx_file_enhanced(filepath, outline, req, update_progress=update_progress, user_id=user_id)

            if quality_mode == "refined":
                from app.services.ppt_quality_orchestrator import review_rendered_deck

                await review_rendered_deck(
                    output_dir / f"{task_id}.pptx", quality_slides, quality_report,
                    req.api_key_token, str(user_id), req.slide_count,
                )

            result = {
                "filename": filepath.name,
                "ppt_id": task_id,
                "download_url": f"/api/v1/pptx/download/{task_id}?format={ext}",
                "preview_url": _preview_url(task_id, req.output_format) if req.output_format in {OutputFormat.PPTX, OutputFormat.HTML, OutputFormat.MARKDOWN} else None
            }
            await persist_ppt_generation_result(
                db,
                task_id,
                int(user_id),
                filepath,
                "pptx" if ext == "pptx" else ext,
                result,
                trace,
                slides_data,
                quality_report,
            )
            await update_progress(
                progress=100,
                message="PPT 生成完成",
                status="completed",
                result_data=json.dumps(result)
            )
            return result
            
        except asyncio.CancelledError:
            # 取消时清理部分写入的 PPTX 文件，保留 JSON 中间状态用于恢复
            try:
                partial_pptx = filepath if 'filepath' in dir() else None
                if partial_pptx and isinstance(partial_pptx, Path) and partial_pptx.exists():
                    partial_pptx.unlink(missing_ok=True)
                    logger.info(f"已清理取消任务的部分文件：{partial_pptx}")
            except Exception:
                pass
            await update_progress(
                status="cancelled",
                message="任务已取消，中间状态已保存",
                result_data=json.dumps({
                    "ppt_id": task_id,
                    "outline_saved": True,
                    "download_url": f"/api/v1/pptx/{task_id}/slides"
                })
            )
            logger.info(f"PPT 任务已取消 | task_id={task_id}")
        except Exception as e:
            await update_progress(
                status="failed",
                message="PPT 生成失败，请稍后重试",
                error_message=str(e)
            )
            logger.error(f"PPT 生成任务失败 | task_id: {task_id} | error: {str(e)}")
    
    task_response = await task_manager.create_task(
        task_type="ppt_generation",
        user_id=user_id,
        func=run_ppt_generation,
        params={}
    )

    # 将批准的大纲快照写入任务记录，保证生成任务可追溯。
    task_options = req.options or {}
    if task_options.get("outline_id"):
        task_record = await db.scalar(
            select(Task).where(Task.task_id == task_response, Task.user_id == int(user_id))
        )
        if task_record:
            task_record.outline_id = str(task_options["outline_id"])
            task_record.outline_version = int(task_options["outline_version"])
            task_record.quality_mode = task_options.get("quality_mode", "standard")
            await db.commit()

    logger.info(f"创建 PPT 生成任务 | task_id: {task_response} | user: {user_id}")
    return TaskResponse(
        task_id=task_response,
        task_type="ppt_generation",
        status="pending",
        progress=0,
        progress_message="等待中...",
        created_at=datetime.now().isoformat()
    )


@router.post("/pptx/generate", response_model=PPTGenerationResponse)
async def generate_ppt(
    req: PPTGenerationRequest,
    token: dict = Depends(verify_token)
):
    """
    生成 PPT（阻塞式同步接口）
    适用于页数较少或需要即时结果的场景
    """
    user_id = token.get("sub", "anonymous")
    ppt_id = str(uuid.uuid4())
    logger.info(f"PPT 同步生成请求 | user: {user_id} | topic: {req.topic[:50]}...")
    
    try:
        outline = await generate_ppt_outline(req, user_id=user_id)
        
        output_dir = PPT_OUTPUT_DIR
        output_dir.mkdir(exist_ok=True)
        
        ext_map = {OutputFormat.PPTX: "pptx", OutputFormat.HTML: "html", OutputFormat.MARKDOWN: "md"}
        ext = ext_map.get(req.output_format, "pptx")
        filepath = output_dir / f"{ppt_id}.{ext}"
        
        if req.output_format == OutputFormat.PPTX:
            await generate_pptx_file_enhanced(filepath, outline, req, user_id=user_id)
        elif req.output_format == OutputFormat.HTML:
            await generate_html_ppt(filepath, outline, req)
        elif req.output_format == OutputFormat.MARKDOWN:
            await generate_markdown_ppt(filepath, outline, req)
        else:
            await generate_pptx_file_enhanced(filepath, outline, req, user_id=user_id)

        _register_ppt_owner(ppt_id, user_id)
        return PPTGenerationResponse(
            id=ppt_id,
            status="completed",
            topic=req.topic[:50],
            slide_count=len(outline.get('slides', [])),
            output_format=req.output_format.value,
            created_at=datetime.now().isoformat(),
            download_url=f"/api/v1/pptx/download/{ppt_id}?format={ext}",
            preview_url=_preview_url(ppt_id, req.output_format) if req.output_format in {OutputFormat.PPTX, OutputFormat.HTML, OutputFormat.MARKDOWN} else None,
            slides=outline.get('slides', [])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PPT 同步生成失败 | error: {str(e)}")
        raise HTTPException(status_code=500, detail="PPT 生成失败，请稍后重试")


@router.get("/pptx/download/{ppt_id}")
async def download_ppt(
    ppt_id: str,
    format: str = Query(default="pptx", description="下载格式"),
    token: dict = Depends(verify_token)
):
    """下载 PPT 文件"""
    _validate_ppt_id(ppt_id)
    user_id = token.get("sub", "anonymous")
    _verify_ppt_owner(ppt_id, user_id)
    output_dir = PPT_OUTPUT_DIR
    
    requested_extension = "md" if format == "markdown" else format
    supported_extensions = ["pptx", "pdf", "html", "md"]
    if requested_extension in supported_extensions:
        possible_extensions = [requested_extension]
    else:
        raise HTTPException(status_code=400, detail="不支持的下载格式")
        
    filepath = None
    for ext in possible_extensions:
        test_path = output_dir / f"{ppt_id}.{ext}"
        if test_path.exists():
            filepath = test_path
            break

    if not filepath:
        raise HTTPException(status_code=404, detail="PPT 文件不存在")
    
    actual_format = filepath.suffix.lstrip('.')
    logger.info(f"下载 PPT | user: {user_id} | file: {filepath.name}")
    
    async def file_stream():
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                yield chunk
    
    mime_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "html": "text/html",
        "md": "text/markdown",
        "pdf": "application/pdf"
    }

    # 转义文件名，防止 Content-Disposition 头注入
    safe_name = filepath.name.replace('"', '\\"').replace('\r', '').replace('\n', '')

    return StreamingResponse(
        file_stream(),
        media_type=mime_types.get(actual_format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"'
        }
    )


@router.get("/pptx/preview/{ppt_id}", response_class=HTMLResponse)
async def preview_ppt(
    ppt_id: str,
    format: str = Query(default="pptx", description="预览格式"),
    token: dict = Depends(verify_token)
):
    """在线预览 PPT"""
    _validate_ppt_id(ppt_id)
    user_id = token.get("sub", "anonymous")
    _verify_ppt_owner(ppt_id, user_id)
    output_dir = PPT_OUTPUT_DIR
    if format not in {"pptx", "html", "markdown", "md"}:
        raise HTTPException(status_code=400, detail="不支持的预览格式")
    extension = "md" if format == "markdown" else format
    artifact_path = output_dir / f"{ppt_id}.{extension}"
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="PPT 文件不存在")

    logger.info(f"预览 PPT | user: {user_id} | ppt_id: {ppt_id}")
    if extension == "html":
        return HTMLResponse(content=artifact_path.read_text(encoding="utf-8"))
    if extension == "md":
        markdown = html.escape(artifact_path.read_text(encoding="utf-8"))
        return HTMLResponse(content=f"<html><body><pre>{markdown}</pre></body></html>")
    return HTMLResponse(content=generate_preview_html(ppt_id))


@router.get("/pptx/{ppt_id}/slides")
async def get_ppt_slides(
    ppt_id: str,
    token: dict = Depends(verify_token)
):
    """获取 PPT 幻灯片数据 (JSON)"""
    _validate_ppt_id(ppt_id)
    _verify_ppt_owner(ppt_id, token.get("sub", "anonymous"))
    output_dir = PPT_OUTPUT_DIR
    json_path = output_dir / f"{ppt_id}_slides.json"
    
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        # 兼容新格式（dict with "slides" key）和旧格式（list）
        slides_data = raw_data.get("slides", raw_data) if isinstance(raw_data, dict) else raw_data
        return {"slides": slides_data}
    
    raise HTTPException(status_code=404, detail="幻灯片数据不存在")


@router.delete("/pptx/{task_id}/cancel")
async def cancel_ppt_task(
    task_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """取消正在进行的 PPT 生成任务，并保存中间状态"""
    _validate_ppt_id(task_id)
    user_id = token.get("sub")

    task_info = await task_manager.get_task_info_async(task_id)
    if task_info:
        if task_info.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权取消此任务")

        if task_info.get("status") in ["success", "failed", "cancelled"]:
            return {"status": "already_finished", "message": f"任务已结束（{task_info['status']}）"}

        success = await task_manager.cancel_task(task_id)
        if success:
            logger.info(f"取消 PPT 任务 | task_id={task_id} | user={user_id}")
            return {"status": "cancelled", "message": "任务已取消"}
        return {"status": "not_running", "message": "任务未在执行"}

    try:
        task_record = await get_owned_task(db, task_id, int(user_id))
    except Exception as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error

    if task_record.status in ["success", "failed", "cancelled"]:
        return {"status": "already_finished", "message": f"任务已结束（{task_record.status}）"}

    if task_record.celery_task_id:
        celery_app.control.revoke(task_record.celery_task_id, terminate=True, signal="SIGTERM")
        await transition_task(db, task_id, int(user_id), "cancelled", progress=task_record.progress or 0)
        await db.commit()
        logger.info(f"取消 Celery PPT 任务 | task_id={task_id} | user={user_id}")
        return {"status": "cancelled", "message": "任务已取消"}

    return {"status": "not_running", "message": "任务未在执行"}


@router.post("/pptx/{task_id}/update", response_model=TaskResponse)
async def update_ppt_task(
    task_id: str,
    body: PPTGenerationRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """基于已有的大纲/中间状态增量生成 PPT"""
    _validate_ppt_id(task_id)
    user_id = token.get("sub")
    _verify_ppt_owner(task_id, user_id)
    output_dir = PPT_OUTPUT_DIR

    # 查找之前的幻灯片数据
    json_path = output_dir / f"{task_id}_slides.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="找不到中间状态数据，无法增量生成")

    with open(json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    # 兼容新格式（dict with "slides" key）和旧格式（list）
    existing_slides = raw_data.get("slides", raw_data) if isinstance(raw_data, dict) else raw_data

    # 用户隔离：检查 PPT 归属
    if isinstance(raw_data, dict) and raw_data.get("user_id") and str(raw_data["user_id"]) != str(user_id):
        raise HTTPException(status_code=403, detail="无权更新此任务")

    async def run_incremental_ppt(task_id: str, **kwargs):
        async def update_progress(progress: int = 0, message: str = "", status: str = None, result_data: str = None, **_kwargs):
            await task_manager.update_progress(
                task_id,
                progress,
                message,
                status=status,
                result_data=result_data,
                error_message=_kwargs.get("error_message"),
            )

        try:
            await update_progress(progress=5, message="正在加载已有内容...")

            # 生成新的增量大纲
            new_req = body
            # 修改 prompt 要求增量生成
            incremental_prompt = f"""
已有 PPT 大纲内容：
{json.dumps(existing_slides, ensure_ascii=False, indent=2)}

请在已有内容基础上，根据以下新需求进行增量更新（新增幻灯片或修改内容）：

{new_req.topic}

要求：
- 保留已有幻灯片的核心内容
- 新增或修改内容以满足新需求
- 返回完整的合并后 JSON 大纲（包含所有幻灯片）
- 格式与已有大纲一致
"""
            new_req.topic = incremental_prompt

            await update_progress(progress=20, message="正在生成增量内容...")
            new_outline = await generate_ppt_outline(new_req, user_id=user_id)

            new_slides = new_outline.get('slides', []) or existing_slides
            if not new_slides:
                await update_progress(progress=100, message="增量生成失败：无法生成有效大纲", status="failed")
                return
            new_title = new_outline.get('title') or (existing_slides[0].get('title', 'PPT') if existing_slides else 'PPT')

            output_id = task_id
            filepath = output_dir / f"{output_id}.{new_req.output_format.value}"

            if new_req.output_format == OutputFormat.PDF:
                await update_progress(progress=50, message="正在渲染 PPTX...")
                merged_outline = {"title": new_title, "slides": new_slides}
                pptx_filepath = output_dir / f"{output_id}.pptx"
                await generate_pptx_file_enhanced(pptx_filepath, merged_outline, new_req, update_progress=update_progress, user_id=user_id)
                await _convert_pptx_to_pdf(pptx_filepath, filepath)
            elif new_req.output_format == OutputFormat.HTML:
                await update_progress(progress=60, message="正在生成 HTML...")
                merged_outline = {"title": new_title, "slides": new_slides}
                await generate_html_ppt(filepath, merged_outline, new_req)
            elif new_req.output_format == OutputFormat.MARKDOWN:
                await update_progress(progress=60, message="正在生成 Markdown...")
                merged_outline = {"title": new_title, "slides": new_slides}
                await generate_markdown_ppt(filepath, merged_outline, new_req)
            else:
                await update_progress(progress=50, message="正在渲染 PPTX...")
                merged_outline = {"title": new_title, "slides": new_slides}
                await generate_pptx_file_enhanced(filepath, merged_outline, new_req, update_progress=update_progress, user_id=user_id)

            # 只有新文件生成成功后才更新快照，保留上一版可恢复内容。
            new_json_path = output_dir / f"{output_id}_slides.json"
            with open(new_json_path, 'w', encoding='utf-8') as f:
                json.dump(new_slides, f, ensure_ascii=False, indent=2)
            _register_ppt_owner(output_id, user_id)
            logger.info(f"更新大纲快照 | task_id={output_id} | slides={len(new_slides)}")

            ext_map = {OutputFormat.PPTX: "pptx", OutputFormat.HTML: "html", OutputFormat.MARKDOWN: "md", OutputFormat.PDF: "pdf"}
            ext = ext_map.get(new_req.output_format, "pptx")

            result = {
                "filename": filepath.name,
                "ppt_id": output_id,
                "download_url": f"/api/v1/pptx/download/{output_id}?format={ext}",
                "preview_url": _preview_url(output_id, new_req.output_format) if new_req.output_format in {OutputFormat.PPTX, OutputFormat.HTML, OutputFormat.MARKDOWN} else None
            }
            await update_progress(
                progress=100,
                message="PPT 更新完成",
                status="completed",
                result_data=json.dumps(result)
            )
            return result

        except Exception as e:
            await update_progress(
                status="failed",
                message="PPT 更新失败，请稍后重试",
                error_message=str(e)
            )
            logger.error(f"PPT 更新任务失败 | task_id: {task_id} | error: {str(e)}")

    task_response = await task_manager.create_task(
        task_type="ppt_update",
        user_id=user_id,
        func=run_incremental_ppt,
        params={}
    )

    logger.info(f"创建 PPT 更新任务 | task_id: {task_response} | base_task: {task_id} | user: {user_id}")
    return TaskResponse(
        task_id=task_response,
        task_type="ppt_update",
        status="pending",
        progress=0,
        progress_message="等待中...",
        created_at=datetime.now().isoformat()
    )


# =============================================================================
# 视觉增强 PPT 修改
# =============================================================================


@router.post("/pptx/{task_id}/modify")
async def modify_ppt_visual_endpoint(
    task_id: str,
    body: PPTModifyRequest,
    token: dict = Depends(verify_token),
):
    """
    视觉增强 PPT 修改

    基于已有 PPTX 文件，通过自然语言修改需求进行精确修改。
    支持修改字体、颜色、布局等属性。

    流程：
    1. 解析用户修改需求
    2. 视觉分析目标幻灯片
    3. 应用修改
    4. 返回修改结果和预览图
    """
    _validate_ppt_id(task_id)
    user_id = token.get("sub", "anonymous")
    output_dir = PPT_OUTPUT_DIR
    _verify_ppt_owner(task_id, user_id)

    # 查找已有的 PPTX 文件
    pptx_path = output_dir / f"{task_id}.pptx"
    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail=f"找不到 PPT 文件：{task_id}")

    try:
        from app.utils.pptx.visual_modifier import modify_ppt_visual

        # 生成新的 task_id 用于存储修改后的文件
        new_task_id = str(uuid.uuid4())
        new_pptx_path = output_dir / f"{new_task_id}.pptx"

        logger.info("PPT 视觉修改请求 | user: %s | base_task: %s | input: %s",
                    user_id, task_id, body.user_input[:100])

        # 执行视觉增强修改
        result = await modify_ppt_visual(
            pptx_path=str(pptx_path),
            user_input=body.user_input,
            output_path=str(new_pptx_path),
            api_key_token=body.api_key_token,
            user_id=user_id,
            analyze_before_modify=body.analyze_before_modify
        )

        if result["success"]:
            _register_ppt_owner(new_task_id, user_id)
            return {
                "success": True,
                "message": result["message"],
                "task_id": new_task_id,
                "download_url": f"/api/v1/pptx/download/{new_task_id}",
                "preview_url": f"/api/v1/pptx/preview/{new_task_id}",
                "intent": result.get("intent"),
                "analysis": result.get("analysis"),
                "preview_count": result.get("preview_count", 0)
            }
        else:
            return {
                "success": False,
                "message": result["message"],
                "intent": result.get("intent"),
                "analysis": result.get("analysis")
            }

    except Exception as exc:
        logger.error("PPT 视觉修改失败 | task_id: %s | error: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="修改失败，请稍后重试")


@router.get("/pptx/{task_id}/analyze")
async def analyze_ppt_endpoint(
    task_id: str,
    slide_number: Optional[int] = Query(None, description="指定幻灯片编号"),
    api_key_token: Optional[str] = Query(None, description="用户 API Key Token"),
    token: dict = Depends(verify_token),
):
    """
    分析 PPT 视觉状态（不执行修改）

    返回 PPT 的布局、字体、颜色等信息，用于了解当前状态。
    """
    user_id = token.get("sub", "anonymous")
    _verify_ppt_owner(task_id, user_id)
    output_dir = PPT_OUTPUT_DIR
    pptx_path = output_dir / f"{task_id}.pptx"

    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail=f"找不到 PPT 文件：{task_id}")

    try:
        from app.utils.pptx.visual_modifier import analyze_ppt_for_modification

        result = await analyze_ppt_for_modification(
            pptx_path=str(pptx_path),
            slide_number=slide_number,
            api_key_token=api_key_token,
            user_id=user_id
        )

        return result

    except Exception as exc:
        logger.error("PPT 分析失败 | task_id: %s | error: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="分析失败，请稍后重试")


# =============================================================================
# 模板与历史管理
# =============================================================================


@router.get("/pptx/templates")
async def list_ppt_templates(
    category: Optional[str] = Query(None, description="按分类筛选"),
    scenario: Optional[str] = Query(
        None,
        pattern="^(business|data_report|product_pitch|academic|education|general)$",
        description="按演示场景推荐",
    ),
    topic: str = Query("", max_length=5000, description="用于场景识别的主题"),
    token: dict = Depends(verify_token)
):
    """获取可用 PPT 模板列表"""
    if scenario or topic:
        recommendation = TemplateManager().recommend_for_scenario(topic, scenario=scenario)
        return recommendation
    templates = TemplateManager().list_templates()
    from app.services.ppt_template_samples import ensure_template_sample
    for template in templates:
        try:
            template["sample"] = await ensure_template_sample(template["id"])
        except Exception as exc:
            logger.warning("模板样张不可用 %s: %s", template["id"], exc)
            template["sample"] = {"version": "v1", "status": "unavailable", "reason": "render_failed"}
    if category:
        templates = [tpl for tpl in templates if tpl["category"] == category]
    return {"templates": templates}


@router.get("/pptx/templates/{template_id}/preview/{page}")
async def get_template_sample(template_id: str, page: int):
    if page < 1 or page > 3:
        raise HTTPException(status_code=422, detail="样张页码必须为 1 到 3")
    from app.services.ppt_template_samples import _paths, ensure_template_sample
    from app.utils.pptx.templates.manager import TemplateManager
    try:
        # 解析别名到规范 id，保证缓存目录与 _paths 命中同一位置
        template_id = TemplateManager().select_template(template_id)
    except KeyError:
        # 未知模板是请求侧问题，返回 404 而不是让 KeyError 冒泡成 500
        raise HTTPException(status_code=404, detail="模板不存在")
    await ensure_template_sample(template_id)
    path = _paths(template_id)["png_dir"] / f"slide-{page}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="模板样张暂不可用")
    return FileResponse(path, media_type="image/png")


@router.get("/pptx/history")
async def list_ppt_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    token: dict = Depends(verify_token)
):
    """获取当前用户的 PPT 生成历史"""
    user_id = token.get("sub", "anonymous")
    output_dir = PPT_OUTPUT_DIR

    if not output_dir.exists():
        return {"records": [], "total": 0}

    records = []
    for json_path in sorted(output_dir.glob("*_slides.json"), reverse=True):
        ppt_id = json_path.name.replace("_slides.json", "")
        record = _ppt_history_record(ppt_id, json_path, str(user_id))
        if record is None:
            continue
        records.append(record)

    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size
    total_pages = (total + page_size - 1) // page_size if page_size else 1
    return {
        "records": records[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.delete("/pptx/history/{task_id}")
async def delete_ppt_history(
    task_id: str,
    token: dict = Depends(verify_token)
):
    """删除指定 PPT 历史记录及其文件"""
    user_id = token.get("sub", "anonymous")
    _verify_ppt_owner(task_id, user_id)
    output_dir = PPT_OUTPUT_DIR
    json_path = output_dir / f"{task_id}_slides.json"

    if not json_path.exists():
        raise HTTPException(status_code=404, detail="记录不存在")

    # 用户隔离：检查 PPT 归属
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        if isinstance(raw_data, dict) and raw_data.get("user_id") and str(raw_data["user_id"]) != str(user_id):
            raise HTTPException(status_code=403, detail="无权删除此记录")
    except HTTPException:
        raise
    except Exception:
        pass  # 旧格式或读取失败，允许删除

    json_path.unlink(missing_ok=True)
    for ext in ["pptx", "html", "md", "pdf"]:
        (output_dir / f"{task_id}.{ext}").unlink(missing_ok=True)
    (PPT_OWNER_DIR / f"{task_id}.json").unlink(missing_ok=True)

    return {"success": True, "message": f"已删除 {task_id}"}


@router.get("/pptx/history/stats")
async def get_ppt_stats(
    token: dict = Depends(verify_token)
):
    """获取 PPT 生成统计信息"""
    user_id = str(token.get("sub", "anonymous"))
    output_dir = PPT_OUTPUT_DIR
    if not output_dir.exists():
        return {"total": 0, "completed": 0, "failed": 0}

    owned_ids = []
    for owner_path in PPT_OWNER_DIR.glob("*.json"):
        try:
            with open(owner_path, "r", encoding="utf-8") as owner_file:
                if str(json.load(owner_file).get("user_id")) == user_id:
                    owned_ids.append(owner_path.stem)
        except (OSError, ValueError):
            continue
    total = sum((output_dir / f"{ppt_id}_slides.json").exists() for ppt_id in owned_ids)
    completed = sum((output_dir / f"{ppt_id}.pptx").exists() for ppt_id in owned_ids)
    return {"total": total, "completed": completed, "failed": 0}


@router.get("/pptx/history/{ppt_id}")
async def get_ppt_history_detail(
    ppt_id: str,
    token: dict = Depends(verify_token)
):
    """按 PPT ID 返回单条历史记录及下载地址。"""
    user_id = str(token.get("sub", "anonymous"))
    _verify_ppt_owner(ppt_id, user_id)
    json_path = PPT_OUTPUT_DIR / f"{ppt_id}_slides.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="记录不存在")
    record = _ppt_history_record(ppt_id, json_path, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


# =============================================================================
# 文本防溢出
# =============================================================================

def prevent_text_overflow(
    text: str, 
    max_chars_per_line: int = 70, 
    max_lines: int = 6, 
    shrink_font: bool = True
) -> List[str]:
    """
    防止文本在 PPT 幻灯片中溢出。
    
    使用新的智能文本处理模块:
    - 中文按字数换行
    - 英文按单词边界换行
    - 自动字号调整
    
    Args:
        text: 原始文本
        max_chars_per_line: 每行最大字符数
        max_lines: 最大行数限制
        shrink_font: 是否建议缩小字号
        
    Returns:
        处理后的文本行列表
    """
    layout = prevent_text_overflow_v2(
        text,
        max_chars_per_line=max_chars_per_line,
        max_lines=max_lines,
    )
    
    if layout.needs_overflow_warning:
        logger.warning(layout.overflow_message)
    
    return layout.lines


# =============================================================================
# PPT Agent API 端点
# =============================================================================

class OutlineSlide(BaseModel):
    """大纲中的单页幻灯片"""
    type: str = Field(..., description="幻灯片类型")
    title: str = Field(..., description="幻灯片标题")
    bullets: List[str] = Field(default_factory=list, description="要点列表")
    image_keywords: List[str] = Field(default_factory=list, description="配图关键词")
    notes: str = Field(default="", description="备注")
    narrative_role: str = Field(default="", description="商业叙事角色")
    content_blocks: List[Dict[str, Any]] = Field(default_factory=list, description="结构化商业内容块")

class OutlineGenerationRequest(BaseModel):
    """大纲生成请求"""
    topic: str = Field(..., description="PPT 主题", max_length=500)
    description: str = Field(default="", description="详细描述", max_length=2000)
    num_slides: int = Field(default=10, ge=1, le=PPT_MAX_SLIDES, description="幻灯片数量")
    model: str = Field(default=PPT_DEFAULT_MODEL, description="AI 模型")
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token")

class OutlineGenerationResponse(BaseModel):
    """大纲生成响应"""
    title: str
    slides: List[OutlineSlide]
    total_slides: int
    outline_id: Optional[str] = None
    outline_version: Optional[int] = None
    status: Optional[str] = None


@router.post("/generate-text", response_model=OutlineGenerationResponse)
async def generate_ppt_from_text(
    req: OutlineGenerationRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    自然语言生成 PPT 大纲 (仅返回结构化数据，不生成文件)
    """
    user_id = token.get("sub", "anonymous")
    logger.info("PPT Agent 请求 | user: %s | topic: %s", user_id, req.topic[:50])

    try:
        draft = await persist_create_ppt_outline(
            db,
            str(user_id),
            OutlineCreateRequest(
                topic=req.topic,
                description=req.description,
                num_slides=req.num_slides,
                model=req.model,
                api_key_token=req.api_key_token,
            ),
        )

        if not draft or not draft.slides:
            raise HTTPException(status_code=500, detail="大纲生成失败：无法生成有效大纲")

        return OutlineGenerationResponse(
            title=draft.title,
            slides=[
                OutlineSlide(
                    type=slide.slide_type,
                    title=slide.title,
                    bullets=[block.content for block in slide.content_blocks],
                    image_keywords=slide.asset_intent.keywords if slide.asset_intent else [],
                    notes=slide.speaker_notes,
                    narrative_role=slide.narrative_role,
                    content_blocks=[block.model_dump(mode="json") for block in slide.content_blocks],
                )
                for slide in draft.slides
            ],
            total_slides=1 + len(draft.slides),
            outline_id=draft.id,
            outline_version=draft.version,
            status=draft.status,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PPT Agent 大纲生成失败 | error: %s", exc)
        raise HTTPException(status_code=500, detail="大纲生成失败，请稍后重试")


@router.post("/generate-from-text", response_model=TaskResponse)
async def generate_ppt_from_text_task(
    req: OutlineGenerationRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    端到端: 自然语言 -> 大纲 -> PPTX 文件 (任务队列)
    """
    user_id = token.get("sub", "anonymous")
    logger.info("PPT Agent 端到端请求 | user: %s | topic: %s", user_id, req.topic[:50])

    try:
        draft = await persist_create_ppt_outline(
            db,
            str(user_id),
            OutlineCreateRequest(
                topic=req.topic,
                description=req.description,
                num_slides=req.num_slides,
                model=req.model,
                api_key_token=req.api_key_token,
            ),
        )
        approved = await persist_approve_ppt_outline(db, str(user_id), draft.id)
        return await generate_ppt_from_approved_outline(
            approved.id,
            OutlineGenerateRequest(outline_version=approved.version),
            token,
            db,
        )

    except Exception as exc:
        logger.error("PPT Agent 端到端失败 | error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="生成失败")


# =============================================================================
# 文件上传生成 PPT
# =============================================================================

# 支持的文件扩展名
_PPT_FILE_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".docx", ".doc",
    ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".csv", ".log", ".rst", ".html", ".css",
}

# 文件上传端点支持的输出格式，与 Form 参数文档保持一致
_PPT_FILE_OUTPUT_FORMATS = {"pptx", "html", "markdown"}


async def _stream_upload_to_path(file: UploadFile, destination: Path, max_size: int) -> int:
    """Persist an upload in bounded chunks and return its byte count."""
    total_size = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > max_size:
                raise HTTPException(status_code=400, detail=f"文件过大，最大支持 {max_size // 1024 // 1024}MB")
            output.write(chunk)
    return total_size


async def _parse_uploaded_document(temp_path: Path) -> str:
    """在工作线程中解析上传文档，避免同步 CPU/IO 解析阻塞事件循环。"""
    from app.utils.aicloud.knowledge_processor import parse_document

    return await asyncio.to_thread(parse_document, str(temp_path))


@router.post("/pptx/generate_from_file", response_model=TaskResponse)
async def generate_ppt_from_file(
    file: UploadFile = FastAPIFile(..., description="上传文件 (PDF/Word/TXT/MD 等)"),
    template: str = Form(default="auto", description="模板风格"),
    slide_count: int = Form(default=10, ge=5, le=PPT_MAX_SLIDES, description="页数"),
    output_format: str = Form(default="pptx", description="输出格式 (pptx/html/markdown)"),
    extra_prompt: str = Form(default="", description="额外提示词"),
    api_key_token: Optional[str] = Form(default=None, description="用户 API Key Token"),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    上传文件生成 PPT

    支持格式: PDF, Word, TXT, Markdown, 代码文件等
    流程: 上传文件 → 解析内容 → AI 生成大纲 → 生成 PPT
    """
    user_id = token.get("sub", "anonymous")

    if output_format not in _PPT_FILE_OUTPUT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的输出格式: {output_format}。支持: {', '.join(sorted(_PPT_FILE_OUTPUT_FORMATS))}",
        )

    # 验证文件扩展名
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in _PPT_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}。支持: {', '.join(sorted(_PPT_FILE_EXTENSIONS))}"
        )

    # 保存上传文件到临时目录
    upload_dir = BASE_DIR / "uploads" / "ppt_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    temp_path = upload_dir / f"{file_id}{suffix}"

    try:
        await _stream_upload_to_path(file, temp_path, 50 * 1024 * 1024)
    except HTTPException:
        raise
    except Exception:
        logger.error("上传文件保存失败", exc_info=True)
        raise HTTPException(status_code=500, detail="文件保存失败")

    # 解析文件内容
    try:
        parsed_text = await _parse_uploaded_document(temp_path)
        if not parsed_text or not parsed_text.strip():
            raise HTTPException(status_code=400, detail="文件内容为空或无法解析")
    except HTTPException:
        raise
    except Exception:
        logger.error("上传文件解析失败", exc_info=True)
        raise HTTPException(status_code=500, detail="文件解析失败")

    # 截断过长内容（避免 token 超限）
    max_chars = 30000
    if len(parsed_text) > max_chars:
        parsed_text = parsed_text[:max_chars] + f"\n\n[内容过长，已截断至 {max_chars} 字符]"

    # 构建 PPT 请求
    topic = f"根据以下文件内容生成 PPT：\n\n文件名: {filename}\n\n文件内容:\n{parsed_text}"
    if extra_prompt:
        topic += f"\n\n用户要求: {extra_prompt}"

    # 文件正文由服务端截断到 30000 字符，可能超过请求模型对用户输入
    # 设置的 5000 字上限；先按正常规则校验其它字段，再写入服务端拼装的 topic。
    req = PPTGenerationRequest(
        topic="文件解析结果",
        template=template,
        slide_count=slide_count,
        output_format=output_format,
        api_key_token=api_key_token,
    )
    req.topic = topic

    async def run_file_ppt_generation(task_id: str, **kwargs):
        _register_ppt_owner(task_id, user_id)
        async def update_progress(progress: int = 0, message: str = "", status: str = None, result_data: str = None, **_kwargs):
            await task_manager.update_progress(
                task_id,
                progress,
                message,
                status=status,
                result_data=result_data,
                error_message=_kwargs.get("error_message"),
            )

        try:
            await update_progress(progress=5, message="正在解析文件内容...")

            # 生成大纲
            await update_progress(progress=20, message="正在根据文件内容生成 PPT 大纲...")
            outline = await generate_ppt_outline(req, user_id=user_id)

            # 保存大纲快照
            output_dir = PPT_OUTPUT_DIR
            output_dir.mkdir(exist_ok=True)
            snapshot_path = output_dir / f"{task_id}_slides.json"
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(outline.get('slides', []), f, ensure_ascii=False, indent=2)

            # 根据格式生成文件
            ext_map = {"pptx": "pptx", "html": "html", "markdown": "md"}
            ext = ext_map.get(output_format, "pptx")
            filepath = output_dir / f"{task_id}.{ext}"

            if output_format == "html":
                await update_progress(progress=60, message="正在生成 HTML 格式...")
                await generate_html_ppt(filepath, outline, req)
            elif output_format == "markdown":
                await update_progress(progress=60, message="正在生成 Markdown 格式...")
                await generate_markdown_ppt(filepath, outline, req)
            else:
                await generate_pptx_file_enhanced(filepath, outline, req, update_progress=update_progress)

            result = {
                "filename": filepath.name,
                "ppt_id": task_id,
                "source_file": filename,
                "download_url": f"/api/v1/pptx/download/{task_id}?format={ext}",
                "preview_url": f"/api/v1/pptx/preview/{task_id}?format={output_format}" if output_format in {"pptx", "html", "markdown"} else None,
            }
            await update_progress(
                progress=100,
                message="PPT 生成完成",
                status="completed",
                result_data=json.dumps(result)
            )
            return result

        except asyncio.CancelledError:
            await update_progress(status="cancelled", message="任务已取消")
        except Exception as e:
            await update_progress(status="failed", message=f"生成失败: {e}", error_message=str(e))
            logger.error(f"文件 PPT 生成失败 | task_id: {task_id} | error: {e}")
        finally:
            # 清理临时文件
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

    task_response = await task_manager.create_task(
        task_type="ppt_generation",
        user_id=user_id,
        func=run_file_ppt_generation,
        params={},
    )

    logger.info(f"文件 PPT 生成任务 | task_id: {task_response} | file: {filename} | user: {user_id}")
    return TaskResponse(
        task_id=task_response,
        task_type="ppt_generation",
        status="pending",
        progress=0,
        progress_message="等待中...",
        created_at=datetime.now().isoformat()
    )


# =============================================================================
# 自定义模板上传
# =============================================================================

@router.post("/pptx/templates/upload")
async def upload_custom_template(
    file: UploadFile = FastAPIFile(..., description="上传 PPTX 模板文件"),
    name: str = Form(..., description="模板名称"),
    description: str = Form(default="", description="模板描述"),
    token: dict = Depends(verify_token),
):
    """
    上传自定义 PPT 模板

    上传 .pptx 文件作为模板，系统会解析母版配置（配色、字体、布局）
    """
    user_id = token.get("sub", "anonymous")

    # 验证文件类型
    filename = file.filename or "unknown"
    if not filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="仅支持 .pptx 格式")

    # 保存模板文件
    template_dir = BASE_DIR / "configs" / "ppt" / "custom_templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    template_id = f"custom_{user_id}_{uuid.uuid4().hex[:8]}"
    template_path = template_dir / f"{template_id}.pptx"

    try:
        await _stream_upload_to_path(file, template_path, 20 * 1024 * 1024)
    except HTTPException:
        raise
    except Exception:
        logger.error("模板保存失败", exc_info=True)
        raise HTTPException(status_code=500, detail="模板保存失败")

    # 解析模板配置
    try:
        from app.utils.pptx.custom_template import CustomTemplateParser
        parser = CustomTemplateParser()
        # 模板解析是 CPU/IO 密集的同步操作，放入线程池避免阻塞事件循环
        config = await asyncio.to_thread(parser.parse_template_file, str(template_path))

        # 保存配置
        config_path = template_dir / f"{template_id}.json"
        config_dict = config.to_dict()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

        return {
            "template_id": template_id,
            "name": name,
            "description": description,
            "config": config_dict,
            "message": "模板上传成功",
        }
    except Exception as e:
        logger.warning(f"模板解析失败: {e}")
        # 即使解析失败也保留文件，用户可以手动使用
        return {
            "template_id": template_id,
            "name": name,
            "description": description,
            "config": None,
            "message": f"模板上传成功，但自动解析失败: {e}",
        }


@router.get("/pptx/templates/custom")
async def list_custom_templates(
    token: dict = Depends(verify_token),
):
    """列出用户上传的自定义模板"""
    user_id = token.get("sub", "anonymous")
    template_dir = BASE_DIR / "configs" / "ppt" / "custom_templates"

    if not template_dir.exists():
        return {"templates": []}

    templates = []
    for json_file in template_dir.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            template_id = json_file.stem
            # 只返回当前用户的模板
            if f"custom_{user_id}_" in template_id:
                templates.append({
                    "template_id": template_id,
                    "config": config,
                })
        except Exception:
            pass

    return {"templates": templates}


# =============================================================================
# PDF 导出
# =============================================================================

@router.get("/pptx/download/{ppt_id}/pdf")
async def download_ppt_as_pdf(
    ppt_id: str,
    token: dict = Depends(verify_token),
):
    """将 PPT 转换为 PDF 并下载"""
    _validate_ppt_id(ppt_id)
    _verify_ppt_owner(ppt_id, token.get("sub", "anonymous"))
    # 查找 PPTX 文件
    pptx_path = PPT_OUTPUT_DIR / f"{ppt_id}.pptx"
    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail="PPT 文件不存在")

    pdf_path = PPT_OUTPUT_DIR / f"{ppt_id}.pdf"

    try:
        await _convert_pptx_to_pdf(pptx_path, pdf_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=501,
            detail="PDF 导出需要安装 LibreOffice。请在服务器上安装: apt-get install libreoffice-impress"
        )
    except Exception:
        logger.error("PDF 转换失败", exc_info=True)
        raise HTTPException(status_code=500, detail="PDF 转换失败")

    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF 转换失败")

    return FileResponse(
        path=str(pdf_path),
        filename=f"{ppt_id}.pdf",
        media_type="application/pdf",
    )


async def _convert_pptx_to_pdf(pptx_path: Path, pdf_path: Path) -> None:
    """Convert a generated PPTX using the server's LibreOffice installation."""
    import asyncio
    import subprocess

    if pdf_path.is_file() and pdf_path.stat().st_mtime_ns >= pptx_path.stat().st_mtime_ns:
        return

    def convert() -> None:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(pptx_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice 转换失败: {result.stderr}")
        generated = pptx_path.with_suffix(".pdf")
        if generated != pdf_path and generated.exists():
            generated.replace(pdf_path)
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice 未生成 PDF 文件")

    await asyncio.to_thread(convert)


# =============================================================================
# WebSocket 进度推送
# =============================================================================

@router.websocket("/ws/ppt/{task_id}")
async def ppt_progress_websocket(websocket: WebSocket, task_id: str):
    """
    WebSocket 端点用于实时 PPT 生成进度推送

    客户端连接后会自动接收任务进度更新。
    消息格式:
    - {"type": "progress", "progress": 0.5, "step": "generating", "message": "正在生成第 5 页..."}
    - {"type": "completed", "progress": 1, "step": "completed", "message": "任务完成"}
    - {"type": "error", "error": "错误信息"}
    """
    access_token = websocket.query_params.get("token", "")
    valid, payload, close_code, reason = await verify_token_ws(access_token)
    if not valid or not payload:
        await websocket.close(code=close_code or 1008, reason=reason or "未授权")
        return
    try:
        _verify_ppt_owner(task_id, payload.get("sub", ""))
    except HTTPException as error:
        await websocket.close(code=1008, reason=str(error.detail))
        return

    await websocket.accept()
    logger.info(f"PPT WebSocket 连接已建立 | task_id={task_id}")

    try:
        # 获取任务管理器
        from app.utils.task_manager import task_manager

        last_progress = -1
        last_status = ""
        try:
            last_event_sequence = max(0, int(websocket.query_params.get("after_sequence", "0")))
        except ValueError:
            last_event_sequence = 0
        snapshot_sent = False

        while True:
            # SQL 事件日志提供断线后的可靠重放来源。
            try:
                from app.services.task_event_service import replay_task_events

                async with async_session() as event_db:
                    events = await replay_task_events(
                        event_db,
                        task_id,
                        int(payload.get("sub", 0)),
                        after_sequence=last_event_sequence,
                        limit=100,
                    )
                for event in events:
                    await websocket.send_json({
                        "type": event.event_type,
                        "sequence": event.sequence,
                        "status": event.status,
                        "progress": event.progress,
                        "payload": event.payload_json,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    })
                    last_event_sequence = event.sequence
                if last_event_sequence > 0 and not events and not snapshot_sent:
                    from app.services.task_checkpoint_service import get_latest_checkpoint

                    async with async_session() as checkpoint_db:
                        checkpoint = await get_latest_checkpoint(
                            checkpoint_db,
                            task_id,
                            int(payload.get("sub", 0)),
                        )
                    if checkpoint:
                        await websocket.send_json({
                            "type": "snapshot_recovery",
                            "sequence": last_event_sequence,
                            "revision": checkpoint.revision,
                            "step": checkpoint.step,
                            "state": checkpoint.state_json,
                        })
                    snapshot_sent = True
            except Exception as event_error:
                logger.debug(f"PPT SQL 事件重放暂不可用 | task_id={task_id} | error={event_error}")

            # 查询任务状态
            task_info = await task_manager.get_task_info_async(task_id)

            if not task_info:
                async with async_session() as task_db:
                    task_result = await task_db.execute(
                        select(Task).where(
                            Task.task_id == task_id,
                            Task.user_id == int(payload.get("sub", 0)),
                        )
                    )
                    task_record = task_result.scalar_one_or_none()
                if task_record:
                    task_info = {
                        "task_id": task_record.task_id,
                        "status": task_record.status,
                        "progress": task_record.progress or 0,
                        "progress_message": task_record.progress_message or "",
                        "result": task_record.result or task_record.result_json or {},
                        "error_message": task_record.error_message,
                    }

            if not task_info:
                await websocket.send_json({
                    "type": "error",
                    "error": "任务不存在"
                })
                break

            current_progress = task_info.get("progress", 0)
            current_status = task_info.get("status", "")
            current_message = task_info.get("progress_message", "")

            # 只在进度或状态变化时发送更新
            if current_progress != last_progress or current_status != last_status:
                if current_status == "success":
                    await websocket.send_json({
                        "type": "completed",
                        "progress": 1,
                        "step": "completed",
                        "message": "任务完成",
                        "result": task_info.get("result", {})
                    })
                    break
                elif current_status == "failed":
                    await websocket.send_json({
                        "type": "error",
                        "error": task_info.get("error_message", "任务失败"),
                        "progress": current_progress / 100,
                        "step": "error",
                        "message": current_message
                    })
                    break
                elif current_status == "cancelled":
                    await websocket.send_json({
                        "type": "error",
                        "error": "任务已取消",
                        "progress": current_progress / 100,
                        "step": "cancelled",
                        "message": "任务已取消"
                    })
                    break
                else:
                    await websocket.send_json({
                        "type": "progress",
                        "progress": current_progress / 100,
                        "step": current_status,
                        "message": current_message
                    })

                last_progress = current_progress
                last_status = current_status

            # 检查是否有客户端消息（如 ping）
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            # 等待一段时间再查询
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        logger.info(f"PPT WebSocket 连接断开 | task_id={task_id}")
    except Exception:
        logger.exception(f"PPT WebSocket 错误 | task_id={task_id}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": "服务器发生错误，请稍后重试"
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
