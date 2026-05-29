"""
PPT 模板引擎系统

提供专业 PPT 模板管理能力，支持：
- 多模板注册和切换
- 模板动态加载
- 布局变体
- 智能模板推荐
"""

from app.utils.pptx.templates.base import TemplateConfig, SlideLayout, TemplateBase, TemplateCategory
from app.utils.pptx.templates.manager import TemplateManager

__all__ = [
    "TemplateConfig",
    "SlideLayout",
    "TemplateBase",
    "TemplateManager",
    "TemplateCategory",
]
