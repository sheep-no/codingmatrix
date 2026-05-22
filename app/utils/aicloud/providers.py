"""
多供应商模型调用系统 - Provider 枚举和配置

定义供应商枚举类型和配置数据类。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class ModelProvider(str, Enum):
    """模型供应商枚举"""
    SILICONFLOW = "siliconflow"
    DASHSCOPE = "dashscope"      # 阿里百炼
    ZHIPU = "zhipu"              # 智谱 GLM
    DEEPSEEK = "deepseek"        # DeepSeek 官方
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"            # 本地部署


@dataclass
class ProviderConfig:
    """供应商配置"""
    provider: ModelProvider
    api_key: str = ""
    base_url: str = ""
    timeout: float = 360.0
    max_retries: int = 3
    enabled: bool = True
    
    def is_valid(self) -> bool:
        """检查配置是否有效"""
        if not self.enabled:
            return False
        # Ollama 不需要 API Key
        if self.provider == ModelProvider.OLLAMA:
            return bool(self.base_url)
        return bool(self.api_key) and bool(self.base_url)


@dataclass
class ProviderRegistry:
    """供应商注册表（运行时管理所有可用供应商）"""
    providers: dict[ModelProvider, ProviderConfig] = field(default_factory=dict)
    
    def register(self, config: ProviderConfig) -> None:
        """注册供应商配置"""
        if config.is_valid():
            self.providers[config.provider] = config
    
    def get(self, provider: ModelProvider) -> Optional[ProviderConfig]:
        """获取供应商配置"""
        return self.providers.get(provider)
    
    def get_available_providers(self) -> list[ModelProvider]:
        """获取所有可用的供应商"""
        return [p for p, config in self.providers.items() if config.is_valid()]
    
    def is_provider_available(self, provider: ModelProvider) -> bool:
        """检查供应商是否可用"""
        config = self.get(provider)
        return config is not None and config.is_valid()
