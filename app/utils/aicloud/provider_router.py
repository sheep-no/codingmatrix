"""
多供应商模型调用系统 - 供应商路由器

根据模型名称路由到对应供应商，支持故障转移。
"""

import logging
from typing import Optional

from app.utils.aicloud.providers import ModelProvider, ProviderRegistry

logger = logging.getLogger(__name__)


# 模型到供应商的映射表
MODEL_PROVIDER_MAP: dict[str, ModelProvider] = {
    # SiliconFlow 供应的模型
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": ModelProvider.SILICONFLOW,
    "deepseek-ai/DeepSeek-R1": ModelProvider.SILICONFLOW,
    "deepseek-ai/DeepSeek-OCR": ModelProvider.SILICONFLOW,
    "Qwen/Qwen3.5-4B": ModelProvider.SILICONFLOW,
    "Qwen/Qwen3-8B": ModelProvider.SILICONFLOW,
    "Qwen/Qwen2.5-7B-Instruct": ModelProvider.SILICONFLOW,
    "Qwen/Qwen-2.5-7B-Instruct": ModelProvider.SILICONFLOW,
    "THUDM/GLM-4.1V-9B-Thinking": ModelProvider.SILICONFLOW,
    "THUDM/GLM-4-9B-0414": ModelProvider.SILICONFLOW,
    "THUDM/GLM-Z1-9B-0414": ModelProvider.SILICONFLOW,
    "THUDM/glm-4-9b-chat": ModelProvider.SILICONFLOW,
    "Kwai-Kolors/Kolors": ModelProvider.SILICONFLOW,
    "netease-youdao/bce-embedding-base_v1": ModelProvider.SILICONFLOW,
    
    # 阿里百炼供应的模型（通过 Model ID 简短名称）
    "qwen-plus": ModelProvider.DASHSCOPE,
    "qwen-turbo": ModelProvider.DASHSCOPE,
    "qwen-max": ModelProvider.DASHSCOPE,
    "qwen-long": ModelProvider.DASHSCOPE,
    
    # 智谱供应的模型（通过简短名称）
    "glm-4": ModelProvider.ZHIPU,
    "glm-4v": ModelProvider.ZHIPU,
    "glm-4-alltools": ModelProvider.ZHIPU,
    
    # DeepSeek 官方供应的模型（通过简短名称）
    "deepseek-chat": ModelProvider.DEEPSEEK,
    "deepseek-reasoner": ModelProvider.DEEPSEEK,
}

# 故障转移配置
PROVIDER_FALLBACK: dict[ModelProvider, list[ModelProvider]] = {
    ModelProvider.SILICONFLOW: [ModelProvider.DASHSCOPE, ModelProvider.ZHIPU],
    ModelProvider.DASHSCOPE: [ModelProvider.SILICONFLOW],
    ModelProvider.ZHIPU: [ModelProvider.SILICONFLOW],
    ModelProvider.DEEPSEEK: [ModelProvider.SILICONFLOW],
    ModelProvider.OPENAI: [ModelProvider.SILICONFLOW],
    ModelProvider.ANTHROPIC: [ModelProvider.SILICONFLOW],
    ModelProvider.OLLAMA: [],  # Ollama 本地部署，不故障转移
}


class ProviderRouter:
    """根据模型名称路由到对应供应商"""
    
    _instance: Optional["ProviderRouter"] = None
    _registry: Optional[ProviderRegistry] = None
    
    def __init__(self, registry: Optional[ProviderRegistry] = None):
        if registry:
            self._registry = registry
    
    @classmethod
    def get_instance(cls, registry: Optional[ProviderRegistry] = None) -> "ProviderRouter":
        """获取路由器单例"""
        if cls._instance is None:
            cls._instance = cls(registry)
        elif registry and cls._instance._registry is None:
            cls._instance._registry = registry
        return cls._instance
    
    @classmethod
    def set_registry(cls, registry: ProviderRegistry) -> None:
        """设置供应商注册表"""
        cls._instance = cls(registry)
    
    def route(self, model_name: str) -> ModelProvider:
        """根据模型名称返回对应供应商"""
        # 先尝试动态供应商（自定义 base_url）
        try:
            from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
            manager = get_dynamic_provider_manager()
            dp = manager.get_by_model(model_name)
            if dp:
                # 动态供应商找到，但返回特殊标记
                pass
        except Exception:
            pass
        
        # 再尝试精确匹配
        provider = MODEL_PROVIDER_MAP.get(model_name)
        if provider:
            return provider
        
        # 尝试模糊匹配（前缀匹配）
        for model_key, provider in MODEL_PROVIDER_MAP.items():
            if model_name.startswith(model_key.split("/")[0]) or model_key.startswith(model_name.split("/")[0]):
                return provider
        
        # 默认返回 SiliconFlow
        logger.warning(f"Unknown model {model_name}, defaulting to SiliconFlow")
        return ModelProvider.SILICONFLOW
    
    def get_fallback_providers(self, primary: ModelProvider) -> list[ModelProvider]:
        """获取故障转移供应商列表（过滤掉不可用的）"""
        fallbacks = PROVIDER_FALLBACK.get(primary, [])
        if not self._registry:
            return fallbacks
        
        return [p for p in fallbacks if self._registry.is_provider_available(p)]
    
    @staticmethod
    def clear_cache() -> None:
        """清除单例缓存（用于测试）"""
        ProviderRouter._instance = None
