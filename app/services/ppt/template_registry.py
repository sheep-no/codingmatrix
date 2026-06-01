"""
PPT 模板注册表

统一管理前后端模板配置，支持：
- 从 YAML 文件加载模板配置
- 热重载配置变更
- 注册自定义模板
- 查询模板信息
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any

import yaml

logger = logging.getLogger(__name__)

# 默认配置文件路径
DEFAULT_CONFIG_PATH = Path("./config/ppt/templates.yaml")


@dataclass
class TemplateConfig:
    """单个模板配置"""
    id: str
    name: str
    name_en: str
    description: str
    category: str
    colors: Dict[str, str]
    fonts: Dict[str, Any]
    layouts: List[str]
    animations: Dict[str, Any]
    thumbnail: str = ""
    is_default: bool = False
    is_custom: bool = False
    created_by: Optional[str] = None


@dataclass
class TemplateInfo:
    """模板简要信息（用于列表展示）"""
    id: str
    name: str
    name_en: str
    description: str
    category: str
    thumbnail: str
    is_default: bool
    is_custom: bool


@dataclass
class PPTSettings:
    """全局设置"""
    default_template: str = "modern"
    animation_duration: float = 0.5
    animation_delay: float = 0.1
    slide_width: float = 10.0
    slide_height: float = 7.5
    margin: float = 0.5
    max_title_length: int = 50
    max_content_lines: int = 8
    min_font_size: int = 12
    max_font_size: int = 48
    image_default_width: int = 1920
    image_default_height: int = 1080
    image_download_timeout: int = 10
    image_max_concurrent: int = 5


class TemplateRegistryError(Exception):
    """模板注册表异常"""
    pass


class TemplateRegistry:
    """
    PPT 模板注册表
    
    负责管理和提供统一的模板配置，消除前后端模板名称不匹配问题。
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._templates: Dict[str, TemplateConfig] = {}
        self._settings = PPTSettings()
        self._last_modified: float = 0.0
        self._watcher_task = None
    
    def load(self, config_path: Optional[Path] = None) -> None:
        """
        从 YAML 文件加载模板配置
        
        Args:
            config_path: 配置文件路径，不传则使用默认路径
        
        Raises:
            TemplateRegistryError: 配置加载失败
        """
        path = config_path or self._config_path
        
        if not path.exists():
            logger.warning(f"配置文件不存在：{path}，使用内置默认配置")
            self._load_defaults()
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self._parse_config(config)
            self._last_modified = path.stat().st_mtime
            
            logger.info(f"加载模板配置成功 | path={path} | templates={len(self._templates)}")
            
        except yaml.YAMLError as e:
            logger.error(f"YAML 解析失败：{e}")
            raise TemplateRegistryError(f"配置文件格式错误：{e}")
        except Exception as e:
            logger.error(f"加载配置失败：{e}")
            raise TemplateRegistryError(f"加载配置失败：{e}")
    
    def get_template(self, template_id: str) -> TemplateConfig:
        """
        获取指定模板配置
        
        Args:
            template_id: 模板 ID
        
        Returns:
            模板配置对象
        
        Raises:
            TemplateRegistryError: 模板不存在
        """
        if template_id not in self._templates:
            # 回退到默认模板
            if self._settings.default_template in self._templates:
                logger.warning(f"模板不存在：{template_id}，使用默认模板：{self._settings.default_template}")
                return self._templates[self._settings.default_template]
            raise TemplateRegistryError(f"模板不存在：{template_id}")
        
        return self._templates[template_id]
    
    def list_templates(self, category: Optional[str] = None) -> List[TemplateInfo]:
        """
        列出所有可用模板
        
        Args:
            category: 按类别过滤（如 "business", "tech" 等）
        
        Returns:
            模板信息列表
        """
        templates = list(self._templates.values())
        
        if category:
            templates = [t for t in templates if t.category == category]
        
        # 按是否默认排序（默认模板排前面）
        templates.sort(key=lambda t: (not t.is_default, t.name))
        
        return [
            TemplateInfo(
                id=t.id,
                name=t.name,
                name_en=t.name_en,
                description=t.description,
                category=t.category,
                thumbnail=t.thumbnail,
                is_default=t.is_default,
                is_custom=t.is_custom,
            )
            for t in templates
        ]
    
    def register_custom(
        self,
        template_id: str,
        name: str,
        colors: Dict[str, str],
        fonts: Dict[str, Any],
        created_by: Optional[str] = None,
    ) -> str:
        """
        注册自定义模板
        
        Args:
            template_id: 模板 ID
            name: 模板名称
            colors: 颜色配置
            fonts: 字体配置
            created_by: 创建者
        
        Returns:
            模板 ID
        """
        if template_id in self._templates:
            raise TemplateRegistryError(f"模板 ID 已存在：{template_id}")
        
        template = TemplateConfig(
            id=template_id,
            name=name,
            name_en=name,
            description=f"自定义模板：{name}",
            category="custom",
            colors=colors,
            fonts=fonts,
            layouts=["title_slide", "content_with_image", "bullet_list"],
            animations={"default": "fade", "supported": ["fade"]},
            is_custom=True,
            created_by=created_by,
        )
        
        self._templates[template_id] = template
        logger.info(f"注册自定义模板 | id={template_id} | creator={created_by}")
        
        return template_id
    
    def hot_reload(self) -> None:
        """
        热重载配置文件
        
        检测配置文件变更并重新加载。
        """
        if not self._config_path.exists():
            return
        
        current_mtime = self._config_path.stat().st_mtime
        
        if current_mtime > self._last_modified:
            logger.info(f"检测到配置变更，热重载中...")
            self.load()
            logger.info(f"配置热重载完成 | templates={len(self._templates)}")
    
    def get_settings(self) -> PPTSettings:
        """获取全局设置"""
        return self._settings
    
    def get_categories(self) -> List[str]:
        """获取所有模板类别"""
        categories = set(t.category for t in self._templates.values())
        return sorted(categories)
    
    def _parse_config(self, config: Dict[str, Any]) -> None:
        """解析配置字典"""
        # 清空现有模板
        self._templates.clear()
        
        # 解析模板
        templates_data = config.get("templates", {})
        for template_id, data in templates_data.items():
            try:
                template = self._parse_template(template_id, data)
                self._templates[template_id] = template
            except Exception as e:
                logger.error(f"解析模板失败：{template_id} | error={e}")
        
        # 解析全局设置
        settings_data = config.get("settings", {})
        self._parse_settings(settings_data)
    
    def _parse_template(self, template_id: str, data: Dict[str, Any]) -> TemplateConfig:
        """解析单个模板配置"""
        return TemplateConfig(
            id=template_id,
            name=data.get("name", template_id),
            name_en=data.get("name_en", template_id),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            colors=data.get("colors", {}),
            fonts=data.get("fonts", {}),
            layouts=data.get("layouts", []),
            animations=data.get("animations", {}),
            thumbnail=data.get("thumbnail", ""),
            is_default=data.get("is_default", False),
        )
    
    def _parse_settings(self, data: Dict[str, Any]) -> None:
        """解析全局设置"""
        self._settings.default_template = data.get("default_template", "modern")
        
        animations = data.get("animations", {})
        self._settings.animation_duration = animations.get("duration", 0.5)
        self._settings.animation_delay = animations.get("delay", 0.1)
        
        layouts = data.get("layouts", {})
        self._settings.slide_width = layouts.get("slide_width", 10.0)
        self._settings.slide_height = layouts.get("slide_height", 7.5)
        self._settings.margin = layouts.get("margin", 0.5)
        
        text = data.get("text", {})
        self._settings.max_title_length = text.get("max_title_length", 50)
        self._settings.max_content_lines = text.get("max_content_lines", 8)
        self._settings.min_font_size = text.get("min_font_size", 12)
        self._settings.max_font_size = text.get("max_font_size", 48)
        
        images = data.get("images", {})
        self._settings.image_default_width = images.get("default_width", 1920)
        self._settings.image_default_height = images.get("default_height", 1080)
        self._settings.image_download_timeout = images.get("download_timeout", 10)
        self._settings.image_max_concurrent = images.get("max_concurrent", 5)
    
    def _load_defaults(self) -> None:
        """加载内置默认配置"""
        default_templates = {
            "modern": TemplateConfig(
                id="modern",
                name="现代简约",
                name_en="Modern Minimal",
                description="简洁清晰的现代风格",
                category="general",
                colors={
                    "primary": "#2563eb",
                    "secondary": "#64748b",
                    "accent": "#3b82f6",
                    "background": "#ffffff",
                    "text": "#1e293b",
                },
                fonts={
                    "title": "Arial, sans-serif",
                    "body": "Arial, sans-serif",
                    "title_size": 32,
                    "body_size": 18,
                },
                layouts=["title_slide", "content_with_image", "bullet_list"],
                animations={"default": "fade", "supported": ["fade", "slide_left", "slide_right", "zoom"]},
                is_default=True,
            ),
            "business": TemplateConfig(
                id="business",
                name="商务专业",
                name_en="Business Professional",
                description="稳重大气的商务风格",
                category="business",
                colors={
                    "primary": "#1e40af",
                    "secondary": "#475569",
                    "accent": "#3b82f6",
                    "background": "#f8fafc",
                    "text": "#0f172a",
                },
                fonts={
                    "title": "Georgia, serif",
                    "body": "Georgia, serif",
                    "title_size": 34,
                    "body_size": 18,
                },
                layouts=["title_slide", "content_with_image", "data_chart"],
                animations={"default": "fade", "supported": ["fade", "slide_up"]},
            ),
        }
        
        self._templates = default_templates
        self._settings = PPTSettings()
        
        logger.info(f"使用内置默认配置 | templates={len(self._templates)}")


# 全局单例
template_registry = TemplateRegistry()
