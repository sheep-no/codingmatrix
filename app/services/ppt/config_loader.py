"""
PPT 配置加载器

负责加载和管理 PPT 相关的配置文件：
- 从 YAML 文件加载全局设置
- 合并模板配置和全局设置
- 提供热重载机制
- 处理配置缺失时的默认值
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml

logger = logging.getLogger(__name__)

# 默认配置文件路径
DEFAULT_SETTINGS_PATH = Path("./config/ppt/settings.yaml")
DEFAULT_TEMPLATES_PATH = Path("./config/ppt/templates.yaml")


@dataclass
class ServiceConfig:
    """服务配置"""
    output_dir: str = "./pptx_output"
    static_dir: str = "./static/ppt"
    image_cache_dir: str = "./static/images/ppt-cache"
    temp_dir: str = "./tmp/ppt"


@dataclass
class TaskQueueConfig:
    """任务队列配置"""
    max_concurrent_tasks: int = 10
    max_concurrent_per_user: int = 3
    task_timeout_seconds: int = 300
    task_retention_days: int = 7


@dataclass
class AIConfig:
    """AI 模型配置"""
    default_model: str = "Qwen/Qwen3.5-4B"
    max_retries: int = 3
    temperature: float = 0.7
    outline_model: str = "Qwen/Qwen3.5-4B"
    content_model: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    polish_model: str = "Qwen/Qwen3.5-4B"
    design_model: str = "Qwen/Qwen3.5-4B"


@dataclass
class SlidesConfig:
    """幻灯片配置"""
    default_count: int = 10
    min_count: int = 5
    max_count: int = 50
    width: float = 10.0
    height: float = 7.5
    default_layout: str = "blank"


@dataclass
class TextConfig:
    """文本配置"""
    max_title_length: int = 50
    max_content_lines: int = 8
    max_chars_per_line_cn: int = 25
    max_chars_per_line_en: int = 50
    min_font_size: int = 12
    max_font_size: int = 48
    default_title_size: int = 32
    default_body_size: int = 18
    font_size_step: int = 2


@dataclass
class ImagesConfig:
    """图片配置"""
    search_sources: List[str] = field(default_factory=lambda: ["bing", "unsplash", "pexels"])
    max_concurrent_search: int = 5
    download_timeout: int = 10
    default_width: int = 1920
    default_height: int = 1080
    cache_ttl: int = 604800
    max_cache_size_mb: int = 500


@dataclass
class AnimationConfig:
    """动画配置"""
    default_enabled: bool = False
    default_animation: str = "fade"
    duration: float = 0.5
    delay: float = 0.1
    supported_animations: List[str] = field(default_factory=lambda: [
        "fade", "slide_left", "slide_right", "slide_up", 
        "slide_down", "zoom", "bounce"
    ])


@dataclass
class ExportConfig:
    """导出配置"""
    pdf_enabled: bool = True
    libreoffice_path: str = "libreoffice"
    conversion_timeout: int = 60


@dataclass
class StorageConfig:
    """存储配置"""
    file_retention_days: int = 7
    max_total_size_gb: float = 10.0
    threshold_percentage: float = 80


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    verbose: bool = False


class PPTConfig:
    """
    PPT 全局配置
    
    包含所有配置项的聚合类。
    """
    
    def __init__(self):
        self.service = ServiceConfig()
        self.task_queue = TaskQueueConfig()
        self.ai = AIConfig()
        self.slides = SlidesConfig()
        self.text = TextConfig()
        self.images = ImagesConfig()
        self.animations = AnimationConfig()
        self.export = ExportConfig()
        self.storage = StorageConfig()
        self.logging = LoggingConfig()


class ConfigLoaderError(Exception):
    """配置加载异常"""
    pass


class ConfigLoader:
    """
    PPT 配置加载器
    
    负责从 YAML 文件加载配置，并提供热重载功能。
    """
    
    def __init__(
        self,
        settings_path: Optional[Path] = None,
        templates_path: Optional[Path] = None,
    ):
        self._settings_path = settings_path or DEFAULT_SETTINGS_PATH
        self._templates_path = templates_path or DEFAULT_TEMPLATES_PATH
        
        self._config = PPTConfig()
        self._templates: Dict[str, Any] = {}
        self._last_modified_settings: float = 0.0
        self._last_modified_templates: float = 0.0
    
    @property
    def config(self) -> PPTConfig:
        """获取当前配置"""
        return self._config
    
    @property
    def templates(self) -> Dict[str, Any]:
        """获取模板配置"""
        return self._templates
    
    def load(self) -> None:
        """
        加载所有配置文件
        
        Raises:
            ConfigLoaderError: 加载失败
        """
        self._load_settings()
        self._load_templates()
        
        # 确保必要的目录存在
        self._ensure_directories()
        
        logger.info(f"配置加载完成 | settings={self._settings_path} | templates={self._templates_path}")
    
    def hot_reload(self) -> bool:
        """
        热重载配置文件
        
        Returns:
            是否有配置变更
        """
        has_changes = False
        
        # 检查设置文件
        if self._settings_path.exists():
            current_mtime = self._settings_path.stat().st_mtime
            if current_mtime > self._last_modified_settings:
                logger.info("检测到设置文件变更，热重载中...")
                self._load_settings()
                has_changes = True
        
        # 检查模板文件
        if self._templates_path.exists():
            current_mtime = self._templates_path.stat().st_mtime
            if current_mtime > self._last_modified_templates:
                logger.info("检测到模板文件变更，热重载中...")
                self._load_templates()
                has_changes = True
        
        if has_changes:
            self._ensure_directories()
            logger.info("配置热重载完成")
        
        return has_changes
    
    def get_setting(self, section: str, key: str, default: Any = None) -> Any:
        """
        获取指定配置项
        
        Args:
            section: 配置节（如 "service", "ai"）
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        try:
            section_obj = getattr(self._config, section)
            return getattr(section_obj, key, default)
        except AttributeError:
            return default
    
    def set_setting(self, section: str, key: str, value: Any) -> None:
        """
        设置配置项（运行时覆盖）
        
        Args:
            section: 配置节
            key: 配置键
            value: 配置值
        """
        try:
            section_obj = getattr(self._config, section)
            setattr(section_obj, key, value)
        except AttributeError:
            logger.warning(f"配置节不存在：{section}")
    
    def _load_settings(self) -> None:
        """加载全局设置"""
        if not self._settings_path.exists():
            logger.warning(f"设置文件不存在：{self._settings_path}，使用默认配置")
            self._last_modified_settings = 0.0
            return
        
        try:
            with open(self._settings_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            self._parse_settings(data)
            self._last_modified_settings = self._settings_path.stat().st_mtime
            
        except yaml.YAMLError as e:
            logger.error(f"设置文件解析失败：{e}")
            # 使用默认配置
        except Exception as e:
            logger.error(f"加载设置文件失败：{e}")
            raise ConfigLoaderError(f"加载设置文件失败：{e}")
    
    def _load_templates(self) -> None:
        """加载模板配置"""
        if not self._templates_path.exists():
            logger.warning(f"模板文件不存在：{self._templates_path}")
            self._last_modified_templates = 0.0
            return
        
        try:
            with open(self._templates_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            self._templates = data.get("templates", {})
            self._last_modified_templates = self._templates_path.stat().st_mtime
            
        except Exception as e:
            logger.error(f"加载模板文件失败：{e}")
            self._templates = {}
    
    def _parse_settings(self, data: Dict[str, Any]) -> None:
        """解析设置配置"""
        if not data:
            return
        
        # 服务设置
        service_data = data.get("service", {})
        self._config.service = ServiceConfig(
            output_dir=service_data.get("output_dir", self._config.service.output_dir),
            static_dir=service_data.get("static_dir", self._config.service.static_dir),
            image_cache_dir=service_data.get("image_cache_dir", self._config.service.image_cache_dir),
            temp_dir=service_data.get("temp_dir", self._config.service.temp_dir),
        )
        
        # 任务队列设置
        task_data = data.get("task_queue", {})
        self._config.task_queue = TaskQueueConfig(
            max_concurrent_tasks=task_data.get("max_concurrent_tasks", self._config.task_queue.max_concurrent_tasks),
            max_concurrent_per_user=task_data.get("max_concurrent_per_user", self._config.task_queue.max_concurrent_per_user),
            task_timeout_seconds=task_data.get("task_timeout_seconds", self._config.task_queue.task_timeout_seconds),
            task_retention_days=task_data.get("task_retention_days", self._config.task_queue.task_retention_days),
        )
        
        # AI 设置
        ai_data = data.get("ai", {})
        self._config.ai = AIConfig(
            default_model=ai_data.get("default_model", self._config.ai.default_model),
            max_retries=ai_data.get("max_retries", self._config.ai.max_retries),
            temperature=ai_data.get("temperature", self._config.ai.temperature),
            outline_model=ai_data.get("outline_model", self._config.ai.outline_model),
            content_model=ai_data.get("content_model", self._config.ai.content_model),
            polish_model=ai_data.get("polish_model", self._config.ai.polish_model),
            design_model=ai_data.get("design_model", self._config.ai.design_model),
        )
        
        # 幻灯片设置
        slides_data = data.get("slides", {})
        self._config.slides = SlidesConfig(
            default_count=slides_data.get("default_count", self._config.slides.default_count),
            min_count=slides_data.get("min_count", self._config.slides.min_count),
            max_count=slides_data.get("max_count", self._config.slides.max_count),
            width=slides_data.get("width", self._config.slides.width),
            height=slides_data.get("height", self._config.slides.height),
            default_layout=slides_data.get("default_layout", self._config.slides.default_layout),
        )
        
        # 文本设置
        text_data = data.get("text", {})
        self._config.text = TextConfig(
            max_title_length=text_data.get("max_title_length", self._config.text.max_title_length),
            max_content_lines=text_data.get("max_content_lines", self._config.text.max_content_lines),
            max_chars_per_line_cn=text_data.get("max_chars_per_line_cn", self._config.text.max_chars_per_line_cn),
            max_chars_per_line_en=text_data.get("max_chars_per_line_en", self._config.text.max_chars_per_line_en),
            min_font_size=text_data.get("min_font_size", self._config.text.min_font_size),
            max_font_size=text_data.get("max_font_size", self._config.text.max_font_size),
            default_title_size=text_data.get("default_title_size", self._config.text.default_title_size),
            default_body_size=text_data.get("default_body_size", self._config.text.default_body_size),
            font_size_step=text_data.get("font_size_step", self._config.text.font_size_step),
        )
        
        # 图片设置
        images_data = data.get("images", {})
        self._config.images = ImagesConfig(
            search_sources=images_data.get("search_sources", self._config.images.search_sources),
            max_concurrent_search=images_data.get("max_concurrent_search", self._config.images.max_concurrent_search),
            download_timeout=images_data.get("download_timeout", self._config.images.download_timeout),
            default_width=images_data.get("default_width", self._config.images.default_width),
            default_height=images_data.get("default_height", self._config.images.default_height),
            cache_ttl=images_data.get("cache_ttl", self._config.images.cache_ttl),
            max_cache_size_mb=images_data.get("max_cache_size_mb", self._config.images.max_cache_size_mb),
        )
        
        # 动画设置
        anim_data = data.get("animations", {})
        self._config.animations = AnimationConfig(
            default_enabled=anim_data.get("default_enabled", self._config.animations.default_enabled),
            default_animation=anim_data.get("default_animation", self._config.animations.default_animation),
            duration=anim_data.get("duration", self._config.animations.duration),
            delay=anim_data.get("delay", self._config.animations.delay),
            supported_animations=anim_data.get("supported_animations", self._config.animations.supported_animations),
        )
        
        # 导出设置
        export_data = data.get("export", {})
        pdf_data = export_data.get("pdf", {})
        self._config.export = ExportConfig(
            pdf_enabled=pdf_data.get("enabled", self._config.export.pdf_enabled),
            libreoffice_path=pdf_data.get("libreoffice_path", self._config.export.libreoffice_path),
            conversion_timeout=pdf_data.get("conversion_timeout", self._config.export.conversion_timeout),
        )
        
        # 存储设置
        storage_data = data.get("storage", {})
        self._config.storage = StorageConfig(
            file_retention_days=storage_data.get("file_retention_days", self._config.storage.file_retention_days),
            max_total_size_gb=storage_data.get("max_total_size_gb", self._config.storage.max_total_size_gb),
            threshold_percentage=storage_data.get("threshold_percentage", self._config.storage.threshold_percentage),
        )
        
        # 日志设置
        log_data = data.get("logging", {})
        self._config.logging = LoggingConfig(
            level=log_data.get("level", self._config.logging.level),
            verbose=log_data.get("verbose", self._config.logging.verbose),
        )
    
    def _ensure_directories(self) -> None:
        """确保必要的目录存在"""
        dirs = [
            self._config.service.output_dir,
            self._config.service.static_dir,
            self._config.service.image_cache_dir,
            self._config.service.temp_dir,
        ]
        
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)


# 全局单例
config_loader = ConfigLoader()
