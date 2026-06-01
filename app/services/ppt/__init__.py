"""
PPT 服务模块

提供统一的 PPT 生成、管理和查询功能。
"""

from app.services.ppt.orchestrator import PPTOrchestrator, ppt_orchestrator, PPTOrchestrationError, TaskCancelledError
from app.services.ppt.template_registry import TemplateRegistry, template_registry, TemplateConfig, TemplateInfo, PPTSettings, TemplateRegistryError
from app.services.ppt.file_storage import FileStorageManager, file_storage, FileMetadata, FileStorageError, FileNotFoundError, StorageQuotaExceededError
from app.services.ppt.config_loader import ConfigLoader, config_loader, PPTConfig, ConfigLoaderError

__all__ = [
    # Orchestrator
    "PPTOrchestrator",
    "ppt_orchestrator",
    "PPTOrchestrationError",
    "TaskCancelledError",
    # Template Registry
    "TemplateRegistry",
    "template_registry",
    "TemplateConfig",
    "TemplateInfo",
    "PPTSettings",
    "TemplateRegistryError",
    # File Storage
    "FileStorageManager",
    "file_storage",
    "FileMetadata",
    "FileStorageError",
    "FileNotFoundError",
    "StorageQuotaExceededError",
    # Config Loader
    "ConfigLoader",
    "config_loader",
    "PPTConfig",
    "ConfigLoaderError",
]
