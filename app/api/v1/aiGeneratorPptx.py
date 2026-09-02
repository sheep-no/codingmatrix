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
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File as FastAPIFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.db.database import async_session
from app.utils.security import verify_token, verify_token_ws
from app.utils.task_manager import task_manager
from app.schema.task_schema import TaskResponse
from app.services.unified_state_service import get_owned_task, transition_task
from app.celery_app import celery_app

# 视觉决策模块
from app.utils.visual import (
    visual_analyzer,
    image_manager,
    layout_decider,
    ImageType,
)

from app.models.file import File
from app.models.task import Task
from sqlalchemy import select

# PPT 工具模块
from app.utils.pptx.text_processor import (
    prevent_text_overflow as prevent_text_overflow_v2,
)
from app.utils.pptx.image_search import ImageSearchManager
from app.utils.pptx.ppt_style import PPTStyle, PPT_TEMPLATES
from app.agent.models import DEFAULT_PPT_MODEL

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN

logger = logging.getLogger(__name__)
router = APIRouter(tags=["PPT 生成 (增强版)"])

# =============================================================================
# PPT 全局常量
# =============================================================================

PPT_DEFAULT_MODEL = DEFAULT_PPT_MODEL
PPT_MAX_SLIDES = 50
PPT_OUTPUT_DIR = Path("./pptx_output")
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


def _preview_url(ppt_id: str, output_format: "OutputFormat") -> str:
    """Return a preview URL that preserves the generated artifact format."""
    return f"/api/v1/pptx/preview/{ppt_id}?format={output_format.value}"

# 所有合法模板 ID（前端、后端、配置文件共用此列表）
VALID_TEMPLATE_IDS = [
    "modern", "business", "creative", "minimal",
    "academic", "tech", "education", "medical", "elegant",
]

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
    material_file_ids: Optional[List[int]] = Field(None, description="已上传素材的文件 ID 列表")
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token（用于从 Redis 获取用户自定义 Key）")
    
    # 增强选项
    template: str = Field(default="modern", description="模板风格")
    slide_count: int = Field(default=10, ge=5, le=PPT_MAX_SLIDES, description="页数")
    output_format: OutputFormat = Field(default=OutputFormat.PPTX, description="输出格式")
    language: str = Field(default="zh-CN", description="语言")
    quality: str = Field(default="high", description="内容质量")
    options: Dict[str, bool] = Field(default_factory=dict, description="高级选项")
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
    preview_url: str
    slides: Optional[List[Dict[str, Any]]] = None

# =============================================================================
# 模板与样式配置（已提取到 app/utils/pptx/ppt_style.py）
# =============================================================================

# PPT_TEMPLATES 和 PPTStyle 从 app.utils.pptx.ppt_style 导入（见文件顶部）


def add_decorative_header(slide, prs, title_text, style: PPTStyle):
    """添加装饰性页眉"""
    # 顶部装饰条
    header_height = Inches(0.15)
    header_shape = slide.shapes.add_shape(
        1,  # 矩形
        Inches(0), Inches(0),
        prs.slide_width, header_height
    )
    header_shape.fill.solid()
    header_shape.fill.fore_color.rgb = style.PRIMARY_COLOR
    header_shape.line.fill.background()

    # 标题区域背景
    title_bg = slide.shapes.add_shape(
        1,
        Inches(0), Inches(0.15),
        prs.slide_width, Inches(1.2)
    )
    title_bg.fill.solid()
    title_bg.fill.fore_color.rgb = style.PRIMARY_LIGHT
    title_bg.line.fill.background()


def add_page_number(slide, prs, page_num, total_pages, style: PPTStyle):
    """添加页码"""
    # 页脚装饰条
    footer_height = Inches(0.1)
    footer_shape = slide.shapes.add_shape(
        1,
        Inches(0), prs.slide_height - footer_height,
        prs.slide_width, footer_height
    )
    footer_shape.fill.solid()
    footer_shape.fill.fore_color.rgb = style.PRIMARY_DARK
    footer_shape.line.fill.background()

    # 页码文本
    page_text = slide.shapes.add_textbox(
        prs.slide_width - Inches(1),
        prs.slide_height - Inches(0.6),
        Inches(0.9), Inches(0.4)
    )
    tf = page_text.text_frame
    p = tf.paragraphs[0]
    p.text = f"{page_num} / {total_pages}"
    p.font.name = style.FONT_MAIN
    p.font.size = Pt(12)
    p.font.color.rgb = style.TEXT_WHITE
    p.alignment = PP_ALIGN.RIGHT


