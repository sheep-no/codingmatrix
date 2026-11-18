"""
视觉模块 - 多模态 AI 视觉决策与布局规划

包含：
- visual_analyzer: 视觉分析器，分析内容并决策图片需求
- image_manager: 图片管理器，生成/搜索/缓存图片
- layout_decider: 布局决策器，生成 python-pptx 渲染指令
"""

from app.utils.visual.image_manager import ImageAsset, ImageManager, ImageSource, image_manager
from app.utils.visual.layout_decider import LayoutDecider, LayoutElement, LayoutType, SlideLayoutPlan, layout_decider
from app.utils.visual.visual_analyzer import (
    ImagePosition,
    ImageType,
    PPTVisualPlan,
    SlideVisualDecision,
    VisualAnalyzer,
    visual_analyzer,
)

__all__ = [
    # Visual Analyzer
    "VisualAnalyzer",
    "visual_analyzer",
    "SlideVisualDecision",
    "PPTVisualPlan",
    "ImageType",
    "ImagePosition",
    # Image Manager
    "ImageManager",
    "image_manager",
    "ImageAsset",
    "ImageSource",
    # Layout Decider
    "LayoutDecider",
    "layout_decider",
    "LayoutType",
    "LayoutElement",
    "SlideLayoutPlan",
]