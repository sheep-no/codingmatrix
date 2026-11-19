"""PPT 幻灯片渲染辅助函数。

从 ``app.api.v1.aiGeneratorPptx`` 拆分而来，保持渲染行为不变。
"""

import re
from pathlib import Path
from typing import Any, Dict, List

from lxml import etree
from PIL import Image
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from app.utils.pptx.commercial_content import format_commercial_metadata
from app.utils.pptx.ppt_style import PPTStyle
from app.utils.pptx.semantic_renderer import normalize_slide_type


def add_page_number(slide, prs, page_num, total_pages, style: PPTStyle):
    """添加页码"""
    # 页脚装饰条
    footer_height = Inches(0.04)
    footer_shape = slide.shapes.add_shape(
        1,
        Inches(0), prs.slide_height - footer_height,
        prs.slide_width, footer_height
    )
    footer_shape.fill.solid()
    footer_shape.fill.fore_color.rgb = style.PRIMARY_COLOR
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
    p.font.size = Pt(10)
    p.font.color.rgb = style.PRIMARY_COLOR
    p.alignment = PP_ALIGN.RIGHT
    _apply_paragraph_font(p, style.FONT_MAIN)




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



def _fit_editorial_text(text, width, height, size):
    """Fit text to a fixed box with a conservative estimate for CJK wrapping."""
    value = str(text or "")
    min_size = 8
    for candidate in range(int(size), min_size - 1, -1):
        chars_per_line = max(1, int(width * 72 / (candidate * 0.95)))
        line_units = 0
        lines = 1
        for char in value:
            if char == "\n":
                lines += 1
                line_units = 0
                continue
            line_units += 1 if ord(char) > 255 else 0.58
            if line_units > chars_per_line:
                lines += 1
                line_units = 1 if ord(char) > 255 else 0.58
        required_height = lines * candidate * 1.25
        if required_height <= height * 72 * 0.95:
            return value, candidate

    chars_per_line = max(1, int(width * 72 / (min_size * 0.95)))
    max_lines = max(1, int(height * 72 / (min_size * 1.25) * 0.95))
    capacity = chars_per_line * max_lines
    if len(value) > capacity:
        value = value[:max(1, capacity - 1)].rstrip() + "…"
    return value, min_size


def _add_editorial_text(slide, text, left, top, width, height, style, size=18, color=None, bold=False, align=None, anchor=None):
    if not str(text or "").strip():
        return None
    fitted_text, fitted_size = _fit_editorial_text(text, width, height, size)
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    box.text_frame.word_wrap = True
    box.text_frame.margin_left = 0
    box.text_frame.margin_right = 0
    box.text_frame.margin_top = 0
    box.text_frame.margin_bottom = 0
    if anchor is None:
        anchor = MSO_ANCHOR.MIDDLE if height <= 0.45 else MSO_ANCHOR.TOP
    box.text_frame.vertical_anchor = anchor
    paragraph = box.text_frame.paragraphs[0]
    paragraph.text = fitted_text
    paragraph.font.size = Pt(fitted_size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = color or style.TEXT_DARK
    if align:
        paragraph.alignment = align
    _apply_paragraph_font(paragraph, style.FONT_TITLE if bold else style.FONT_MAIN)
    return box


def _add_editorial_card(slide, title, body, left, top, width, height, style, accent=None, filled=False):
    card = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    card.fill.solid()
    card.fill.fore_color.rgb = style.PRIMARY_COLOR if filled else style.BG_WHITE
    card.line.color.rgb = style.PRIMARY_COLOR if filled else style.PRIMARY_LIGHT
    card.line.width = Pt(1)
    _soften_rounded_rect(card)
    marker = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(0.08), Inches(height))
    marker.fill.solid()
    marker.fill.fore_color.rgb = accent or style.ACCENT_COLOR
    marker.line.fill.background()
    title_color = style.TEXT_WHITE if filled else style.PRIMARY_COLOR
    body_color = style.TEXT_WHITE if filled else style.TEXT_DARK
    if height <= 1.1:
        _add_editorial_text(slide, title, left + 0.28, top + 0.18, 1.75, height - 0.36, style, 12, title_color, True)
        _add_editorial_text(slide, body, left + 2.05, top + 0.14, width - 2.25, height - 0.28, style, 14, body_color)
    else:
        _add_editorial_text(slide, title, left + 0.28, top + 0.2, width - 0.45, 0.35, style, 14, title_color, True)
        _add_editorial_text(slide, body, left + 0.28, top + 0.65, width - 0.45, height - 0.8, style, 16, body_color)