def add_bullet_with_icon(slide, left, top, width, text, level, style: PPTStyle, icon=None):
    """添加带图标的bullet"""
    # bullet 符号
    if level == 0:
        bullet_char = "●"
        bullet_color = style.PRIMARY_COLOR
        font_size = Pt(16)
    else:
        bullet_char = "○"
        bullet_color = style.PRIMARY_LIGHT
        font_size = Pt(14)

    txbox = slide.shapes.add_textbox(left, top, Inches(0.3), Inches(0.3))
    tf = txbox.text_frame
    p = tf.paragraphs[0]
    p.text = bullet_char
    p.font.name = style.FONT_MAIN
    p.font.size = font_size
    p.font.color.rgb = bullet_color

    # 文本内容
    textbox = slide.shapes.add_textbox(
        left + Inches(0.3), top,
        width - Inches(0.3), Inches(0.5)
    )
    tf = textbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = style.FONT_MAIN
    p.font.size = font_size
    p.font.color.rgb = style.TEXT_DARK
    p.space_after = Pt(6)


def style_title_shape(title_shape, text, style: PPTStyle, font_size=Pt(36)):
    """样式化标题形状"""
    title_shape.text = text
    for para in title_shape.text_frame.paragraphs:
        para.font.name = style.FONT_MAIN
        para.font.size = font_size
        para.font.bold = True
        para.font.color.rgb = style.TEXT_WHITE
        para.alignment = PP_ALIGN.LEFT


def add_slide_background(slide, prs, style: PPTStyle, light=True):
    """添加幻灯片背景"""
    bg_color = style.BG_WHITE if light else style.BG_LIGHT_BLUE
    background = slide.shapes.add_shape(
        1,
        Inches(0), Inches(0),
        prs.slide_width, prs.slide_height
    )
    background.fill.solid()
    background.fill.fore_color.rgb = bg_color
    background.line.fill.background()
    # 移到最底层
    spTree = slide.shapes._spTree
    sp = background._element
    spTree.remove(sp)
    spTree.insert(2, sp)


def add_decorative_corner(slide, prs, style: PPTStyle):
    """添加角落装饰"""
    # 右下角装饰圆
    corner = slide.shapes.add_shape(
        9,  # 椭圆
        prs.slide_width - Inches(2),
        prs.slide_height - Inches(1.5),
        Inches(2), Inches(1.5)
    )
    corner.fill.solid()
    corner.fill.fore_color.rgb = style.ACCENT_LIGHT
    corner.fill.fore_color.brightness = 0.3
    corner.line.fill.background()


