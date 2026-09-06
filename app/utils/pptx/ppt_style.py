"""
PPT 样式配置 - 共享模块

从 aiGeneratorPptx.py 提取，供 layout_decider.py 和其他模块使用，消除循环依赖。
"""

from copy import copy

from pptx.dml.color import RGBColor


# 与 aiGeneratorPptx.py 保持同步的模板定义
PPT_TEMPLATES = {
    "modern": {
        "name": "现代简约",
        "primary_color": "#2563eb",
        "secondary_color": "#64748b",
        "font_family": "Arial, sans-serif",
        "background": "#ffffff"
    },
    "business": {
        "name": "商务专业",
        "primary_color": "#1e40af",
        "secondary_color": "#475569",
        "font_family": "Georgia, serif",
        "background": "#f8fafc"
    },
    "creative": {
        "name": "创意设计",
        "primary_color": "#4c1d3d",
        "secondary_color": "#d95d55",
        "font_family": "Verdana, sans-serif",
        "background": "#fff8f1"
    },
    "minimal": {
        "name": "极简主义",
        "primary_color": "#000000",
        "secondary_color": "#6b7280",
        "font_family": "Helvetica, sans-serif",
        "background": "#ffffff"
    },
    "academic": {
        "name": "学术研究",
        "primary_color": "#0369a1",
        "secondary_color": "#0c4a6e",
        "font_family": "Times New Roman, serif",
        "background": "#f0f9ff"
    },
    "tech": {
        "name": "科技蓝调",
        "primary_color": "#3b82f6",
        "secondary_color": "#1d4ed8",
        "font_family": "Consolas, monospace",
        "background": "#0f172a"
    },
    "education": {
        "name": "教育培训",
        "primary_color": "#16a34a",
        "secondary_color": "#15803d",
        "font_family": "Aptos, Arial, sans-serif",
        "background": "#f0fdf4"
    },
    "medical": {
        "name": "医疗健康",
        "primary_color": "#059669",
        "secondary_color": "#047857",
        "font_family": "Arial, sans-serif",
        "background": "#ecfdf5"
    },
    "elegant": {
        "name": "优雅商务",
        "primary_color": "#7c3aed",
        "secondary_color": "#6d28d9",
        "font_family": "Georgia, serif",
        "background": "#f5f3ff"
    },
}

STYLE_TEMPLATE_ALIASES = {
    "business_report": "business",
    "pitch_deck": "creative",
}


def hex_to_rgb(hex_color: str) -> tuple:
    """将 hex 颜色字符串转为 (r, g, b) 元组"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


class PPTStyle:
    """PPT 样式配置"""
    def __init__(self, template_name="modern"):
        resolved_name = STYLE_TEMPLATE_ALIASES.get(template_name, template_name)
        tpl = PPT_TEMPLATES.get(resolved_name, PPT_TEMPLATES["modern"])
        self.template_name = resolved_name if resolved_name in PPT_TEMPLATES else "modern"

        pc = hex_to_rgb(tpl['primary_color'])
        sc = hex_to_rgb(tpl['secondary_color'])
        bg = hex_to_rgb(tpl['background'])

        self.PRIMARY_COLOR = RGBColor(*pc)
        self.PRIMARY_LIGHT = RGBColor(min(pc[0]+50, 255), min(pc[1]+50, 255), min(pc[2]+50, 255))
        self.PRIMARY_DARK = RGBColor(max(pc[0]-50, 0), max(pc[1]-50, 0), max(pc[2]-50, 0))

        self.ACCENT_COLOR = RGBColor(*sc) if self.template_name == "creative" else RGBColor(0xFF, 0x66, 0x00)
        self.ACCENT_LIGHT = RGBColor(0xED, 0xA5, 0x9F) if self.template_name == "creative" else RGBColor(0xFF, 0x99, 0x66)

        self.BG_WHITE = RGBColor(*bg)
        self.BG_LIGHT_BLUE = RGBColor(0xE8, 0xF4, 0xFC)
        self.BG_LIGHT_GRAY = RGBColor(0xF5, 0xF5, 0xF5)

        self.TEXT_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
        self.TEXT_DARK = RGBColor(0x33, 0x33, 0x33)
        self.TEXT_GRAY = RGBColor(0x66, 0x66, 0x66)

        self.FONT_MAIN = tpl['font_family'].split(',')[0].strip()
        self.FONT_TITLE = 'Arial'


def apply_design_tokens(style, tokens):
    """Overlay immutable design tokens onto the legacy renderer style."""
    def color(value, fallback):
        if not isinstance(value, str):
            return fallback
        value = value.lstrip("#")
        if len(value) != 6:
            return fallback
        return RGBColor.from_string(value.upper())

    token_style = copy(style)
    token_style.PRIMARY_COLOR = color(tokens.colors.get("primary"), style.PRIMARY_COLOR)
    token_style.PRIMARY_LIGHT = color(tokens.colors.get("secondary"), style.PRIMARY_LIGHT)
    token_style.PRIMARY_DARK = color(tokens.colors.get("secondary"), style.PRIMARY_DARK)
    token_style.ACCENT_COLOR = color(tokens.colors.get("accent"), style.ACCENT_COLOR)
    token_style.BG_WHITE = color(tokens.colors.get("background"), style.BG_WHITE)
    token_style.TEXT_DARK = color(tokens.colors.get("text"), style.TEXT_DARK)
    token_style.TEXT_GRAY = color(tokens.colors.get("muted_text"), style.TEXT_GRAY)
    token_style.FONT_MAIN = tokens.typography.get("body_font", style.FONT_MAIN)
    token_style.FONT_TITLE = tokens.typography.get("title_font", style.FONT_TITLE)
    return token_style
