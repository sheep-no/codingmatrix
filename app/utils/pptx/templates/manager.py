"""
PPT 模板管理器 - 注册、加载、推荐模板
"""
import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.utils.pptx.templates.base import TemplateBase, TemplateConfig, TemplateCategory
from app.utils.pptx.design_tokens import DesignTokens, resolve_design_tokens
from app.utils.pptx.scenario import SCENARIO_PROFILES, ScenarioResult, classify_scenario

logger = logging.getLogger(__name__)

TEMPLATE_ALIASES = {
    "business": "business_report",
    "creative": "pitch_deck",
}

SCENARIO_TEMPLATE_RANKINGS = {
    "business": ("business_report", "minimal", "tech"),
    "data_report": ("tech", "business_report", "minimal"),
    "product_pitch": ("pitch_deck", "tech", "minimal"),
    "academic": ("academic", "minimal", "tech"),
    "education": ("education", "minimal", "business_report"),
    "general": ("minimal", "business_report", "education"),
}


def migrate_legacy_template_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Add versioned token containers to legacy custom-template JSON."""
    migrated = dict(data)
    migrated.setdefault("schema_version", 2)
    migrated.setdefault("version", "1.0")
    for group in ("colors", "typography", "spacing", "shapes", "image", "chart"):
        migrated.setdefault(group, {})
    return migrated


class TemplateManager:
    """PPT 模板管理器"""

    def __init__(self, template_dir: Optional[str] = None):
        self._templates: Dict[str, TemplateBase] = {}
        self._template_configs: Dict[str, TemplateConfig] = {}

        if template_dir is None:
            self._template_dir = Path(__file__).parent / "presets"
        else:
            self._template_dir = Path(template_dir)

        self._register_builtin_templates()

    def register(self, template: TemplateBase):
        """注册一个模板"""
        config = template.config
        if config.template_id in self._templates:
            raise ValueError(f"模板已存在：{config.template_id}")

        self._templates[config.template_id] = template
        self._template_configs[config.template_id] = config
        logger.info(f"注册模板：{config.name_zh} ({config.template_id})")

    def get_template(self, template_id: str) -> Optional[TemplateBase]:
        """根据 ID 获取模板"""
        return self._templates.get(TEMPLATE_ALIASES.get(template_id, template_id))

    def get_config(self, template_id: str) -> Optional[TemplateConfig]:
        """根据 ID 获取模板配置"""
        return self._template_configs.get(TEMPLATE_ALIASES.get(template_id, template_id))

    def resolve_design_tokens(self, template_id: str, version: Optional[str] = None) -> DesignTokens:
        """Resolve one token bundle for every page in a generation task."""
        config = self.get_config(template_id)
        if config is None:
            raise KeyError(f"模板不存在：{template_id}")
        return resolve_design_tokens(config, version)

    def list_templates(self) -> List[Dict]:
        """列出所有可用模板"""
        result = []
        for tid, config in self._template_configs.items():
            result.append({
                "id": tid,
                "name": config.name,
                "name_zh": config.name_zh,
                "category": config.category.value,
                "description": config.description,
                "version": config.version,
                "primary_color": f"#{config.primary_color}",
                "secondary_color": f"#{config.secondary_color}",
                "background": f"#{config.background_color}",
                "has_header_bar": config.has_header_bar,
                "has_page_number": config.has_page_number,
            })
        return result

    def recommend_template(
        self,
        category: Optional[TemplateCategory] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[str]:
        """推荐合适的的模板"""
        if category:
            candidates = [
                tid for tid, cfg in self._template_configs.items()
                if cfg.category == category
            ]
        else:
            candidates = list(self._template_configs.keys())

        # 如果有关键字，尝试匹配
        if keywords:
            scored = []
            for tid in candidates:
                config = self._template_configs[tid]
                score = 0
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower in config.description.lower():
                        score += 2
                    if kw_lower in config.name.lower():
                        score += 1
                scored.append((score, tid))
            candidates = [tid for _, tid in sorted(scored, reverse=True)]

        return candidates[:5]  # 最多推荐 5 个

    def recommend_for_scenario(
        self,
        text: str = "",
        limit: int = 3,
        scenario: Optional[str] = None,
    ) -> Dict[str, object]:
        """Return a scenario result and stable ranked template candidates."""
        if scenario in SCENARIO_PROFILES:
            result = ScenarioResult(scenario, SCENARIO_PROFILES[scenario][0], 1.0, ())
        else:
            result = classify_scenario(text)
        preferred = list(SCENARIO_TEMPLATE_RANKINGS[result.scenario])
        ranked_ids = preferred + [template_id for template_id in self._template_configs if template_id not in preferred]
        ranked_ids = ranked_ids[:max(3, min(limit, len(ranked_ids)))]
        candidates = []
        for rank, template_id in enumerate(ranked_ids):
            config = self._template_configs[template_id]
            candidates.append({
                "id": template_id,
                "name": config.name_zh,
                "category": config.category.value,
                "version": config.version,
                "score": max(0, 100 - rank * 10),
                "preview": {
                    "primary_color": f"#{config.primary_color.lstrip('#')}",
                    "secondary_color": f"#{config.secondary_color.lstrip('#')}",
                    "background": f"#{config.background_color.lstrip('#')}",
                },
            })
        return {
            "scenario": result.scenario,
            "confidence": result.confidence,
            "matched_keywords": list(result.matched_keywords),
            "templates": [candidate["id"] for candidate in candidates],
            "candidates": candidates,
        }

    def _register_builtin_templates(self):
        """注册内置模板"""
        try:
            from app.utils.pptx.templates.presets import (
                BusinessReportTemplate,
                AcademicPresetTemplate,
                PitchDeckTemplate,
                EducationTemplate,
                ElegantTemplate,
                MedicalTemplate,
                MinimalTemplate,
                ModernTemplate,
                TechTemplate,
            )

            presets = [
                BusinessReportTemplate(),
                AcademicPresetTemplate(),
                PitchDeckTemplate(),
                EducationTemplate(),
                ElegantTemplate(),
                MedicalTemplate(),
                MinimalTemplate(),
                ModernTemplate(),
                TechTemplate(),
            ]

            for preset in presets:
                self.register(preset)

            logger.info(f"注册 {len(presets)} 个内置模板")
        except Exception as e:
            logger.warning(f"加载内置模板失败：{e}")

    def save_custom_template(self, config: TemplateConfig) -> str:
        """保存自定义模板配置"""
        template_id = config.template_id
        config_path = self._template_dir / f"{template_id}.json"

        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        tokens = resolve_design_tokens(config)
        data = {
            "template_id": config.template_id,
            "name": config.name,
            "name_zh": config.name_zh,
            "category": config.category.value,
            "description": config.description,
            "schema_version": config.schema_version,
            "version": config.version,
            "primary_color": config.primary_color,
            "secondary_color": config.secondary_color,
            "accent_color": config.accent_color,
            "background_color": config.background_color,
            "text_color": config.text_color,
            "light_text_color": config.light_text_color,
            "title_font": config.title_font,
            "body_font": config.body_font,
            "title_font_en": config.title_font_en,
            "body_font_en": config.body_font_en,
            "title_size": config.title_size,
            "subtitle_size": config.subtitle_size,
            "heading_size": config.heading_size,
            "body_size": config.body_size,
            "bullet_size": config.bullet_size,
            "caption_size": config.caption_size,
            "slide_margin": config.slide_margin,
            "title_margin_bottom": config.title_margin_bottom,
            "paragraph_spacing": config.paragraph_spacing,
            "bullet_indent": config.bullet_indent,
            "line_spacing": config.line_spacing,
            "has_header_bar": config.has_header_bar,
            "has_footer_bar": config.has_footer_bar,
            "has_corner_decor": config.has_corner_decor,
            "has_page_number": config.has_page_number,
            "colors": tokens.colors,
            "typography": tokens.typography,
            "spacing": tokens.spacing,
            "shapes": tokens.shapes,
            "image": tokens.image,
            "chart": tokens.chart,
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"保存自定义模板：{template_id}")
        return template_id

    def load_custom_template(self, config_path: str) -> Optional[TemplateConfig]:
        """从文件加载自定义模板配置"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = migrate_legacy_template_data(json.load(f))

            return TemplateConfig(
                template_id=data["template_id"],
                name=data["name"],
                name_zh=data["name_zh"],
                category=TemplateCategory(data["category"]),
                description=data["description"],
                schema_version=data["schema_version"],
                version=data["version"],
                primary_color=data.get("primary_color", "1F4E79"),
                secondary_color=data.get("secondary_color", "2E75B6"),
                accent_color=data.get("accent_color", "70AD47"),
                background_color=data.get("background_color", "FFFFFF"),
                text_color=data.get("text_color", "333333"),
                light_text_color=data.get("light_text_color", "666666"),
                title_font=data.get("title_font", "微软雅黑"),
                body_font=data.get("body_font", "微软雅黑"),
                title_font_en=data.get("title_font_en", "Arial"),
                body_font_en=data.get("body_font_en", "Calibri"),
                title_size=data.get("title_size", 32),
                subtitle_size=data.get("subtitle_size", 20),
                heading_size=data.get("heading_size", 24),
                body_size=data.get("body_size", 16),
                bullet_size=data.get("bullet_size", 14),
                caption_size=data.get("caption_size", 12),
                slide_margin=data.get("slide_margin", 0.8),
                title_margin_bottom=data.get("title_margin_bottom", 0.4),
                paragraph_spacing=data.get("paragraph_spacing", 0.15),
                bullet_indent=data.get("bullet_indent", 0.3),
                line_spacing=data.get("line_spacing", 1.3),
                has_header_bar=data.get("has_header_bar", True),
                has_footer_bar=data.get("has_footer_bar", True),
                has_corner_decor=data.get("has_corner_decor", False),
                has_page_number=data.get("has_page_number", True),
                colors=data["colors"],
                typography=data["typography"],
                spacing=data["spacing"],
                shapes=data["shapes"],
                image=data["image"],
                chart=data["chart"],
            )
        except Exception as e:
            logger.error(f"加载自定义模板失败：{e}")
            return None

    def apply_template_from_config(self, prs, config: TemplateConfig):
        """根据模板配置设置幻灯片尺寸和基本配置"""
        from pptx.util import Inches

        # 设置幻灯片尺寸
        prs.slide_width = Inches(config.slide_width)
        prs.slide_height = Inches(config.slide_height)

        # 设置主题颜色
        # python-pptx 主题设置较复杂，这里简化处理