def _render_slide_default(prs, blank_layout, style, slide_data, idx, total_slides):
    """默认幻灯片渲染（不使用视觉决策）"""
    content_slide = prs.slides.add_slide(blank_layout)

    # 浅蓝背景
    add_slide_background(content_slide, prs, style, light=True)

    # 顶部装饰
    add_decorative_header(content_slide, prs, slide_data.get('title', ''), style)

    # 左侧装饰
    left_dec = content_slide.shapes.add_shape(
        1, Inches(0), Inches(0),
        Inches(0.1), Inches(7.5)
    )
    left_dec.fill.solid()
    left_dec.fill.fore_color.rgb = style.PRIMARY_COLOR
    left_dec.line.fill.background()

    # 标题
    title_shape = content_slide.shapes.add_textbox(
        Inches(0.5), Inches(0.4),
        Inches(12), Inches(1)
    )
    tf = title_shape.text_frame
    p = tf.paragraphs[0]
    p.text = slide_data.get('title', f'第 {idx} 页')
    p.font.name = style.FONT_MAIN
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = style.PRIMARY_COLOR

    # 分隔线
    line = content_slide.shapes.add_shape(
        1,
        Inches(0.5), Inches(1.3),
        Inches(12.333), Inches(0.03)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = style.PRIMARY_LIGHT
    line.line.fill.background()

    # 内容区域 (使用防溢出处理)
    content_items = slide_data.get('content', [])
    if isinstance(content_items, str):
        content_items = [content_items]
    elif isinstance(content_items, dict):
        content_items = [str(content_items)]
    elif not content_items:
        content_items = ['暂无内容']
    
    # 防溢出处理
    processed_items = []
    for item in content_items:
        if isinstance(item, str):
            processed_items.extend(prevent_text_overflow(item, max_chars_per_line=70, max_lines=6))
        else:
            processed_items.append(str(item))
    content_items = processed_items

    # 自动配图 (如果有搜索到的图片)
    local_images = slide_data.get('local_images', [])
    if local_images:
        try:
            img_path = local_images[0]
            if Path(img_path).exists():
                content_slide.shapes.add_picture(
                    img_path, 
                    Inches(9), Inches(2), 
                    Inches(3.5), Inches(2.5)
                )
        except Exception as e:
            logger.warning(f"图片添加失败: {e}")

    # 逐行添加内容
    y_pos = 1.6
    for item in content_items:
        item_text = str(item).strip()
        if item_text:
            # 添加 bullet
            bullet = content_slide.shapes.add_shape(
                9,  # 椭圆
                Inches(0.5), Inches(y_pos + 0.1),
                Inches(0.15), Inches(0.15)
            )
            bullet.fill.solid()
            bullet.fill.fore_color.rgb = style.ACCENT_COLOR
            bullet.line.fill.background()

            # 文本
            text_box = content_slide.shapes.add_textbox(
                Inches(0.8), Inches(y_pos),
                Inches(11.5), Inches(0.8)
            )
            tf = text_box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = item_text
            p.font.name = style.FONT_MAIN
            p.font.size = Pt(20)
            p.font.color.rgb = style.TEXT_DARK
            p.space_after = Pt(12)
            y_pos += 0.7

    # 右下角装饰
    add_decorative_corner(content_slide, prs, style)

    # 页码
    add_page_number(content_slide, prs, idx + 1, total_slides, style)

    # 底部装饰条
    bottom_bar = content_slide.shapes.add_shape(
        1, Inches(0), Inches(7.35),
        prs.slide_width, Inches(0.15)
    )
    bottom_bar.fill.solid()
    bottom_bar.fill.fore_color.rgb = style.PRIMARY_DARK
    bottom_bar.line.fill.background()


# 导入 Aicode 的会话压缩函数
from app.api.v1.Aicode import compress_conversation_history
from app.utils import call_llm

# =============================================================================
# 辅助函数：大纲生成、多格式导出、预览
# =============================================================================

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
    
    prompt = f"""
请根据以下要求生成一个专业的 PPT 大纲，返回 JSON 格式：

{{
    "title": "PPT 标题",
    "slides": [
        {{
            "slide_number": 1,
            "title": "幻灯片标题",
            "content": "详细内容（支持 Markdown 格式）",
            "slide_type": "cover|content|summary|toc",
            "notes": "演讲者备注（可选）"
        }}
    ]
}}

要求：
- 主题：{content_context}
- 页数：{req.slide_count}页
- 语言：{req.language}
- 质量：{req.quality}
- 模板风格：{req.template}
{skill_context if skill_context else ""}

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

        # 提取 JSON（可能用 markdown 代码块包裹）
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```|(\{[\s\S]*\}|\[[\s\S]*\])', content)
        if json_match:
            json_str = json_match.group(1) or json_match.group(2)
        else:
            json_str = content

        outline = json.loads(json_str)
        return outline
        
    except Exception as e:
        logger.warning(f"AI 大纲生成失败，使用默认大纲：{e}")
        # 返回默认大纲
        return {
            "title": req.topic[:50],
            "slides": [
                {
                    "slide_number": 1,
                    "title": req.topic[:50],
                    "content": req.topic,
                    "slide_type": "cover",
                    "notes": ""
                },
                {
                    "slide_number": 2,
                    "title": "目录",
                    "content": "1. 引言\n2. 主体内容\n3. 总结",
                    "slide_type": "toc",
                    "notes": ""
                },
                {
                    "slide_number": 3,
                    "title": "引言",
                    "content": req.topic[:200],
                    "slide_type": "content",
                    "notes": ""
                },
                {
                    "slide_number": 4,
                    "title": "总结",
                    "content": "核心要点总结",
                    "slide_type": "summary",
                    "notes": ""
                }
            ]
        }

async def generate_pptx_file_enhanced(filepath: Path, outline: Dict[str, Any], req: PPTGenerationRequest, update_progress=None):
    """生成 PPTX 文件 (增强版：包含视觉决策和模板支持)"""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    style = PPTStyle(template_name=req.template)
    total_slides = 1 + len(outline.get('slides', []))
    blank_layout = prs.slide_layouts[6]

    if update_progress: await update_progress(message="正在创建封面...")

    # === 1. 标题页（封面）===
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    
    # 顶部装饰条
    top_bar = slide.shapes.add_shape(
        1, Inches(0), Inches(0),
        prs.slide_width, Inches(0.3)
    )
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = style.PRIMARY_COLOR
    top_bar.line.fill.background()

    # 左侧装饰条
    left_bar = slide.shapes.add_shape(
        1, Inches(0), Inches(0),
        Inches(0.15), prs.slide_height
    )
    left_bar.fill.solid()
    left_bar.fill.fore_color.rgb = style.PRIMARY_LIGHT
    left_bar.line.fill.background()

    # 中央装饰框
    center_box = slide.shapes.add_shape(
        1, Inches(1.5), Inches(2),
        Inches(10.333), Inches(3)
    )
    center_box.fill.solid()
    center_box.fill.fore_color.rgb = style.PRIMARY_COLOR
    center_box.line.fill.background()

    # 主标题
    title_box = slide.shapes.add_textbox(
        Inches(1.5), Inches(2.3),
        Inches(10.333), Inches(1.5)
    )
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = outline.get('title', 'PPT 标题')
    p.font.name = style.FONT_MAIN
    p.font.size = Pt(48)
    p.font.bold = True
    p.font.color.rgb = style.TEXT_WHITE
    p.alignment = PP_ALIGN.CENTER

    # 副标题
    subtitle_box = slide.shapes.add_textbox(
        Inches(1.5), Inches(4),
        Inches(10.333), Inches(0.8)
    )
    tf = subtitle_box.text_frame
    p = tf.paragraphs[0]
    p.text = f"生成时间：{datetime.now().strftime('%Y-%m-%d')}"
    p.font.name = style.FONT_MAIN
    p.font.size = Pt(18)
    p.font.color.rgb = style.TEXT_WHITE
    p.alignment = PP_ALIGN.CENTER

    add_decorative_corner(slide, prs, style)
    
    # === 2. 视觉决策阶段 ===
    visual_plan = None
    if update_progress: await update_progress(message="正在分析视觉需求...")
    try:
        visual_plan = await visual_analyzer.analyze_ppt_content(
            title=outline.get("title", "PPT"),
            slides_content=outline.get("slides", []),
            theme=req.template
        )
    except Exception as e:
        logger.warning(f"视觉分析失败，使用默认布局: {e}")

    # === 3. 内容幻灯片 ===
    for idx, slide_data in enumerate(outline.get('slides', []), 1):
        if update_progress: 
            await update_progress(progress=int(50 + 50 * idx / total_slides), message=f"正在生成第 {idx} 页...")
        
        # 如果视觉决策启用，尝试使用
        slide_decision = None
        image_asset = None
        used_visual = False

        if visual_plan and idx <= len(visual_plan.slides):
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
                except Exception: pass

            try:
                layout_plan = layout_decider.plan_slide_layout(
                    slide_decision=slide_decision,
                    page_number=idx + 1,
                    total_pages=total_slides
                )
                layout_decider.render_slide(
                    prs=prs, layout_plan=layout_plan, image_asset=image_asset, style=style
                )
                used_visual = True
            except Exception: pass

        if not used_visual:
            _render_slide_default(prs, blank_layout, style, slide_data, idx, total_slides)
    
    prs.save(str(filepath))
    logger.info(f"PPTX 文件保存成功 | file: {filepath}")
    
    # 保存 JSON 数据（用于预览）
    json_path = filepath.parent / f"{filepath.stem}_slides.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(outline.get('slides', []), f, ensure_ascii=False, indent=2)

async def generate_html_ppt(filepath: Path, outline: Dict[str, Any], req: PPTGenerationRequest):
    """生成 HTML 格式 PPT"""
    template = PPT_TEMPLATES.get(req.template, PPT_TEMPLATES["modern"])
    
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
    
    for slide_data in outline.get('slides', []):
        if slide_data.get('slide_type') == 'cover':
            continue
            
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
    
    for slide_data in outline.get('slides', []):
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
            <a href="/api/v1/pptx/download/{ppt_id}?format=pptx" class="download-btn">下载 PowerPoint</a>
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
            .catch(err => console.error('加载幻灯片失败:', err));
    </script>
</body>
</html>"""

# =============================================================================
# API 路由
# =============================================================================


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

    ppt_id = str(uuid.uuid4())
    
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
            context_parts = []
            
            # 会话历史
            if conversation_id:
                try:
                    history_context = await compress_conversation_history(
                        db, int(user_id), int(conversation_id), max_messages=5
                    )
                    if history_context:
                        context_parts.append(f"\n[对话历史]\n{history_context}")
                except Exception as e:
                    logger.warning(f"获取会话历史失败: {e}")

            # 素材文件
            if material_file_ids:
                material_info = []
                for file_id in material_file_ids:
                    try:
                        result = await db.execute(select(File).where(File.id == file_id, File.user_id == int(user_id)))
                        file_record = result.scalar_one_or_none()
                        if file_record:
                            if not req.session_id or file_record.conversation_id == req.session_id:
                                material_info.append(f"- {file_record.filename}")
                    except Exception: pass
                if material_info:
                    context_parts.append(f"\n[参考素材]\n" + "\n".join(material_info))
            
            if context_parts:
                req.topic = f"{full_prompt}\n\n{''.join(context_parts)}"

            # 2. 生成大纲
            await update_progress(progress=20, message="正在生成 PPT 大纲...")
            outline = await generate_ppt_outline(req, user_id=user_id)

            # 立即保存大纲快照（用于恢复/增量生成）
            output_dir = PPT_OUTPUT_DIR
            output_dir.mkdir(exist_ok=True)
            snapshot_path = output_dir / f"{task_id}_slides.json"
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(outline.get('slides', []), f, ensure_ascii=False, indent=2)
            logger.info(f"保存大纲快照 | task_id={task_id} | slides={len(outline.get('slides', []))}")
            
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

            if req.output_format == OutputFormat.PDF:
                logger.warning("PDF 输出格式尚未实现 pptx-to-pdf 转换，将回退到 PPTX 格式")
                ext = "pptx"
            
            filepath = output_dir / f"{task_id}.{ext}"
            slides_data = outline.get('slides', [])

            if req.output_format == OutputFormat.PPTX:
                # 使用高级视觉决策逻辑生成 PPTX
                await generate_pptx_file_enhanced(filepath, outline, req, update_progress=update_progress)
            elif req.output_format == OutputFormat.HTML:
                await update_progress(progress=60, message="正在生成 HTML 格式...")
                await generate_html_ppt(filepath, outline, req)
            elif req.output_format == OutputFormat.MARKDOWN:
                await update_progress(progress=60, message="正在生成 Markdown 格式...")
                await generate_markdown_ppt(filepath, outline, req)
            else:
                # 默认回退到 PPTX
                await generate_pptx_file_enhanced(filepath, outline, req, update_progress=update_progress)

            result = {
                "filename": filepath.name,
                "ppt_id": task_id,
                "download_url": f"/api/v1/pptx/download/{task_id}?format={ext}",
                "preview_url": _preview_url(task_id, req.output_format) if req.output_format in {OutputFormat.PPTX, OutputFormat.HTML, OutputFormat.MARKDOWN} else None
            }
            await update_progress(
                progress=100,
                message="PPT 生成完成",
                status="completed",
                result_data=json.dumps(result)
            )
            return result
            
        except asyncio.CancelledError:
            # 取消时保存已有的中间状态
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
                message=f"PPT 生成失败：{str(e)}",
                error_message=str(e)
            )
            logger.error(f"PPT 生成任务失败 | task_id: {task_id} | error: {str(e)}")
    
    task_response = await task_manager.create_task(
        task_type="ppt_generation",
        user_id=user_id,
        func=run_ppt_generation,
        params={}
    )

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
            await generate_pptx_file_enhanced(filepath, outline, req)
        elif req.output_format == OutputFormat.HTML:
            await generate_html_ppt(filepath, outline, req)
        elif req.output_format == OutputFormat.MARKDOWN:
            await generate_markdown_ppt(filepath, outline, req)
        else:
            await generate_pptx_file_enhanced(filepath, outline, req)

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
    except Exception as e:
        logger.error(f"PPT 同步生成失败 | error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pptx/download/{ppt_id}")