def _add_cropped_picture(slide, image_path, left, top, width, height):
    """Fill a visual box while preserving the source image aspect ratio."""
    with Image.open(image_path) as image:
        source_ratio = image.width / image.height
    box_ratio = width / height
    picture = slide.shapes.add_picture(
        image_path, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    if source_ratio > box_ratio:
        picture.crop_left = picture.crop_right = (1 - box_ratio / source_ratio) / 2
    elif source_ratio < box_ratio:
        picture.crop_top = picture.crop_bottom = (1 - source_ratio / box_ratio) / 2
    return picture


def _normalize_slide_items(content):
    """Turn model prose into short presentation-ready statements."""
    if isinstance(content, list):
        raw_items = content
    else:
        raw_items = re.split(r"[\n；;]+", str(content or ""))
    items = []
    for item in raw_items:
        text = re.sub(r"^\s*[-•●\d]+[.、)]?\s*", "", str(item)).strip()
        if text:
            items.append(text)
    return items or ["待补充内容"]


def _commercial_slide_items(slide_data: Dict[str, Any]) -> List[str]:
    """Prefer semantic content blocks and expose their commercial metadata."""
    role = slide_data.get("narrative_role") or "opportunity_map"
    blocks = slide_data.get("content_blocks") or []
    if not isinstance(blocks, list) or not blocks:
        return _normalize_slide_items(slide_data.get("content", []))

    items = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        content = str(block.get("content", "")).strip()
        if not content:
            continue
        detail = format_commercial_metadata(role, block.get("metadata") or {})
        items.append(f"{content}\n{detail}" if detail else content)
    return items or _normalize_slide_items(slide_data.get("content", []))


def _slide_role(slide_data: Dict[str, Any]) -> str:
    return slide_data.get("narrative_role") or {
        "data": "evidence_story",
        "comparison": "strategic_choice",
        "timeline": "execution_roadmap",
        "process": "execution_roadmap",
        "summary": "decision_close",
        "closing": "decision_close",
    }.get(normalize_slide_type(slide_data.get("slide_type")), "opportunity_map")


def _is_zh_style(style) -> bool:
    language = getattr(style, "language", "zh-CN")
    return isinstance(language, str) and language.lower().startswith("zh")


def _chrome(style, zh: str, en: str) -> str:
    return zh if _is_zh_style(style) else en


_ROLE_LABELS = {
    "opportunity_map": ("机会判断", "OPPORTUNITY MAP"),
    "evidence_story": ("证据叙事", "EVIDENCE STORY"),
    "strategic_choice": ("战略选择", "STRATEGIC CHOICE"),
    "execution_roadmap": ("执行路径", "EXECUTION ROADMAP"),
    "decision_close": ("决策收口", "DECISION CLOSE"),
}


def _role_kicker(style, role: str, idx: int | None = None) -> str:
    zh, en = _ROLE_LABELS.get(role, ("内容", "CONTENT"))
    label = _chrome(style, zh, en)
    if idx is None:
        return label
    return f"{idx:02d} / {label}"


def _cover_kicker(style) -> str:
    mapping = {
        "education": ("学习讲义", "LEARNING LAB"),
        "elegant": ("决策备忘", "PRIVATE EDITION"),
        "medical": ("临床简报", "CLINICAL BRIEF"),
        "academic": ("研究简报", "RESEARCH BRIEF"),
        "creative": ("策略提案", "STRATEGY"),
        "tech": ("技术方案", "SYSTEM DECK"),
        "minimal": ("演示文稿", "PRESENTATION"),
        "modern": ("策略简报", "STRATEGY BRIEF"),
        "business": ("策略简报", "STRATEGY BRIEF"),
    }
    zh, en = mapping.get(getattr(style, "template_name", "modern"), ("策略简报", "STRATEGY BRIEF"))
    return _chrome(style, zh, en)


def _cover_tagline(outline: Dict[str, Any]) -> str:
    for key in ("subtitle", "tagline", "summary"):
        value = str(outline.get(key) or "").strip()
        if value:
            return value
    slides = outline.get("slides") or []
    if slides and isinstance(slides[0], dict):
        message = str(slides[0].get("key_message") or "").strip()
        if message:
            return message
    return "把关键判断讲清楚，再落到可执行的下一步"


def _apply_paragraph_font(paragraph, font_name: str) -> None:
    paragraph.font.name = font_name
    for run in paragraph.runs:
        run.font.name = font_name
        rPr = run._r.get_or_add_rPr()
        for tag in ("latin", "ea", "cs"):
            el = rPr.find(qn(f"a:{tag}"))
            if el is None:
                el = etree.SubElement(rPr, qn(f"a:{tag}"))
            el.set("typeface", font_name)


def _soften_rounded_rect(shape) -> None:
    try:
        shape.adjustments[0] = 0.08
    except (AttributeError, IndexError, ValueError):
        pass


def _item_at(items: List[str], index: int) -> str:
    return items[index] if 0 <= index < len(items) else ""


def _split_commercial_item(item: str) -> tuple[str, str]:
    headline, separator, detail = str(item).partition("\n")
    return headline.strip(), detail.strip() if separator else ""


def _add_academic_note(slide, label, body, left, top, width, height, style, featured=False):
    """Add a paper-like evidence note with a restrained research hierarchy."""
    note = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    note.fill.solid()
    note.fill.fore_color.rgb = style.PRIMARY_COLOR if featured else style.TEXT_WHITE
    note.line.color.rgb = style.PRIMARY_COLOR if featured else style.PRIMARY_LIGHT
    note.line.width = Pt(1)
    label_color = style.TEXT_WHITE if featured else style.PRIMARY_COLOR
    body_color = style.TEXT_WHITE if featured else style.TEXT_DARK
    headline, detail = _split_commercial_item(body)
    if height <= 1.4:
        _add_editorial_text(slide, label, left + 0.25, top + 0.14, 2.05, 0.26, style, 9, label_color, True)
        _add_editorial_text(slide, headline, left + 2.35, top + 0.13, width - 2.6, 0.38, style, 14, body_color, True)
        if detail:
            _add_editorial_text(slide, detail, left + 2.35, top + 0.62, width - 2.6, 0.32, style, 10, body_color)
        return note
    _add_editorial_text(slide, label, left + 0.25, top + 0.18, width - 0.5, 0.28, style, 10, label_color, True)
    _add_editorial_text(slide, headline, left + 0.25, top + 0.62, width - 0.5, 0.62, style, 16, body_color, True)
    if detail:
        _add_editorial_text(slide, detail, left + 0.25, top + 1.38, width - 0.5, max(height - 1.58, 0.25), style, 11, body_color)
    return note


def _render_slide_academic(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render an evidence-led research brief with paper and citation motifs."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    _add_editorial_text(slide, _cover_kicker(style), 0.7, 0.34, 2.7, 0.28, style, 9, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, _role_kicker(style, role, idx), 8.8, 0.34, 3.8, 0.28, style, 9, style.PRIMARY_COLOR, True, PP_ALIGN.RIGHT)
    rule = slide.shapes.add_shape(1, Inches(0.7), Inches(0.83), Inches(11.9), Inches(0.025))
    rule.fill.solid(); rule.fill.fore_color.rgb = style.PRIMARY_COLOR; rule.line.fill.background()
    _add_editorial_text(slide, title, 0.7, 1.02, 8.5, 0.68, style, 28, style.PRIMARY_DARK, True)
    _add_editorial_text(slide, key_message, 9.2, 1.05, 3.4, 0.58, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)

    if role == "evidence_story":
        _add_academic_note(slide, _chrome(style, "核心发现", "PRIMARY FINDING"), items[0], 0.7, 1.92, 4.0, 4.72, style, True)
        for number in range(1, 4):
            _add_academic_note(slide, _chrome(style, f"证据 [{number}]", f"EVIDENCE [{number}]"), _item_at(items, number), 5.05, 1.92 + (number - 1) * 1.57, 7.55, 1.28, style)
    elif role == "strategic_choice":
        _add_academic_note(slide, _chrome(style, "假设 A", "HYPOTHESIS A"), items[0], 0.7, 1.92, 5.55, 2.72, style)
        _add_academic_note(slide, _chrome(style, "假设 B", "HYPOTHESIS B"), _item_at(items, 1), 6.65, 1.92, 5.95, 2.72, style)
        _add_academic_note(slide, _chrome(style, "研究结论", "RESEARCH CONCLUSION"), "；".join(items[2:]) or key_message, 2.15, 5.02, 9.05, 1.38, style, True)
    elif role == "execution_roadmap":
        protocol = slide.shapes.add_shape(1, Inches(1.28), Inches(2.18), Inches(0.035), Inches(3.72))
        protocol.fill.solid(); protocol.fill.fore_color.rgb = style.PRIMARY_COLOR; protocol.line.fill.background()
        for number in range(3):
            top = 1.9 + number * 1.48
            marker = slide.shapes.add_shape(9, Inches(1.03), Inches(top + 0.3), Inches(0.52), Inches(0.52))
            marker.fill.solid(); marker.fill.fore_color.rgb = style.PRIMARY_COLOR; marker.line.fill.background()
            _add_editorial_text(slide, str(number + 1), 1.03, top + 0.42, 0.52, 0.2, style, 11, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
            _add_academic_note(slide, _chrome(style, f"步骤 / {('试点', '验证', '推广')[number]}", f"PROTOCOL / {('PILOT', 'VALIDATE', 'SCALE')[number]}"), _item_at(items, number), 1.85, top, 10.45, 1.12, style, number == 2)
        _add_editorial_text(slide, _item_at(items, 3), 1.85, 6.42, 10.45, 0.32, style, 10, style.TEXT_GRAY)
    elif role == "decision_close":
        _add_academic_note(slide, _chrome(style, "结论", "CONCLUSION"), items[0], 0.7, 1.92, 11.9, 2.05, style, True)
        for number in range(1, 4):
            _add_academic_note(slide, _chrome(style, f"含义 [{number}]", f"IMPLICATION [{number}]"), _item_at(items, number), 0.7 + (number - 1) * 4.05, 4.35, 3.8, 2.05, style)
    else:
        _add_academic_note(slide, _chrome(style, "研究问题", "RESEARCH QUESTION"), items[0], 0.7, 1.92, 7.15, 4.72, style, True)
        _add_academic_note(slide, _chrome(style, "观察 [1]", "OBSERVATION [1]"), _item_at(items, 1), 8.2, 1.92, 4.4, 2.05, style)
        _add_academic_note(slide, _chrome(style, "观察 [2]", "OBSERVATION [2]"), _item_at(items, 2), 8.2, 4.35, 4.4, 2.29, style)
        _add_editorial_text(slide, _item_at(items, 3), 1.02, 5.92, 6.5, 0.38, style, 10, style.TEXT_WHITE, True)
    sources = slide_data.get("evidence_sources") or []
    source_label = sources[0].get("title", "已批准大纲") if sources else "待补：基线数据、用户访谈或公开研究"
    _add_editorial_text(slide, f"{_chrome(style, '来源', 'SOURCE')} / {source_label[:72]}", 0.7, 6.92, 10.2, 0.24, style, 9, style.PRIMARY_COLOR)
    return slide


def _add_learning_card(slide, label, body, left, top, width, height, style, featured=False):
    """Add a workshop card with a clear label, lesson and supporting detail."""
    card = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    card.fill.solid()
    card.fill.fore_color.rgb = style.PRIMARY_COLOR if featured else style.TEXT_WHITE
    card.line.color.rgb = style.PRIMARY_COLOR if featured else style.PRIMARY_LIGHT
    card.line.width = Pt(1.25)
    label_color = style.TEXT_WHITE if featured else style.PRIMARY_COLOR
    text_color = style.TEXT_WHITE if featured else style.TEXT_DARK
    headline, detail = _split_commercial_item(body)
    _add_editorial_text(slide, label, left + 0.28, top + 0.18, width - 0.56, 0.3, style, 9, label_color, True)
    _add_editorial_text(slide, headline, left + 0.28, top + 0.65, width - 0.56, 0.62, style, 15, text_color, True)
    if detail and height >= 1.75:
        _add_editorial_text(slide, detail, left + 0.28, top + 1.4, width - 0.56, height - 1.62, style, 12, text_color)
    return card


def _render_slide_education(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render an adult learning workshop with objectives, practice and checks."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    chapter = slide.shapes.add_shape(5, Inches(0.68), Inches(0.38), Inches(1.35), Inches(0.42))
    chapter.fill.solid(); chapter.fill.fore_color.rgb = style.PRIMARY_COLOR; chapter.line.fill.background()
    _add_editorial_text(slide, _chrome(style, f"课时 {idx:02d}", f"LESSON {idx:02d}"), 0.68, 0.46, 1.35, 0.22, style, 9, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
    _add_editorial_text(slide, _role_kicker(style, role), 2.25, 0.46, 4.5, 0.25, style, 9, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, f"{idx + 1} / {total_slides}", 11.68, 0.46, 0.9, 0.25, style, 9, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    _add_editorial_text(slide, title, 0.68, 1.02, 8.65, 0.68, style, 29, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.25, 1.05, 3.33, 0.58, style, 12, style.PRIMARY_DARK, True, PP_ALIGN.RIGHT)

    if role == "evidence_story":
        _add_learning_card(slide, _chrome(style, "关键学习", "KEY LEARNING"), items[0], 0.68, 1.92, 4.2, 4.72, style, True)
        for number in range(1, 4):
            _add_learning_card(slide, _chrome(style, f"证据 {number}", f"PROOF POINT {number}"), _item_at(items, number), 5.18, 1.92 + (number - 1) * 1.57, 7.4, 1.28, style)
    elif role == "strategic_choice":
        _add_learning_card(slide, _chrome(style, "练习 A", "PRACTICE A"), items[0], 0.68, 1.92, 5.55, 2.75, style)
        _add_learning_card(slide, _chrome(style, "练习 B", "PRACTICE B"), _item_at(items, 1), 6.65, 1.92, 5.93, 2.75, style, True)
        _add_learning_card(slide, _chrome(style, "学习检验", "LEARNING CHECK"), "；".join(items[2:]) or key_message, 2.1, 5.03, 9.15, 1.38, style, True)
    elif role == "execution_roadmap":
        rail = slide.shapes.add_shape(1, Inches(1.25), Inches(3.16), Inches(10.7), Inches(0.06))
        rail.fill.solid(); rail.fill.fore_color.rgb = style.PRIMARY_LIGHT; rail.line.fill.background()
        for number in range(3):
            left = 0.68 + number * 4.08
            badge = slide.shapes.add_shape(9, Inches(left + 1.5), Inches(2.87), Inches(0.62), Inches(0.62))
            badge.fill.solid(); badge.fill.fore_color.rgb = style.PRIMARY_COLOR; badge.line.fill.background()
            _add_editorial_text(slide, str(number + 1), left + 1.5, 3.0, 0.62, 0.22, style, 12, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
            _add_learning_card(slide, _chrome(style, f"模块 / {('尝试', '练习', '应用')[number]}", f"MODULE / {('TRY', 'PRACTICE', 'APPLY')[number]}"), _item_at(items, number), left, 3.55, 3.65, 2.35, style, number == 2)
        _add_editorial_text(slide, _item_at(items, 3), 1.3, 6.3, 10.7, 0.38, style, 11, style.PRIMARY_DARK, True, PP_ALIGN.CENTER)
    elif role == "decision_close":
        _add_learning_card(slide, _chrome(style, "带走的要点", "TAKEAWAY"), items[0], 0.68, 1.92, 11.9, 2.02, style, True)
        for number in range(1, 4):
            _add_learning_card(slide, _chrome(style, f"下一步 {number}", f"NEXT STEP {number}"), _item_at(items, number), 0.68 + (number - 1) * 4.08, 4.35, 3.66, 2.05, style)
    else:
        _add_learning_card(slide, _chrome(style, "为什么重要", "WHY THIS MATTERS"), items[0], 0.68, 1.92, 6.95, 4.72, style, True)
        _add_learning_card(slide, _chrome(style, "请注意", "NOTICE"), _item_at(items, 1), 7.98, 1.92, 4.6, 2.05, style)
        _add_learning_card(slide, _chrome(style, "下一步尝试", "TRY NEXT"), _item_at(items, 2), 7.98, 4.35, 4.6, 2.29, style)
        _add_editorial_text(slide, _item_at(items, 3), 1.0, 5.9, 6.1, 0.42, style, 10, style.TEXT_WHITE, True)
    return slide


def _add_clinical_card(slide, label, body, left, top, width, height, style, featured=False):
    """Add a calm clinical brief card with evidence-first hierarchy."""
    card = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    card.fill.solid()
    card.fill.fore_color.rgb = style.PRIMARY_COLOR if featured else style.TEXT_WHITE
    card.line.color.rgb = style.PRIMARY_COLOR if featured else style.PRIMARY_LIGHT
    card.line.width = Pt(1)
    label_color = style.TEXT_WHITE if featured else style.PRIMARY_COLOR
    text_color = style.TEXT_WHITE if featured else style.TEXT_DARK
    headline, detail = _split_commercial_item(body)
    _add_editorial_text(slide, label, left + 0.3, top + 0.2, width - 0.6, 0.28, style, 9, label_color, True)
    _add_editorial_text(slide, headline, left + 0.3, top + 0.68, width - 0.6, 0.6, style, 15, text_color, True)
    if detail and height >= 1.7:
        _add_editorial_text(slide, detail, left + 0.3, top + 1.42, width - 0.6, height - 1.62, style, 12, text_color)
    return card


def _render_slide_medical(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render a clinical brief with findings, options, pathway and care actions."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    _add_editorial_text(slide, _cover_kicker(style), 0.72, 0.42, 2.4, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, _chrome(style, f"病例 / {idx:02d}", f"CASE / {idx:02d}"), 10.75, 0.42, 1.8, 0.28, style, 9, style.TEXT_GRAY, True, PP_ALIGN.RIGHT)
    _add_editorial_text(slide, title, 0.72, 0.98, 8.4, 0.7, style, 28, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.28, 1.02, 3.3, 0.58, style, 12, style.PRIMARY_DARK, True, PP_ALIGN.RIGHT)
    rule = slide.shapes.add_shape(1, Inches(0.72), Inches(1.78), Inches(11.88), Inches(0.025))
    rule.fill.solid(); rule.fill.fore_color.rgb = style.PRIMARY_LIGHT; rule.line.fill.background()

    if role == "evidence_story":
        _add_clinical_card(slide, _chrome(style, "核心发现", "PRIMARY FINDING"), items[0], 0.72, 2.05, 4.25, 4.45, style, True)
        for number in range(1, 4):
            _add_clinical_card(slide, _chrome(style, f"证据 / {number}", f"EVIDENCE / {number}"), _item_at(items, number), 5.25, 2.05 + (number - 1) * 1.5, 7.35, 1.23, style)
    elif role == "strategic_choice":
        _add_clinical_card(slide, _chrome(style, "方案 A", "OPTION A"), items[0], 0.72, 2.05, 5.5, 2.65, style)
        _add_clinical_card(slide, _chrome(style, "推荐方案", "RECOMMENDED OPTION"), _item_at(items, 1), 6.65, 2.05, 5.95, 2.65, style, True)
        _add_clinical_card(slide, _chrome(style, "临床依据", "CLINICAL RATIONALE"), "；".join(items[2:]) or key_message, 2.05, 5.03, 9.2, 1.35, style, True)
    elif role == "execution_roadmap":
        _add_editorial_text(slide, _chrome(style, "照护路径", "CARE PATHWAY"), 0.72, 2.18, 2.4, 0.3, style, 10, style.PRIMARY_COLOR, True)
        rail = slide.shapes.add_shape(1, Inches(1.0), Inches(3.2), Inches(11.0), Inches(0.04))
        rail.fill.solid(); rail.fill.fore_color.rgb = style.PRIMARY_LIGHT; rail.line.fill.background()
        for number in range(3):
            left = 0.72 + number * 4.08
            marker = slide.shapes.add_shape(9, Inches(left + 1.48), Inches(2.88), Inches(0.64), Inches(0.64))
            marker.fill.solid(); marker.fill.fore_color.rgb = style.PRIMARY_COLOR; marker.line.fill.background()
            _add_editorial_text(slide, str(number + 1), left + 1.48, 3.03, 0.64, 0.2, style, 12, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
            _add_clinical_card(slide, _chrome(style, ("评估", "处置", "随访")[number], ("ASSESS", "TREAT", "FOLLOW UP")[number]), _item_at(items, number), left, 3.58, 3.65, 2.15, style, number == 2)
        _add_editorial_text(slide, _item_at(items, 3), 1.25, 6.25, 10.8, 0.35, style, 11, style.PRIMARY_DARK, True, PP_ALIGN.CENTER)
    elif role == "decision_close":
        _add_clinical_card(slide, _chrome(style, "照护决策", "CARE DECISION"), items[0], 0.72, 2.05, 11.88, 1.95, style, True)
        for number in range(1, 4):
            _add_clinical_card(slide, _chrome(style, f"行动 / {number}", f"ACTION / {number}"), _item_at(items, number), 0.72 + (number - 1) * 4.08, 4.35, 3.66, 2.15, style)
    else:
        _add_clinical_card(slide, _chrome(style, "临床信号", "CLINICAL SIGNAL"), items[0], 0.72, 2.05, 6.95, 4.45, style, True)
        _add_clinical_card(slide, _chrome(style, "患者影响", "PATIENT IMPACT"), _item_at(items, 1), 7.98, 2.05, 4.62, 1.95, style)
        _add_clinical_card(slide, _chrome(style, "下次复核", "NEXT REVIEW"), _item_at(items, 2), 7.98, 4.35, 4.62, 2.15, style)
    sources = slide_data.get("evidence_sources") or []
    source_label = sources[0].get("title", "已批准大纲") if sources else "待补：临床指南、病例数据或用户访谈"
    _add_editorial_text(slide, f"{_chrome(style, '来源', 'SOURCE')} / {source_label[:68]}", 0.72, 6.9, 10.8, 0.28, style, 10, style.PRIMARY_COLOR)
    _add_editorial_text(slide, f"{idx + 1} / {total_slides}", 11.68, 6.92, 0.9, 0.24, style, 9, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    return slide


def _add_elegant_note(slide, label, body, left, top, width, height, style, featured=False):
    """Add a restrained editorial note for executive presentations."""
    note = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    note.fill.solid()
    note.fill.fore_color.rgb = style.PRIMARY_COLOR if featured else style.TEXT_WHITE
    note.line.color.rgb = style.PRIMARY_COLOR if featured else style.PRIMARY_LIGHT
    note.line.width = Pt(0.75)
    label_color = style.TEXT_WHITE if featured else style.PRIMARY_COLOR
    text_color = style.TEXT_WHITE if featured else style.TEXT_DARK
    headline, detail = _split_commercial_item(body)
    _add_editorial_text(slide, label, left + 0.28, top + 0.18, width - 0.56, 0.28, style, 9, label_color, True)
    divider = slide.shapes.add_shape(1, Inches(left + 0.28), Inches(top + 0.58), Inches(min(width - 0.56, 1.05)), Inches(0.025))
    divider.fill.solid(); divider.fill.fore_color.rgb = label_color; divider.line.fill.background()
    if height < 1.75:
        _add_editorial_text(slide, headline, left + 0.28, top + 0.67, width - 0.56, max(height - 0.84, 0.28), style, 12, text_color, featured)
    else:
        _add_editorial_text(slide, headline, left + 0.28, top + 0.72, width - 0.56, 0.62, style, 15, text_color, True)
    if detail and height >= 1.75:
        _add_editorial_text(slide, detail, left + 0.28, top + 1.48, width - 0.56, height - 1.68, style, 12, text_color)
    return note


def _render_slide_elegant(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render a premium board memo with editorial hierarchy and fine rules."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    _add_editorial_text(slide, _cover_kicker(style), 0.72, 0.42, 2.7, 0.28, style, 9, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, f"{idx + 1:02d}", 11.78, 0.36, 0.8, 0.38, style, 16, style.PRIMARY_COLOR, True, PP_ALIGN.RIGHT)
    _add_editorial_text(slide, title, 0.72, 0.95, 8.4, 0.72, style, 29, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.15, 1.0, 3.43, 0.58, style, 11, style.PRIMARY_DARK, False, PP_ALIGN.RIGHT)
    top_rule = slide.shapes.add_shape(1, Inches(0.72), Inches(1.78), Inches(11.86), Inches(0.02))
    top_rule.fill.solid(); top_rule.fill.fore_color.rgb = style.PRIMARY_COLOR; top_rule.line.fill.background()

    if role == "evidence_story":
        _add_elegant_note(slide, _chrome(style, "证据", "THE EVIDENCE"), items[0], 0.72, 2.08, 4.05, 4.35, style, True)
        for number in range(1, 4):
            top = 2.08 + (number - 1) * 1.48
            _add_editorial_text(slide, f"0{number}", 5.25, top + 0.05, 0.55, 0.35, style, 16, style.PRIMARY_COLOR, True)
            _add_elegant_note(slide, _chrome(style, "证据笔记", "EVIDENCE NOTE"), _item_at(items, number), 5.95, top, 6.63, 1.18, style)
    elif role == "strategic_choice":
        _add_elegant_note(slide, _chrome(style, "路径 A", "PATH A"), items[0], 0.72, 2.08, 4.7, 2.65, style)
        _add_elegant_note(slide, _chrome(style, "路径 B", "PATH B"), _item_at(items, 1), 5.78, 2.08, 6.8, 2.65, style)
        _add_elegant_note(slide, _chrome(style, "董事会建议", "BOARD RECOMMENDATION"), "；".join(items[2:]) or key_message, 2.08, 5.08, 9.18, 1.3, style, True)
    elif role == "execution_roadmap":
        spine = slide.shapes.add_shape(1, Inches(2.15), Inches(2.18), Inches(0.025), Inches(4.05))
        spine.fill.solid(); spine.fill.fore_color.rgb = style.PRIMARY_COLOR; spine.line.fill.background()
        for number in range(3):
            top = 2.02 + number * 1.42
            _add_editorial_text(slide, f"0{number + 1}", 0.72, top + 0.28, 0.7, 0.35, style, 16, style.PRIMARY_COLOR, True)
            marker = slide.shapes.add_shape(9, Inches(1.98), Inches(top + 0.31), Inches(0.36), Inches(0.36))
            marker.fill.solid(); marker.fill.fore_color.rgb = style.PRIMARY_COLOR; marker.line.fill.background()
            _add_elegant_note(slide, _chrome(style, ("承诺", "验证", "扩大")[number], ("COMMIT", "PROVE", "EXPAND")[number]), _item_at(items, number), 2.72, top, 9.86, 1.12, style, number == 2)
        _add_editorial_text(slide, _item_at(items, 3), 2.72, 6.38, 9.86, 0.32, style, 11, style.PRIMARY_DARK, True)
    elif role == "decision_close":
        _add_elegant_note(slide, _chrome(style, "决议", "RESOLUTION"), items[0], 0.72, 2.08, 11.86, 1.86, style, True)
        for number in range(1, 4):
            _add_elegant_note(slide, _chrome(style, f"承诺 / 0{number}", f"COMMITMENT / 0{number}"), _item_at(items, number), 0.72 + (number - 1) * 4.08, 4.38, 3.66, 2.02, style)
    else:
        _add_editorial_text(slide, "01", 0.72, 2.12, 1.4, 0.9, style, 44, style.PRIMARY_COLOR, True)
        _add_elegant_note(slide, _chrome(style, "核心信号", "PRIMARY SIGNAL"), items[0], 2.05, 2.08, 6.12, 4.35, style, True)
        _add_elegant_note(slide, _chrome(style, "含义", "IMPLICATION"), _item_at(items, 1), 8.55, 2.08, 4.03, 1.88, style)
        _add_elegant_note(slide, _chrome(style, "验证", "VALIDATION"), _item_at(items, 2), 8.55, 4.38, 4.03, 2.05, style)
    _add_editorial_text(slide, _chrome(style, "内部审阅", "PRIVATE & CONFIDENTIAL"), 0.72, 6.92, 3.0, 0.22, style, 8, style.TEXT_GRAY, True)
    return slide


def _add_modern_tile(slide, label, body, left, top, width, height, style, featured=False):
    tile = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    tile.fill.solid()
    tile.fill.fore_color.rgb = style.PRIMARY_COLOR if featured else style.BG_WHITE
    tile.line.color.rgb = style.PRIMARY_COLOR if featured else style.PRIMARY_LIGHT
    tile.line.width = Pt(1.25)
    _soften_rounded_rect(tile)
    text_color = style.TEXT_WHITE if featured else style.TEXT_DARK
    label_color = style.TEXT_WHITE if featured else style.PRIMARY_COLOR
    _add_editorial_text(slide, label, left + 0.28, top + 0.18, width - 0.56, 0.28, style, 11, label_color, True)
    headline, detail = _split_commercial_item(body)
    body_top = top + 0.5
    body_height = max(0.4, height - 0.68)
    if detail and height >= 1.6:
        head_h = 0.52 if height < 2.2 else 0.68
        _add_editorial_text(slide, headline, left + 0.28, body_top, width - 0.56, head_h, style, 16 if height < 2.2 else 18, text_color, True)
        _add_editorial_text(slide, detail, left + 0.28, body_top + head_h + 0.06, width - 0.56, max(0.36, body_height - head_h - 0.08), style, 12, text_color)
    elif height >= 2.2:
        size = 16 if width < 4.5 else (18 if featured else 16)
        _add_editorial_text(slide, body, left + 0.28, body_top, width - 0.56, body_height, style, size, text_color, True, anchor=MSO_ANCHOR.MIDDLE)
    else:
        _add_editorial_text(slide, body, left + 0.28, body_top, width - 0.56, body_height, style, 15, text_color, featured, anchor=MSO_ANCHOR.MIDDLE)
    return tile


def _render_slide_modern(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render a modular product-story layout with strong metric tiles."""
    if style.template_name == "modern" and slide_data.get("layout_variant", 0) > 0:
        return _render_slide_modern_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    add_page_number(slide, prs, idx + 1, total_slides, style)
    _add_editorial_text(slide, _role_kicker(style, role, idx), 0.72, 0.38, 4.8, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.72, 0.72, 8.6, 0.58, style, 28, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.05, 0.68, 3.55, 0.55, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)

    if role == "evidence_story":
        _add_modern_tile(slide, _chrome(style, "核心信号", "PRIMARY SIGNAL"), items[0], 0.72, 1.52, 11.88, 1.42, style, True)
        for number in range(1, 4):
            _add_modern_tile(slide, _chrome(style, f"证据 {number:02d}", f"EVIDENCE {number:02d}"), _item_at(items, number), 0.72 + (number - 1) * 4.05, 3.18, 3.85, 2.55, style, number == 1)
    elif role == "strategic_choice":
        _add_modern_tile(slide, _chrome(style, "方案 01", "OPTION 01"), items[0], 0.72, 1.52, 5.7, 2.35, style)
        _add_modern_tile(slide, _chrome(style, "方案 02 / 推荐", "OPTION 02 / RECOMMENDED"), _item_at(items, 1), 6.9, 1.52, 5.7, 2.35, style, True)
        _add_modern_tile(slide, _chrome(style, "决策", "DECISION"), "；".join(items[2:]) or key_message, 0.72, 4.12, 11.88, 1.55, style, True)
    elif role == "execution_roadmap":
        rail = slide.shapes.add_shape(1, Inches(1.0), Inches(3.15), Inches(11.25), Inches(0.06))
        rail.fill.solid(); rail.fill.fore_color.rgb = style.PRIMARY_LIGHT; rail.line.fill.background()
        for number in range(3):
            left = 0.72 + number * 4.15
            stage = (_chrome(style, "试点", "PILOT"), _chrome(style, "扩展", "EXPAND"), _chrome(style, "规模化", "SCALE"))[number]
            _add_modern_tile(slide, f"0{number + 1} / {stage}", _item_at(items, number), left, 2.05, 3.72, 2.2, style, number == 2)
        _add_editorial_text(slide, _item_at(items, 3), 0.72, 4.52, 11.88, 0.5, style, 14, style.PRIMARY_COLOR, True, PP_ALIGN.CENTER)
    elif role == "decision_close":
        _add_modern_tile(slide, _chrome(style, "优先事项", "PRIORITY"), items[0], 0.72, 1.52, 11.88, 1.42, style, True)
        for number in range(1, 4):
            _add_modern_tile(slide, _chrome(style, f"行动 {number:02d}", f"ACTION {number:02d}"), _item_at(items, number), 0.72 + (number - 1) * 4.05, 3.18, 3.85, 2.55, style, number == 1)
    else:
        _add_modern_tile(slide, _chrome(style, "机会 / 01", "OPPORTUNITY / 01"), items[0], 0.72, 1.52, 5.85, 2.4, style, True)
        _add_modern_tile(slide, _chrome(style, "信号 / 02", "SIGNAL / 02"), _item_at(items, 1), 6.85, 1.52, 5.75, 2.4, style)
        _add_modern_tile(slide, _chrome(style, "信号 / 03", "SIGNAL / 03"), _item_at(items, 2), 0.72, 4.15, 5.85, 2.18, style)
        _add_modern_tile(slide, _chrome(style, "信号 / 04", "SIGNAL / 04"), _item_at(items, 3), 6.85, 4.15, 5.75, 2.18, style)
    return slide


def _render_slide_modern_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render stable composition families for long decks."""
    variant = slide_data.get("layout_variant", 1)
    if variant == 7:
        return _render_modern_full_bleed_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 8:
        return _render_modern_timeline_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 9:
        return _render_modern_metric_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 10:
        return _render_modern_split_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 2:
        return _render_modern_grid_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 3:
        return _render_modern_statement_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 4:
        return _render_modern_rail_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 5:
        return _render_modern_matrix_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if variant == 6 or variant == 0:
        return _render_modern_quote_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    add_page_number(slide, prs, idx + 1, total_slides, style)
    band = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.333), Inches(1.45))
    band.fill.solid(); band.fill.fore_color.rgb = style.PRIMARY_COLOR; band.line.fill.background()
    _add_editorial_text(slide, _role_kicker(style, role, idx), 0.72, 0.34, 4.4, 0.28, style, 10, style.ACCENT_LIGHT, True)
    _add_editorial_text(slide, title, 0.72, 0.7, 7.8, 0.52, style, 27, style.TEXT_WHITE, True)
    _add_editorial_text(slide, key_message, 9.0, 0.65, 3.55, 0.62, style, 12, style.TEXT_WHITE, False, PP_ALIGN.RIGHT)
    _add_editorial_text(slide, "核心判断", 0.82, 1.95, 1.55, 0.3, style, 11, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, _item_at(items, 0), 0.82, 2.38, 4.0, 1.9, style, 25, style.TEXT_DARK, True)
    _add_editorial_text(slide, "从理解到参与，每一步都应留下可观察的结果。", 0.82, 5.35, 4.25, 0.5, style, 12, style.TEXT_GRAY)
    for number in range(1, 4):
        top = 1.9 + (number - 1) * 1.45
        marker = slide.shapes.add_shape(9, Inches(5.35), Inches(top + 0.05), Inches(0.48), Inches(0.48))
        marker.fill.solid(); marker.fill.fore_color.rgb = style.ACCENT_COLOR; marker.line.fill.background()
        _add_editorial_text(slide, str(number), 5.35, top + 0.14, 0.48, 0.2, style, 11, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
        _add_editorial_text(slide, ["事实", "选择", "行动"][number - 1], 6.05, top, 1.2, 0.28, style, 11, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, _item_at(items, number), 7.35, top - 0.02, 5.0, 0.72, style, 15, style.TEXT_DARK)
        if number < 3:
            rule = slide.shapes.add_shape(1, Inches(5.58), Inches(top + 0.62), Inches(0.03), Inches(0.7))
            rule.fill.solid(); rule.fill.fore_color.rgb = style.PRIMARY_LIGHT; rule.line.fill.background()
    _add_editorial_text(slide, _item_at(items, 3), 5.35, 6.25, 7.0, 0.35, style, 11, style.PRIMARY_COLOR, True)
    return slide


def _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides):
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    add_page_number(slide, prs, idx + 1, total_slides, style)
    return slide, items, title, key_message


def _render_modern_grid_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '四个视角', 'FOUR LENSES')}", 0.72, 0.42, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.72, 0.85, 8.5, 0.65, style, 30, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 0.75, 1.58, 11.5, 0.35, style, 13, style.TEXT_GRAY)
    labels = ("理解", "参与", "协作", "结果")
    for i in range(4):
        left = 0.72 + (i % 2) * 6.15
        top = 2.35 + (i // 2) * 1.95
        _add_modern_tile(slide, f"0{i + 1} / {labels[i]}", _item_at(items, i), left, top, 5.55, 1.5, style, i == 3)
    return slide


def _render_modern_statement_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '核心判断', 'STATEMENT')}", 0.78, 0.5, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.78, 0.95, 11.4, 0.65, style, 30, style.TEXT_DARK, True)
    panel = slide.shapes.add_shape(5, Inches(0.78), Inches(2.05), Inches(11.75), Inches(2.05))
    panel.fill.solid(); panel.fill.fore_color.rgb = style.PRIMARY_COLOR; panel.line.fill.background()
    _add_editorial_text(slide, items[0], 1.2, 2.55, 10.9, 0.9, style, 26, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
    _add_editorial_text(slide, key_message, 1.2, 4.55, 10.9, 0.4, style, 14, style.TEXT_GRAY, False, PP_ALIGN.CENTER)
    for i in range(1, 4):
        _add_editorial_card(slide, ("依据", "方法", "衡量")[i - 1], _item_at(items, i), 0.78 + (i - 1) * 4.0, 5.35, 3.65, 1.0, style, style.ACCENT_COLOR)
    return slide


def _render_modern_rail_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    rail = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(2.2), Inches(7.5))
    rail.fill.solid(); rail.fill.fore_color.rgb = style.PRIMARY_COLOR; rail.line.fill.background()
    _add_editorial_text(slide, f"{idx:02d}", 0.55, 0.62, 1.1, 0.7, style, 32, style.TEXT_WHITE, True)
    _add_editorial_text(slide, _chrome(style, "行动\n路径", "ACTION\nPATH"), 0.58, 1.65, 1.1, 0.8, style, 15, style.ACCENT_LIGHT, True)
    _add_editorial_text(slide, title, 2.85, 0.75, 8.7, 0.65, style, 30, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 2.88, 1.55, 9.5, 0.4, style, 13, style.TEXT_GRAY)
    for i in range(4):
        top = 2.3 + i * 1.05
        _add_editorial_text(slide, f"0{i + 1}", 2.9, top, 0.5, 0.3, style, 12, style.PRIMARY_COLOR, True)
        _add_editorial_text(slide, _item_at(items, i), 3.8, top - 0.03, 8.2, 0.62, style, 16, style.TEXT_DARK)
        if i < 3:
            _add_minimal_rule(slide, 3.8, top + 0.75, 8.2, style)
    return slide


def _render_modern_matrix_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '现场笔记', 'FIELD NOTES')}", 0.75, 0.45, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.75, 0.9, 7.8, 0.62, style, 29, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 8.95, 0.92, 3.55, 0.55, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    for i in range(4):
        left = 0.75 + (i % 2) * 6.05
        top = 2.0 + (i // 2) * 2.15
        tile = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(5.45), Inches(1.7))
        tile.fill.solid(); tile.fill.fore_color.rgb = style.TEXT_WHITE; tile.line.color.rgb = style.PRIMARY_LIGHT
        _add_editorial_text(slide, f"{i + 1:02d}", left + 0.28, top + 0.25, 0.5, 0.3, style, 14, style.ACCENT_COLOR, True)
        _add_editorial_text(slide, _item_at(items, i), left + 1.0, top + 0.25, 4.05, 1.05, style, 15, style.TEXT_DARK, i == 0)
    return slide


def _render_modern_quote_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '要点', 'TAKEAWAY')}", 0.82, 0.55, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, "“", 0.8, 1.55, 1.0, 1.0, style, 72, style.ACCENT_COLOR, True)
    _add_editorial_text(slide, items[0], 1.65, 1.85, 10.3, 1.35, style, 31, style.TEXT_DARK, True)
    _add_editorial_text(slide, title, 1.68, 3.65, 9.5, 0.5, style, 17, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, key_message, 1.68, 4.35, 8.7, 0.6, style, 14, style.TEXT_GRAY)
    _add_editorial_card(slide, "下一步", "；".join(items[1:]), 1.68, 5.55, 10.3, 0.85, style, style.ACCENT_COLOR, filled=True)
    return slide


def _render_modern_full_bleed_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    hero = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    hero.fill.solid(); hero.fill.fore_color.rgb = style.PRIMARY_COLOR; hero.line.fill.background()
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '立场', 'POINT OF VIEW')}", 0.82, 0.62, 4.8, 0.3, style, 10, style.ACCENT_LIGHT, True)
    _add_editorial_text(slide, items[0], 1.0, 2.05, 11.2, 1.45, style, 34, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
    _add_editorial_text(slide, title, 1.1, 4.05, 11.0, 0.55, style, 19, style.ACCENT_LIGHT, True, PP_ALIGN.CENTER)
    _add_editorial_text(slide, key_message, 2.0, 5.05, 9.3, 0.7, style, 14, style.TEXT_WHITE, False, PP_ALIGN.CENTER)
    return slide


def _render_modern_timeline_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '节奏', 'SEQUENCE')}", 0.75, 0.45, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.75, 0.9, 8.4, 0.6, style, 29, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.3, 0.93, 3.2, 0.5, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    rail = slide.shapes.add_shape(1, Inches(1.1), Inches(3.35), Inches(11.1), Inches(0.06))
    rail.fill.solid(); rail.fill.fore_color.rgb = style.PRIMARY_LIGHT; rail.line.fill.background()
    labels = ("起点", "转折", "放大", "结果")
    for number in range(4):
        left = 0.72 + number * 3.05
        marker = slide.shapes.add_shape(9, Inches(left + 0.7), Inches(3.05), Inches(0.65), Inches(0.65))
        marker.fill.solid(); marker.fill.fore_color.rgb = style.ACCENT_COLOR if number == 3 else style.PRIMARY_COLOR; marker.line.fill.background()
        _add_editorial_text(slide, str(number + 1), left + 0.7, 3.22, 0.65, 0.22, style, 13, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
        _add_editorial_text(slide, labels[number], left, 2.35, 2.05, 0.3, style, 11, style.PRIMARY_COLOR, True, PP_ALIGN.CENTER)
        _add_editorial_text(slide, _item_at(items, number), left, 4.05, 2.25, 1.35, style, 14, style.TEXT_DARK, number == 3, PP_ALIGN.CENTER)
    return slide


def _render_modern_metric_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '信号', 'SIGNALS')}", 0.75, 0.45, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.75, 0.9, 8.3, 0.6, style, 29, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.25, 0.93, 3.25, 0.5, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    _add_editorial_text(slide, items[0], 0.85, 2.0, 7.05, 2.0, style, 33, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, "核心信号", 0.9, 4.55, 2.1, 0.3, style, 11, style.TEXT_GRAY, True)
    for number in range(1, 4):
        top = 1.82 + (number - 1) * 1.45
        _add_modern_tile(slide, _chrome(style, f"指标 0{number}", f"METRIC 0{number}"), _item_at(items, number), 8.25, top, 4.25, 1.12, style, number == 3)
    return slide


