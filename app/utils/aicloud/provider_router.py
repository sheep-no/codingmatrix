"""
多供应商模型调用系统 - 供应商路由器

根据模型名称路由到对应供应商，支持故障转移。
模型映射从 data/agent_model_config.json 统一加载。
"""

import json
import logging
import os
from typing import Optional

from app.utils.aicloud.providers import ModelProvider, ProviderRegistry

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../../data/agent_model_config.json")


def _load_provider_map() -> dict[str, ModelProvider]:
    """从统一配置文件构建模型-供应商映射"""
    provider_enum_map = {
        "siliconflow": ModelProvider.SILICONFLOW,
        "dashscope": ModelProvider.DASHSCOPE,
        "zhipu": ModelProvider.ZHIPU,
        "deepseek": ModelProvider.DEEPSEEK,
    }
    result = {}
    try:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        for model_id, m in config.get("models", {}).items():
            name = m.get("name", "")
            provider_str = m.get("provider", "siliconflow")
            provider = provider_enum_map.get(provider_str, ModelProvider.SILICONFLOW)
            if name:
                result[name] = provider
    except Exception as e:
        logger.warning(f"加载统一模型配置失败: {e}")

    # 不在统一配置中的特殊模型（兜底）
    result.setdefault("THUDM/glm-4-9b-chat", ModelProvider.SILICONFLOW)
    result.setdefault("Qwen/Qwen-2.5-7B-Instruct", ModelProvider.SILICONFLOW)
    result.setdefault("THUDM/GLM-4.1V-9B-Thinking", ModelProvider.SILICONFLOW)
    result.setdefault("deepseek-ai/DeepSeek-R1", ModelProvider.SILICONFLOW)
    result.setdefault("qwen-plus", ModelProvider.DASHSCOPE)
    result.setdefault("qwen-turbo", ModelProvider.DASHSCOPE)
    result.setdefault("qwen-max", ModelProvider.DASHSCOPE)
    result.setdefault("qwen-long", ModelProvider.DASHSCOPE)
    result.setdefault("glm-4", ModelProvider.ZHIPU)
    result.setdefault("glm-4v", ModelProvider.ZHIPU)
    result.setdefault("glm-4-alltools", ModelProvider.ZHIPU)
    result.setdefault("deepseek-chat", ModelProvider.DEEPSEEK)
    result.setdefault("deepseek-reasoner", ModelProvider.DEEPSEEK)
    return result


# 从统一配置动态加载
MODEL_PROVIDER_MAP: dict[str, ModelProvider] = _load_provider_map()

# 故障转移配置
PROVIDER_FALLBACK: dict[ModelProvider, list[ModelProvider]] = {
    ModelProvider.SILICONFLOW: [ModelProvider.DASHSCOPE, ModelProvider.ZHIPU],
    ModelProvider.DASHSCOPE: [ModelProvider.SILICONFLOW],
    ModelProvider.ZHIPU: [ModelProvider.SILICONFLOW],
    ModelProvider.DEEPSEEK: [ModelProvider.SILICONFLOW],
    ModelProvider.OPENAI: [ModelProvider.SILICONFLOW],
    ModelProvider.ANTHROPIC: [ModelProvider.SILICONFLOW],
    ModelProvider.OLLAMA: [],
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
        try:
            from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
            manager = get_dynamic_provider_manager()
            dp = manager.get_by_model(model_name)
            if dp:
                pass
        except Exception:
            pass
        
        provider = MODEL_PROVIDER_MAP.get(model_name)
        if provider:
            return provider
        
        for model_key, provider in MODEL_PROVIDER_MAP.items():
            if model_name.startswith(model_key.split("/")[0]) or model_key.startswith(model_name.split("/")[0]):
                return provider
        
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