async def download_ppt(
    ppt_id: str,
    format: str = Query(default="pptx", description="下载格式"),
    token: dict = Depends(verify_token)
):
    """下载 PPT 文件"""
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
    
    return StreamingResponse(
        file_stream(),
        media_type=mime_types.get(actual_format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{filepath.name}"'
        }
    )


@router.get("/pptx/preview/{ppt_id}", response_class=HTMLResponse)
async def preview_ppt(
    ppt_id: str,
    format: str = Query(default="pptx", description="预览格式"),
    token: dict = Depends(verify_token)
):
    """在线预览 PPT"""
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
    _verify_ppt_owner(ppt_id, token.get("sub", "anonymous"))
    output_dir = PPT_OUTPUT_DIR
    json_path = output_dir / f"{ppt_id}_slides.json"
    
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            slides_data = json.load(f)
        return {"slides": slides_data}
    
    raise HTTPException(status_code=404, detail="幻灯片数据不存在")


@router.delete("/pptx/{task_id}/cancel")
async def cancel_ppt_task(
    task_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """取消正在进行的 PPT 生成任务，并保存中间状态"""
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
    user_id = token.get("sub")
    _verify_ppt_owner(task_id, user_id)
    output_dir = PPT_OUTPUT_DIR

    # 查找之前的幻灯片数据
    json_path = output_dir / f"{task_id}_slides.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="找不到中间状态数据，无法增量生成")

    with open(json_path, 'r', encoding='utf-8') as f:
        existing_slides = json.load(f)

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
            original_prompt = new_req.topic
            new_req.topic = incremental_prompt

            await update_progress(progress=20, message="正在生成增量内容...")
            new_outline = await generate_ppt_outline(new_req, user_id=user_id)

            new_slides = new_outline.get('slides', existing_slides)
            new_title = new_outline.get('title', existing_slides[0].get('title', 'PPT') if existing_slides else 'PPT')

            output_id = task_id
            filepath = output_dir / f"{output_id}.{new_req.output_format.value}"
            slides_data = new_slides

            if new_req.output_format == OutputFormat.PPTX:
                await update_progress(progress=50, message="正在渲染 PPTX...")
                merged_outline = {"title": new_title, "slides": new_slides}
                await generate_pptx_file_enhanced(filepath, merged_outline, new_req, update_progress=update_progress)
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
                await generate_pptx_file_enhanced(filepath, merged_outline, new_req, update_progress=update_progress)

            # 只有新文件生成成功后才更新快照，保留上一版可恢复内容。
            new_json_path = output_dir / f"{output_id}_slides.json"
            with open(new_json_path, 'w', encoding='utf-8') as f:
                json.dump(new_slides, f, ensure_ascii=False, indent=2)
            _register_ppt_owner(output_id, user_id)
            logger.info(f"更新大纲快照 | task_id={output_id} | slides={len(new_slides)}")

            ext_map = {OutputFormat.PPTX: "pptx", OutputFormat.HTML: "html", OutputFormat.MARKDOWN: "md"}
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
                message=f"PPT 更新失败：{str(e)}",
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
        raise HTTPException(status_code=500, detail=f"修改失败: {exc}")


@router.get("/pptx/{task_id}/analyze")
async def analyze_ppt_endpoint(
    task_id: str,
    slide_number: Optional[int] = Query(None, description="指定幻灯片编号"),
    token: dict = Depends(verify_token),
):
    """
    分析 PPT 视觉状态（不执行修改）

    返回 PPT 的布局、字体、颜色等信息，用于了解当前状态。
    """
    _verify_ppt_owner(task_id, token.get("sub", "anonymous"))
    output_dir = PPT_OUTPUT_DIR
    pptx_path = output_dir / f"{task_id}.pptx"

    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail=f"找不到 PPT 文件：{task_id}")

    try:
        from app.utils.pptx.visual_modifier import analyze_ppt_for_modification

        result = await analyze_ppt_for_modification(
            pptx_path=str(pptx_path),
            slide_number=slide_number
        )

        return result

    except Exception as exc:
        logger.error("PPT 分析失败 | task_id: %s | error: %s", task_id, exc)
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}")