def _render_modern_split_variant(prs, blank_layout, style, slide_data, idx, total_slides):
    slide, items, title, key_message = _modern_variant_base(prs, blank_layout, style, slide_data, idx, total_slides)
    _add_editorial_text(slide, f"{idx:02d} / {_chrome(style, '两个视角', 'TWO LENSES')}", 0.75, 0.45, 4.0, 0.28, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, title, 0.75, 0.9, 8.2, 0.6, style, 29, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.2, 0.93, 3.3, 0.5, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    _add_modern_tile(slide, _chrome(style, "视角 A", "LENS A"), items[0], 0.75, 2.0, 5.7, 3.9, style, True)
    _add_modern_tile(slide, _chrome(style, "视角 B", "LENS B"), _item_at(items, 1), 6.9, 2.0, 5.7, 3.9, style)
    _add_editorial_text(slide, "共同结论", 1.0, 6.25, 1.6, 0.25, style, 10, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, "；".join(items[2:]), 2.3, 6.2, 9.6, 0.35, style, 12, style.TEXT_GRAY)
    return slide


def _add_minimal_rule(slide, left, top, width, style, weight=1):
    rule = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(0.02 * weight))
    rule.fill.solid(); rule.fill.fore_color.rgb = style.PRIMARY_LIGHT; rule.line.fill.background()
    return rule


