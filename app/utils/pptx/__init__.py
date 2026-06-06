"""
PPT 工具包
"""
from app.utils.pptx.templates import TemplateManager, TemplateConfig, SlideLayout, TemplateCategory
from app.utils.pptx.layout_engine import LayoutOptimizer
from app.utils.pptx.image_upgrader import ImageStrategy, ImageCacheManager
from app.utils.pptx.custom_template import CustomTemplateParser, TemplateValidator, TemplateConverter
from app.utils.pptx.animation_engine import AnimationEngine, AnimationPresets, TransitionEffect, EntranceEffect
from app.utils.pptx.ppt_style import PPTStyle, PPT_TEMPLATES, hex_to_rgb

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