# =============================================================================
# 模板与历史管理
# =============================================================================


@router.get("/pptx/templates")
async def list_ppt_templates(
    category: Optional[str] = Query(None, description="按分类筛选"),
    token: dict = Depends(verify_token)
):
    """获取可用 PPT 模板列表"""
    templates = []
    for tpl_id, tpl_config in PPT_TEMPLATES.items():
        if category and not tpl_id.startswith(category):
            continue
        templates.append({
            "id": tpl_id,
            "name": tpl_config["name"],
            "primary_color": tpl_config["primary_color"],
            "background": tpl_config["background"],
        })
    return {"templates": templates}


@router.get("/pptx/history")
async def list_ppt_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    token: dict = Depends(verify_token)
):
    """获取用户的 PPT 生成历史"""
    user_id = token.get("sub", "anonymous")
    output_dir = PPT_OUTPUT_DIR

    if not output_dir.exists():
        return {"records": [], "total": 0}

    records = []
    for json_path in sorted(output_dir.glob("*_slides.json"), reverse=True):
        ppt_id = json_path.name.replace("_slides.json", "")
        try:
            owner_path = PPT_OWNER_DIR / f"{ppt_id}.json"
            if not owner_path.exists():
                continue
            with open(owner_path, "r", encoding="utf-8") as owner_file:
                if str(json.load(owner_file).get("user_id")) != str(user_id):
                    continue
            with open(json_path, "r", encoding="utf-8") as f:
                slides_data = json.load(f)
            pptx_path = output_dir / f"{ppt_id}.pptx"
            records.append({
                "task_id": ppt_id,
                "title": slides_data[0].get("title", "未命名") if slides_data else "未命名",
                "slide_count": len(slides_data),
                "has_file": pptx_path.exists(),
                "created_at": datetime.fromtimestamp(json_path.stat().st_mtime).isoformat(),
            })
        except Exception:
            continue

    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size
    return {"records": records[start:end], "total": total}


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

    json_path.unlink(missing_ok=True)
    for ext in ["pptx", "html", "md"]:
        (output_dir / f"{task_id}.{ext}").unlink(missing_ok=True)

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
# 自动搜图
# =============================================================================

