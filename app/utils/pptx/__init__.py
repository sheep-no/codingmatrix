"""
PPT 工具包
"""
from app.utils.pptx.animation_engine import AnimationEngine, AnimationPresets, EntranceEffect, TransitionEffect
from app.utils.pptx.custom_template import CustomTemplateParser, TemplateConverter, TemplateValidator
from app.utils.pptx.image_upgrader import ImageCacheManager, ImageStrategy
from app.utils.pptx.layout_engine import LayoutOptimizer
from app.utils.pptx.ppt_style import PPT_TEMPLATES, PPTStyle, hex_to_rgb
from app.utils.pptx.templates import SlideLayout, TemplateCategory, TemplateConfig, TemplateManager

__all__ = [
    # 模板系统
    "TemplateManager",
    "TemplateConfig",
    "SlideLayout",
    "TemplateCategory",
    # 排版引擎
    "LayoutOptimizer",
    # 配图系统
    "ImageStrategy",
    "ImageCacheManager",
    # 自定义模板
    "CustomTemplateParser",
    "TemplateValidator",
    "TemplateConverter",
    # 动画系统
    "AnimationEngine",
    "AnimationPresets",
    "TransitionEffect",
    "EntranceEffect",
    # 样式配置
    "PPTStyle",
    "PPT_TEMPLATES",
    "hex_to_rgb",
]
