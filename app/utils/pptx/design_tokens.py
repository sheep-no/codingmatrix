"""Resolve legacy template fields into one versioned design-token set."""

from dataclasses import asdict, dataclass
from typing import Any

from app.utils.pptx.templates.base import TemplateConfig


DESIGN_TOKEN_VERSION = "1.0"


@dataclass(frozen=True)
class DesignTokens:
    version: str
    colors: dict[str, Any]
    typography: dict[str, Any]
    spacing: dict[str, Any]
    shapes: dict[str, Any]
    image: dict[str, Any]
    chart: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_design_tokens(config: TemplateConfig, version: str | None = None) -> DesignTokens:
    """Build complete tokens while keeping existing TemplateConfig as source data."""
    colors = {
        "background": f"#{config.background_color.lstrip('#')}",
        "surface": f"#{config.background_color.lstrip('#')}",
        "primary": f"#{config.primary_color.lstrip('#')}",
        "secondary": f"#{config.secondary_color.lstrip('#')}",
        "accent": f"#{config.accent_color.lstrip('#')}",
        "text": f"#{config.text_color.lstrip('#')}",
        "muted_text": f"#{config.light_text_color.lstrip('#')}",
        "success": "#16A34A",
        "warning": "#D97706",
        "error": "#DC2626",
        "chart_series": [
            f"#{config.primary_color.lstrip('#')}",
            f"#{config.secondary_color.lstrip('#')}",
            f"#{config.accent_color.lstrip('#')}",
        ],
    }
    colors.update(config.colors)
    typography = {
        "title_font": config.title_font,
        "body_font": config.body_font,
        "title_font_en": config.title_font_en,
        "body_font_en": config.body_font_en,
        "title_size": max(24, config.title_size),
        "heading_size": max(20, config.heading_size),
        "body_size": max(14, config.body_size),
        "caption_size": config.caption_size,
        "title_weight": 700,
        "body_weight": 400,
        "line_spacing": config.line_spacing,
    }
    typography.update(config.typography)
    spacing = {
        "safe_margin": config.slide_margin,
        "grid_columns": 12,
        "grid_gutter": 0.2,
        "block_gap": config.paragraph_spacing,
        "title_margin_bottom": config.title_margin_bottom,
        "paragraph": config.paragraph_spacing,
        "bullet_indent": config.bullet_indent,
    }
    spacing.update(config.spacing)
    shapes = {
        "corner_radius": 0.12,
        "border_width": 1,
        "shadow": "subtle",
        "divider_width": 1,
        "icon_size": 0.3,
        "header_bar": config.has_header_bar,
        "footer_bar": config.has_footer_bar,
    }
    shapes.update(config.shapes)
    image = {
        "fit": "contain",
        "crop_focus": "center",
        "corner_radius": 0.12,
        "mask": "none",
        "tone": "natural",
        "credit_position": "bottom_right",
    }
    image.update(config.image)
    chart = {
        "axis_color": f"#{config.light_text_color.lstrip('#')}",
        "grid_color": f"#{config.light_text_color.lstrip('#')}",
        "legend_position": "bottom",
        "show_labels": True,
        "show_source": True,
        "source_style": "caption",
    }
    chart.update(config.chart)
    return DesignTokens(
        version=version or config.version or DESIGN_TOKEN_VERSION,
        colors=colors,
        typography=typography,
        spacing=spacing,
        shapes=shapes,
        image=image,
        chart=chart,
    )