# 图片搜索管理器 (延迟初始化)
_image_search_manager: Optional[ImageSearchManager] = None


def get_image_search_manager() -> ImageSearchManager:
    """获取图片搜索管理器单例"""
    global _image_search_manager
    if _image_search_manager is None:
        _image_search_manager = ImageSearchManager(
            bing_key=os.environ.get("BING_IMAGE_SEARCH_KEY"),
            unsplash_key=os.environ.get("UNSPLASH_ACCESS_KEY"),
            pexels_key=os.environ.get("PEXELS_API_KEY"),
        )
    return _image_search_manager


async def search_image_url(keyword: str) -> Optional[str]:
    """
    搜索图片 URL
    
    使用多源聚合搜索:
    1. Bing Image Search (需要 API Key)
    2. Unsplash (需要 API Key)
    3. Pexels (需要 API Key)
    4. 占位图降级
    """
    manager = get_image_search_manager()
    return await manager.search_image(keyword)


async def download_image(url: str, save_path: Path) -> bool:
    """下载图片到本地"""
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    save_path.write_bytes(data)
                    return True
    except Exception as e:
        logger.warning(f"图片下载失败 {url}: {e}")
    
    return False


IMAGE_CACHE_DIR = Path("./static/images/cache")


async def get_image_for_slide(keywords: List[str], slide_index: int) -> Optional[str]:
    """获取幻灯片配图 (缓存优先)"""
    manager = get_image_search_manager()
    
    for kw in keywords[:2]:
        # 检查缓存
        cached = await manager.get_cached_image(kw)
        if cached:
            return str(cached)
        
        # 搜索并下载
        url = await manager.search_image(kw)
        if url:
            path = await manager.download_and_cache(kw, url)
            if path:
                return str(path)
    
    return None


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