def _render_slide_minimal(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render a restrained editorial layout built from type and rules."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    _add_editorial_text(slide, f"{idx:02d}", 0.65, 0.42, 0.7, 0.4, style, 12, style.TEXT_DARK, True)
    _add_editorial_text(slide, _role_kicker(style, role), 1.5, 0.42, 4.4, 0.4, style, 10, style.TEXT_GRAY, True)
    _add_editorial_text(slide, f"{idx + 1} / {total_slides}", 11.8, 0.42, 0.85, 0.4, style, 10, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)
    _add_minimal_rule(slide, 0.65, 1.0, 12.0, style, 2)
    _add_editorial_text(slide, title, 0.65, 1.22, 8.65, 0.72, style, 30, style.TEXT_DARK, True)
    _add_editorial_text(slide, key_message, 9.45, 1.28, 3.2, 0.62, style, 12, style.TEXT_GRAY, False, PP_ALIGN.RIGHT)

    if role == "execution_roadmap":
        timeline = slide.shapes.add_shape(1, Inches(2.13), Inches(2.25), Inches(0.03), Inches(3.55))
        timeline.fill.solid(); timeline.fill.fore_color.rgb = style.TEXT_DARK; timeline.line.fill.background()
        for number in range(3):
            top = 2.08 + number * 1.4
            _add_editorial_text(slide, f"0{number + 1}", 0.75, top, 0.7, 0.45, style, 18, style.TEXT_DARK, True)
            _add_editorial_text(slide, ("试点", "扩展", "规模化")[number], 1.45, top, 0.7, 0.45, style, 11, style.TEXT_GRAY, True)
            _add_editorial_text(slide, _item_at(items, number), 2.65, top - 0.05, 9.7, 0.75, style, 15, style.TEXT_DARK)
            _add_minimal_rule(slide, 2.65, top + 0.85, 9.7, style)
    elif role == "decision_close":
        _add_editorial_text(slide, items[0], 0.65, 2.25, 11.3, 1.25, style, 25, style.TEXT_DARK, True)
        _add_minimal_rule(slide, 0.65, 3.72, 12.0, style)
        for number in range(1, 4):
            left = 0.65 + (number - 1) * 4.0
            _add_editorial_text(slide, _chrome(style, f"行动 / 0{number}", f"ACTION / 0{number}"), left, 4.05, 3.55, 0.3, style, 10, style.TEXT_GRAY, True)
            _add_editorial_text(slide, _item_at(items, number), left, 4.55, 3.55, 1.25, style, 15, style.TEXT_DARK)
    else:
        labels = {
            "strategic_choice": (
                _chrome(style, "方案 A", "A / OPTION"),
                _chrome(style, "方案 B", "B / OPTION"),
                _chrome(style, "决策", "DECISION /"),
            ),
            "evidence_story": (
                _chrome(style, "01 / 信号", "01 / SIGNAL"),
                _chrome(style, "02 / 信号", "02 / SIGNAL"),
                _chrome(style, "03 / 含义", "03 / MEANING"),
            ),
            "opportunity_map": (
                _chrome(style, "01 / 变化", "01 / CHANGE"),
                _chrome(style, "02 / 窗口", "02 / WINDOW"),
                _chrome(style, "03 / 验证", "03 / TEST"),
            ),
        }.get(role, (
            _chrome(style, "01 / 要点", "01 / POINT"),
            _chrome(style, "02 / 要点", "02 / POINT"),
            _chrome(style, "03 / 要点", "03 / POINT"),
        ))
        for number in range(3):
            top = 2.28 + number * 1.25
            if role == "strategic_choice" and number == 2:
                decision = slide.shapes.add_shape(1, Inches(0.65), Inches(top - 0.18), Inches(12.0), Inches(1.02))
                decision.fill.solid(); decision.fill.fore_color.rgb = style.TEXT_DARK; decision.line.fill.background()
                _add_editorial_text(slide, labels[number], 0.92, top, 1.2, 0.35, style, 10, style.TEXT_WHITE, True)
                _add_editorial_text(slide, _item_at(items, number), 2.2, top - 0.08, 9.95, 0.68, style, 16, style.TEXT_WHITE, True)
                continue
            _add_editorial_text(slide, labels[number], 0.65, top, 1.35, 0.35, style, 10, style.TEXT_GRAY, True)
            _add_editorial_text(slide, _item_at(items, number), 2.2, top - 0.08, 10.1, 0.68, style, 16, style.TEXT_DARK, False)
            _add_minimal_rule(slide, 2.2, top + 0.72, 10.1, style)
        _add_editorial_text(slide, _item_at(items, 3), 2.2, 6.15, 10.1, 0.45, style, 12, style.TEXT_GRAY)
    return slide


def _add_tech_panel(slide, label, body, left, top, width, height, style, featured=False):
    panel = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    panel.fill.solid(); panel.fill.fore_color.rgb = style.PRIMARY_DARK if featured else style.BG_WHITE
    panel.line.color.rgb = style.ACCENT_COLOR; panel.line.width = Pt(1.5 if featured else 0.75)
    corner = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(0.42), Inches(0.06))
    corner.fill.solid(); corner.fill.fore_color.rgb = style.ACCENT_COLOR; corner.line.fill.background()
    _add_editorial_text(slide, label, left + 0.25, top + 0.2, width - 0.5, 0.3, style, 10, style.ACCENT_LIGHT, True)
    headline, detail = _split_commercial_item(body)
    if detail and height >= 2.0:
        _add_editorial_text(slide, headline, left + 0.25, top + 0.65, width - 0.5, 0.68, style, 16, style.TEXT_WHITE, True)
        _add_editorial_text(slide, detail, left + 0.25, top + 1.48, width - 0.5, height - 1.7, style, 11, style.ACCENT_LIGHT)
    else:
        _add_editorial_text(slide, body, left + 0.25, top + 0.62, width - 0.5, height - 0.82, style, 14, style.TEXT_WHITE, featured)
    return panel


