"""
PPT 模板管理器 - 注册、加载、推荐模板
"""
import os
import json
import logging
from typing import Dict, List, Optional, Type
from pathlib import Path

from app.utils.pptx.templates.base import TemplateBase, TemplateConfig, TemplateCategory

logger = logging.getLogger(__name__)


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
        return self._templates.get(template_id)

    def get_config(self, template_id: str) -> Optional[TemplateConfig]:
        """根据 ID 获取模板配置"""
        return self._template_configs.get(template_id)

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
                "primary_color": f"#{config.primary_color}",
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

    def _register_builtin_templates(self):
        """注册内置模板"""
        try:
            from app.utils.pptx.templates.presets import (
                BusinessReportTemplate,
                AcademicPresetTemplate,
                PitchDeckTemplate,
                EducationTemplate,
                MinimalTemplate,
            )

            presets = [
                BusinessReportTemplate(),
                AcademicPresetTemplate(),
                PitchDeckTemplate(),
                EducationTemplate(),
                MinimalTemplate(),
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

        data = {
            "template_id": config.template_id,
            "name": config.name,
            "name_zh": config.name_zh,
            "category": config.category.value,
            "description": config.description,
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
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"保存自定义模板：{template_id}")
        return template_id

    def load_custom_template(self, config_path: str) -> Optional[TemplateConfig]:
        """从文件加载自定义模板配置"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return TemplateConfig(
                template_id=data["template_id"],
                name=data["name"],
                name_zh=data["name_zh"],
                category=TemplateCategory(data["category"]),
                description=data["description"],
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