@router.post("/generate-text", response_model=OutlineGenerationResponse)
async def generate_ppt_from_text(
    req: OutlineGenerationRequest,
    token: dict = Depends(verify_token),
):
    """
    自然语言生成 PPT 大纲 (仅返回结构化数据，不生成文件)
    """
    user_id = token.get("sub", "anonymous")
    logger.info("PPT Agent 请求 | user: %s | topic: %s", user_id, req.topic[:50])

    try:
        from app.agent.ppt_agent import PPTAgent

        agent = PPTAgent(model=req.model)
        outline = await agent.generate_outline(
            topic=req.topic,
            description=req.description,
            num_slides=req.num_slides,
            api_key_token=req.api_key_token,
        )

        return OutlineGenerationResponse(
            title=outline.title,
            slides=[
                OutlineSlide(
                    type=s.type,
                    title=s.title,
                    bullets=s.bullets,
                    image_keywords=s.image_keywords,
                    notes=s.notes,
                )
                for s in outline.slides
            ],
            total_slides=len(outline.slides),
        )

    except Exception as exc:
        logger.error("PPT Agent 大纲生成失败 | error: %s", exc)
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {exc}")


@router.post("/generate-from-text", response_model=TaskResponse)
async def generate_ppt_from_text_task(
    req: OutlineGenerationRequest,
    token: dict = Depends(verify_token),
):
    """
    端到端: 自然语言 -> 大纲 -> PPTX 文件 (任务队列)
    """
    user_id = token.get("sub", "anonymous")
    logger.info("PPT Agent 端到端请求 | user: %s | topic: %s", user_id, req.topic[:50])

    try:
        from app.agent.ppt_agent import PPTAgent
        import uuid
        from app.schema.task_schema import TaskResponse as SchemaTaskResponse

        agent = PPTAgent(model=req.model)
        outline = await agent.generate_outline(
            topic=req.topic,
            description=req.description,
            num_slides=req.num_slides,
            api_key_token=req.api_key_token,
        )

        ppt_id = str(uuid.uuid4())
        outline_dict = PPTAgent.adapt_for_pptx_engine(outline)

        async def run_ppt_gen(task_id: str, **kwargs):
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

                # 搜图
                await update_progress(progress=15, message="正在搜索配图...")
                for i, slide in enumerate(outline_dict['slides']):
                    if slide.get('image_keywords'):
                        try:
                            img_path = await get_image_for_slide(slide['image_keywords'], i)
                            if img_path:
                                outline_dict['slides'][i]['local_images'] = [img_path]
                        except Exception as e:
                            logger.warning(f"幻灯片 {i+1} 配图失败: {e}")

                # 构建兼容请求
                compat_req = PPTGenerationRequest(
                    topic=outline.title,
                    model=req.model,
                    template=req.template if hasattr(req, 'template') else "modern",
                    slide_count=len(outline.slides),
                )

                output_dir = PPT_OUTPUT_DIR
                output_dir.mkdir(exist_ok=True)
                filepath = output_dir / f"{task_id}.pptx"

                await update_progress(progress=20, message="正在生成 PPTX 文件...")
                await generate_pptx_file_enhanced(filepath, outline_dict, compat_req, update_progress=update_progress)

                result = {
                    "filename": filepath.name,
                    "ppt_id": task_id,
                    "download_url": f"/api/v1/pptx/download/{task_id}?format=pptx",
                    "preview_url": f"/api/v1/pptx/preview/{task_id}",
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
            except Exception as exc:
                await update_progress(status="failed", message=f"生成失败: {exc}", error_message=str(exc))
                logger.error("PPT 生成任务失败 | task_id: %s | error: %s", task_id, exc)

        task_response = await task_manager.create_task(
            task_type="ppt_generation",
            user_id=user_id,
            func=run_ppt_gen,
            params={},
        )

        return SchemaTaskResponse(
            task_id=task_response,
            task_type="ppt_generation",
            status="pending",
            progress=0,
            progress_message="等待中...",
            created_at=datetime.now().isoformat()
        )

    except Exception as exc:
        logger.error("PPT Agent 端到端失败 | error: %s", exc)
        raise HTTPException(status_code=500, detail=f"生成失败: {exc}")


# =============================================================================
# 文件上传生成 PPT
# =============================================================================

# 支持的文件扩展名
_PPT_FILE_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".docx", ".doc",
    ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".csv", ".log", ".rst", ".html", ".css",
}


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