def _render_slide_tech(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render a dark technical command-center layout."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    items = _commercial_slide_items(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    key_message = slide_data.get("key_message") or ""
    _add_editorial_text(slide, _cover_kicker(style), 0.7, 0.35, 3.0, 0.25, style, 9, style.ACCENT_LIGHT, True)
    _add_editorial_text(slide, _chrome(style, f"节点 {idx:02d}", f"NODE {idx:02d}"), 10.9, 0.35, 1.7, 0.25, style, 9, style.ACCENT_LIGHT, True, PP_ALIGN.RIGHT)
    _add_editorial_text(slide, title, 0.7, 0.72, 8.75, 0.62, style, 28, style.TEXT_WHITE, True)
    _add_editorial_text(slide, key_message, 9.15, 0.74, 3.45, 0.54, style, 12, style.ACCENT_LIGHT, True, PP_ALIGN.RIGHT)
    header_line = slide.shapes.add_shape(1, Inches(0.7), Inches(1.42), Inches(11.9), Inches(0.04))
    header_line.fill.solid(); header_line.fill.fore_color.rgb = style.ACCENT_COLOR; header_line.line.fill.background()

    if role == "evidence_story":
        _add_tech_panel(slide, _chrome(style, "核心信号", "CORE / SIGNAL"), items[0], 0.7, 1.78, 4.15, 4.9, style, True)
        for number in range(1, 4):
            _add_tech_panel(slide, _chrome(style, f"数据 / 0{number}", f"DATA / 0{number}"), _item_at(items, number), 5.2, 1.78 + (number - 1) * 1.62, 7.4, 1.28, style)
    elif role == "strategic_choice":
        _add_tech_panel(slide, _chrome(style, "节点 A / 方案", "NODE A / OPTION"), items[0], 0.7, 1.82, 5.45, 2.75, style)
        _add_tech_panel(slide, _chrome(style, "节点 B / 推荐", "NODE B / RECOMMENDED"), _item_at(items, 1), 7.15, 1.82, 5.45, 2.75, style, True)
        connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(6.15), Inches(3.18), Inches(7.15), Inches(3.18))
        connector.line.color.rgb = style.ACCENT_COLOR; connector.line.width = Pt(2)
        _add_tech_panel(slide, _chrome(style, "锁定建议", "LOCK / RECOMMENDATION"), "；".join(items[2:]) or key_message, 2.35, 5.05, 8.65, 1.35, style, True)
    elif role == "execution_roadmap":
        for number in range(3):
            left = 0.7 + number * 4.18
            top = 2.0 + number * 0.42
            _add_tech_panel(slide, _chrome(style, f"阶段 / 0{number + 1}", f"PHASE / 0{number + 1}"), _item_at(items, number), left, top, 3.65, 3.25, style, number == 2)
            if number < 2:
                connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(left + 3.65), Inches(top + 1.62), Inches(left + 4.18), Inches(top + 2.04))
                connector.line.color.rgb = style.ACCENT_COLOR; connector.line.width = Pt(2)
        _add_editorial_text(slide, _item_at(items, 3), 1.2, 6.35, 10.9, 0.35, style, 11, style.ACCENT_LIGHT, True, PP_ALIGN.CENTER)
    elif role == "decision_close":
        _add_tech_panel(slide, _chrome(style, "优先锁定", "PRIORITY / LOCKED"), items[0], 0.7, 1.82, 7.0, 4.82, style, True)
        for number in range(1, 4):
            _add_tech_panel(slide, _chrome(style, f"执行 / 0{number}", f"EXEC / 0{number}"), _item_at(items, number), 8.05, 1.82 + (number - 1) * 1.62, 4.55, 1.28, style)
    else:
        for number in range(3):
            left = 0.7 + number * 4.18
            _add_tech_panel(slide, _chrome(style, f"信号 / 0{number + 1}", f"SIGNAL / 0{number + 1}"), _item_at(items, number), left, 2.0 + (number % 2) * 0.7, 3.65, 3.45, style, number == 0)
        _add_editorial_text(slide, _item_at(items, 3), 2.0, 6.2, 9.35, 0.42, style, 11, style.ACCENT_LIGHT, True, PP_ALIGN.CENTER)
    return slide