@router.post("/pptx/generate_from_file", response_model=TaskResponse)
async def generate_ppt_from_file(
    file: UploadFile = FastAPIFile(..., description="上传文件 (PDF/Word/TXT/MD 等)"),
    template: str = Form(default="modern", description="模板风格"),
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

    # 验证文件扩展名
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in _PPT_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}。支持: {', '.join(sorted(_PPT_FILE_EXTENSIONS))}"
        )

    # 保存上传文件到临时目录
    upload_dir = Path("./uploads/ppt_uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    temp_path = upload_dir / f"{file_id}{suffix}"

    try:
        await _stream_upload_to_path(file, temp_path, 50 * 1024 * 1024)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    # 解析文件内容
    try:
        from app.utils.aicloud.knowledge_processor import parse_document
        parsed_text = parse_document(str(temp_path))
        if not parsed_text or not parsed_text.strip():
            raise HTTPException(status_code=400, detail="文件内容为空或无法解析")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件解析失败: {e}")

    # 截断过长内容（避免 token 超限）
    max_chars = 30000
    if len(parsed_text) > max_chars:
        parsed_text = parsed_text[:max_chars] + f"\n\n[内容过长，已截断至 {max_chars} 字符]"

    # 构建 PPT 请求
    topic = f"根据以下文件内容生成 PPT：\n\n文件名: {filename}\n\n文件内容:\n{parsed_text}"
    if extra_prompt:
        topic += f"\n\n用户要求: {extra_prompt}"

    req = PPTGenerationRequest(
        topic=topic,
        template=template,
        slide_count=slide_count,
        output_format=output_format,
        api_key_token=api_key_token,
    )

    ppt_id = str(uuid.uuid4())

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

            if output_format == "pptx":
                await generate_pptx_file_enhanced(filepath, outline, req, update_progress=update_progress)
            elif output_format == "html":
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
    template_dir = Path("./configs/ppt/custom_templates")
    template_dir.mkdir(parents=True, exist_ok=True)

    template_id = f"custom_{user_id}_{uuid.uuid4().hex[:8]}"
    template_path = template_dir / f"{template_id}.pptx"

    try:
        await _stream_upload_to_path(file, template_path, 20 * 1024 * 1024)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板保存失败: {e}")

    # 解析模板配置
    try:
        from app.utils.pptx.custom_template import CustomTemplateParser
        parser = CustomTemplateParser()
        config = parser.parse(str(template_path))

        # 保存配置
        config_path = template_dir / f"{template_id}.json"
        import json as _json
        with open(config_path, 'w', encoding='utf-8') as f:
            _json.dump(config, f, ensure_ascii=False, indent=2)

        return {
            "template_id": template_id,
            "name": name,
            "description": description,
            "config": config,
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
    template_dir = Path("./configs/ppt/custom_templates")

    if not template_dir.exists():
        return {"templates": []}

    templates = []
    for json_file in template_dir.glob("*.json"):
        try:
            import json as _json
            with open(json_file, 'r', encoding='utf-8') as f:
                config = _json.load(f)
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
    _verify_ppt_owner(ppt_id, token.get("sub", "anonymous"))
    # 查找 PPTX 文件
    pptx_path = PPT_OUTPUT_DIR / f"{ppt_id}.pptx"
    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail="PPT 文件不存在")

    pdf_path = PPT_OUTPUT_DIR / f"{ppt_id}.pdf"

    # 使用 LibreOffice 转换
    try:
        import subprocess
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(PPT_OUTPUT_DIR), str(pptx_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice 转换失败: {result.stderr}")
    except FileNotFoundError:
        # LibreOffice 未安装，尝试使用 python-pptx 的替代方案
        raise HTTPException(
            status_code=501,
            detail="PDF 导出需要安装 LibreOffice。请在服务器上安装: apt-get install libreoffice-impress"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 转换失败: {e}")

    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF 转换失败")

    return FileResponse(
        path=str(pdf_path),
        filename=f"{ppt_id}.pdf",
        media_type="application/pdf",
    )


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
    valid, payload, close_code, reason = verify_token_ws(access_token)
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
    except Exception as e:
        logger.error(f"PPT WebSocket 错误 | task_id={task_id} | error={e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": f"服务器错误: {str(e)}"
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