def _add_creative_block(
    slide, title, body, left, top, width, height, style, fill_color,
    inverted=True, body_font=17,
):
    block = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    block.fill.solid(); block.fill.fore_color.rgb = fill_color; block.line.fill.background()
    title_color = style.TEXT_WHITE if inverted else style.PRIMARY_COLOR
    body_color = style.TEXT_WHITE if inverted else style.TEXT_DARK
    if height <= 1.2:
        _add_editorial_text(slide, title, left + 0.32, top + 0.2, 2.0, height - 0.4, style, 11, title_color, True)
        _add_editorial_text(slide, body, left + 2.45, top + 0.16, width - 2.77, height - 0.32, style, 15, body_color, True)
    else:
        _add_editorial_text(slide, title, left + 0.32, top + 0.25, width - 0.64, 0.35, style, 12, title_color, True)
        _add_editorial_text(
            slide, body, left + 0.32, top + 0.72, width - 0.64,
            height - 0.87, style, body_font, body_color, True,
        )
    return block


def _render_slide_creative(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render creative slides with asymmetric editorial compositions."""
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = slide_data.get("narrative_role") or "opportunity_map"
    title = slide_data.get("title", f"第 {idx} 页")
    items = _commercial_slide_items(slide_data)
    add_page_number(slide, prs, idx + 1, total_slides, style)
    marker = slide.shapes.add_shape(1, Inches(0.72), Inches(0.48), Inches(0.1), Inches(0.72))
    marker.fill.solid(); marker.fill.fore_color.rgb = style.ACCENT_COLOR; marker.line.fill.background()
    _add_editorial_text(slide, title, 1.05, 0.42, 9.5, 0.72, style, 29, style.PRIMARY_COLOR, True)
    _add_editorial_text(slide, f"{idx:02d}", 11.25, 0.22, 1.2, 0.9, style, 38, style.ACCENT_LIGHT, True, PP_ALIGN.RIGHT)

    if role == "evidence_story":
        _add_editorial_text(slide, "事实先行，判断随后", 0.8, 1.42, 8.2, 0.6, style, 24, style.PRIMARY_COLOR, True)
        band_specs = [(0.8, 2.35, 11.8, style.PRIMARY_COLOR), (1.55, 3.65, 11.05, style.ACCENT_COLOR), (2.3, 4.95, 10.3, style.PRIMARY_DARK)]
        for number, (left, top, width, color) in enumerate(band_specs, 1):
            _add_creative_block(slide, _chrome(style, f"证据 / {number:02d}", f"EVIDENCE / {number:02d}"), items[number - 1] if len(items) >= number else items[-1], left, top, width, 1.05, style, color)
    elif role == "strategic_choice":
        _add_creative_block(slide, _chrome(style, "路径 A", "PATH / A"), items[0], 0.7, 1.6, 5.45, 3.15, style, style.PRIMARY_COLOR)
        _add_creative_block(slide, _chrome(style, "路径 B", "PATH / B"), items[1] if len(items) > 1 else items[0], 7.18, 1.6, 5.45, 3.15, style, style.ACCENT_COLOR)
        versus = slide.shapes.add_shape(9, Inches(6.0), Inches(2.68), Inches(1.0), Inches(1.0))
        versus.fill.solid(); versus.fill.fore_color.rgb = style.BG_WHITE; versus.line.color.rgb = style.PRIMARY_COLOR
        _add_editorial_text(slide, "VS", 6.0, 2.96, 1.0, 0.3, style, 14, style.PRIMARY_COLOR, True, PP_ALIGN.CENTER)
        _add_creative_block(slide, _chrome(style, "选择 / 推荐", "CHOICE / 推荐"), "；".join(items[2:]) or "优先验证价值更清晰的路径", 2.05, 5.18, 9.25, 1.12, style, style.PRIMARY_DARK)
    elif role == "execution_roadmap":
        stage_specs = [(0.75, 4.35, style.PRIMARY_COLOR), (4.88, 3.12, style.ACCENT_COLOR), (9.0, 1.9, style.PRIMARY_DARK)]
        connector_specs = [(4.3, 5.1, 4.88, 4.15), (8.43, 3.9, 9.0, 2.95)]
        for start_x, start_y, end_x, end_y in connector_specs:
            connector = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Inches(start_x), Inches(start_y), Inches(end_x), Inches(end_y),
            )
            connector.line.color.rgb = style.ACCENT_COLOR
            connector.line.width = Pt(2.5)
        for number, (left, top, color) in enumerate(stage_specs, 1):
            stage_name = ("试点", "扩展", "规模化")[number - 1]
            _add_creative_block(
                slide, f"0{number} / {stage_name}",
                items[number - 1] if len(items) >= number else items[-1],
                left, top, 3.55, 1.95, style, color, body_font=12,
            )
        _add_editorial_text(slide, "从左下到右上，逐级放大确定性", 0.78, 1.55, 6.8, 0.45, style, 16, style.TEXT_GRAY)
    elif role == "decision_close":
        _add_creative_block(slide, _chrome(style, "优先 / 01", "PRIORITY / 01"), items[0], 0.72, 1.55, 6.75, 4.75, style, style.PRIMARY_COLOR)
        _add_creative_block(slide, _chrome(style, "行动 / 02", "ACTION / 02"), items[1] if len(items) > 1 else items[0], 7.85, 1.55, 4.78, 2.1, style, style.ACCENT_COLOR)
        _add_creative_block(slide, _chrome(style, "行动 / 03", "ACTION / 03"), items[2] if len(items) > 2 else items[-1], 7.85, 4.18, 4.78, 2.12, style, style.PRIMARY_DARK)
        if len(items) > 3:
            _add_editorial_text(slide, items[3], 0.9, 5.7, 6.35, 0.42, style, 11, style.TEXT_WHITE, True)
    else:
        _add_creative_block(slide, _chrome(style, "信号 / 01", "SIGNAL / 01"), items[0], 0.72, 1.55, 5.35, 4.75, style, style.PRIMARY_COLOR)
        _add_creative_block(slide, _chrome(style, "信号 / 02", "SIGNAL / 02"), items[1] if len(items) > 1 else items[0], 6.42, 1.55, 6.2, 2.05, style, style.ACCENT_COLOR)
        _add_creative_block(slide, _chrome(style, "信号 / 03", "SIGNAL / 03"), items[2] if len(items) > 2 else items[-1], 7.15, 4.02, 5.47, 2.28, style, style.PRIMARY_DARK)

    sources = slide_data.get("evidence_sources", [])
    if sources:
        _add_editorial_text(slide, f"{_chrome(style, '来源', 'SOURCE')} / {sources[0].get('title', '公开资料')[:64]}", 0.72, 6.86, 10.2, 0.22, style, 8, style.TEXT_GRAY)
    return slide


def _render_slide_default(prs, blank_layout, style, slide_data, idx, total_slides):
    """Render semantic content with varied editorial compositions."""
    theme_renderers = {
        "academic": _render_slide_academic,
        "creative": _render_slide_creative,
        "education": _render_slide_education,
        "elegant": _render_slide_elegant,
        "medical": _render_slide_medical,
        "modern": _render_slide_modern,
        "minimal": _render_slide_minimal,
        "tech": _render_slide_tech,
    }
    theme_renderer = theme_renderers.get(style.template_name)
    if style.template_name == "modern" and slide_data.get("layout_variant", 0) > 0:
        return _render_slide_modern_variant(prs, blank_layout, style, slide_data, idx, total_slides)
    if theme_renderer:
        return theme_renderer(prs, blank_layout, style, slide_data, idx, total_slides)
    slide = prs.slides.add_slide(blank_layout)
    add_slide_background(slide, prs, style, light=True)
    role = _slide_role(slide_data)
    title = slide_data.get("title", f"第 {idx} 页")
    items = _commercial_slide_items(slide_data)
    add_page_number(slide, prs, idx + 1, total_slides, style)
    _add_editorial_text(slide, f"0{idx}", 0.6, 0.45, 0.55, 0.35, style, 12, style.ACCENT_COLOR, True)
    _add_editorial_text(slide, title, 1.25, 0.32, 10.8, 0.65, style, 27, style.PRIMARY_COLOR, True)
    sources = slide_data.get("evidence_sources", [])

    if role == "evidence_story":
        panel = slide.shapes.add_shape(5, Inches(0.65), Inches(1.45), Inches(2.75), Inches(4.95))
        panel.fill.solid(); panel.fill.fore_color.rgb = style.PRIMARY_COLOR; panel.line.fill.background()
        _add_editorial_text(slide, _chrome(style, "证据", "EVIDENCE"), 0.95, 1.85, 2.05, 0.3, style, 12, style.TEXT_WHITE, True)
        _add_editorial_text(slide, "01", 0.9, 2.4, 2.1, 0.9, style, 46, style.TEXT_WHITE, True)
        _add_editorial_text(slide, "从事实出发\n把变化转成判断", 0.95, 3.75, 1.95, 0.9, style, 17, style.TEXT_WHITE, True)
        _add_editorial_text(slide, "可验证  ·  可复核  ·  可追溯", 0.95, 5.45, 2.05, 0.3, style, 10, style.TEXT_WHITE, True)
        for number, item in enumerate(items[:3], 1):
            _add_editorial_card(slide, f"证据 {number:02d}", item, 3.8, 1.45 + (number - 1) * 1.55, 8.85, 1.22, style, style.ACCENT_COLOR)
        if len(items) > 3:
            _add_editorial_card(slide, "结论含义", items[3], 3.8, 6.0, 8.85, 0.75, style, style.PRIMARY_COLOR)
    elif role == "strategic_choice":
        _add_editorial_text(slide, "两条路径，一个明确选择", 0.65, 1.25, 8.5, 0.35, style, 15, style.TEXT_GRAY)
        _add_editorial_card(slide, "方案 A", items[0], 0.65, 1.9, 5.8, 2.45, style, style.PRIMARY_LIGHT)
        _add_editorial_card(slide, "方案 B", items[1] if len(items) > 1 else items[0], 6.85, 1.9, 5.8, 2.45, style, style.ACCENT_COLOR)
        _add_editorial_card(slide, "推荐路径", "；".join(items[2:]) or "优先验证价值更清晰、交付更可控的路径。", 0.65, 4.75, 12.0, 1.45, style, style.ACCENT_COLOR, filled=True)
    elif role == "execution_roadmap":
        _add_editorial_text(slide, "三个阶段，逐步验证，形成可复制交付", 0.65, 1.25, 11.7, 0.4, style, 15, style.TEXT_GRAY)
        stages = items[:3]
        for number, item in enumerate(stages, 1):
            left = 0.7 + (number - 1) * 4.15
            circle = slide.shapes.add_shape(9, Inches(left), Inches(2.0), Inches(0.62), Inches(0.62))
            circle.fill.solid(); circle.fill.fore_color.rgb = style.ACCENT_COLOR; circle.line.fill.background()
            _add_editorial_text(slide, str(number), left, 2.12, 0.62, 0.25, style, 14, style.TEXT_WHITE, True, PP_ALIGN.CENTER)
            if number < 3:
                connector = slide.shapes.add_shape(1, Inches(left + 0.62), Inches(2.29), Inches(3.53), Inches(0.04))
                connector.fill.solid(); connector.fill.fore_color.rgb = style.PRIMARY_LIGHT; connector.line.fill.background()
            stem = slide.shapes.add_shape(1, Inches(left + 0.29), Inches(2.62), Inches(0.04), Inches(0.33))
            stem.fill.solid(); stem.fill.fore_color.rgb = style.PRIMARY_LIGHT; stem.line.fill.background()
            _add_editorial_card(slide, ["试点", "扩展", "规模化"][number - 1], item, left - 0.1, 2.95, 3.65, 1.7, style, style.ACCENT_COLOR)
        _add_editorial_card(slide, "进入下一阶段的门槛", items[3] if len(items) > 3 else "核心指标达到目标，并完成复盘。", 2.1, 5.05, 9.15, 1.1, style, style.PRIMARY_COLOR)
    elif role == "decision_close":
        _add_editorial_text(slide, "把决定转成今天可执行的三个动作", 1.1, 1.45, 11.1, 0.65, style, 25, style.PRIMARY_COLOR, True, PP_ALIGN.CENTER)
        for number, item in enumerate(items[:3], 1):
            _add_editorial_card(slide, f"决策 {number:02d}", item, 0.75 + (number - 1) * 4.15, 2.65, 3.7, 2.05, style, style.ACCENT_COLOR)
        close_metric = items[3] if len(items) > 3 else "下一次评审以结果改善幅度决定是否扩大投入"
        _add_editorial_text(slide, close_metric, 2.0, 5.35, 9.4, 0.75, style, 13, style.TEXT_GRAY, False, PP_ALIGN.CENTER)
    else:
        _add_editorial_text(slide, "从市场变化中锁定最值得优先验证的机会", 0.65, 1.25, 11.7, 0.4, style, 15, style.TEXT_GRAY)
        local_images = slide_data.get("local_images", [])
        usable_image = local_images and Path(local_images[0]).exists()
        if usable_image:
            _add_cropped_picture(slide, local_images[0], 0.7, 1.95, 4.15, 3.75)
            for number, item in enumerate(items[:3], 1):
                _add_editorial_card(slide, f"机会 {number:02d}", item, 5.2, 1.95 + (number - 1) * 1.3, 7.45, 1.08, style, style.ACCENT_COLOR if number == 2 else style.PRIMARY_COLOR)
        else:
            for number, item in enumerate(items[:3], 1):
                _add_editorial_card(slide, f"机会 {number:02d}", item, 0.7 + (number - 1) * 4.15, 2.05, 3.65, 2.55, style, style.ACCENT_COLOR if number == 2 else style.PRIMARY_COLOR)
        _add_editorial_card(slide, "验证指标", items[3] if len(items) > 3 else "在明确周期内验证使用率与结果改善幅度。", 2.15, 4.85, 9.05, 1.05, style, style.PRIMARY_COLOR)

    if sources:
        source_title = sources[0].get("title", "网络检索来源")
        _add_editorial_text(slide, f"来源：{source_title[:72]}", 0.65, 6.88, 10.0, 0.22, style, 9, style.TEXT_GRAY)
