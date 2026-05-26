"""
自定义供应商管理

支持用户通过 base_url 和协议类型（OpenAI 兼容 / Anthropic）添加自定义供应商，
并自动拉取模型列表。
"""
import logging
import time
import httpx
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# 模型缓存时间（秒）
MODEL_LIST_CACHE_TTL = 3600  # 1 小时


class Protocol(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str = ""
    description: str = ""
    max_tokens: int = 4096
    supports_vision: bool = False


@dataclass
class CustomProvider:
    """自定义供应商配置"""
    id: str
    name: str
    base_url: str
    protocol: Protocol
    api_key: str
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    models: List[ModelInfo] = field(default_factory=list)
    last_sync: float = 0.0


class CustomProviderManager:
    """自定义供应商管理器"""
    
    def __init__(self):
        self.providers: Dict[str, CustomProvider] = {}
    
    def add_provider(self, name: str, base_url: str, protocol: str, api_key: str) -> CustomProvider:
        """添加自定义供应商"""
        # 生成唯一 ID
        provider_id = f"custom_{int(time.time())}_{hash(name + base_url) & 0xFFFFFFFF:08x}"
        
        # 清理 base_url（去除末尾斜杠）
        base_url = base_url.rstrip("/")
        if protocol == Protocol.OPENAI and not base_url.endswith("/v1"):
            # 自动补充 /v1
            base_url = f"{base_url}/v1"
        
        provider = CustomProvider(
            id=provider_id,
            name=name,
            base_url=base_url,
            protocol=Protocol(protocol),
            api_key=api_key,
        )
        
        self.providers[provider_id] = provider
        return provider
    
    def get_provider(self, provider_id: str) -> Optional[CustomProvider]:
        """获取供应商配置"""
        return self.providers.get(provider_id)
    
    def list_providers(self) -> List[CustomProvider]:
        """获取所有供应商（不含 API Key）"""
        return [
            CustomProvider(
                id=p.id,
                name=p.name,
                base_url=p.base_url,
                protocol=p.protocol,
                api_key="",  # 隐藏 key
                enabled=p.enabled,
                created_at=p.created_at,
                models=p.models,
                last_sync=p.last_sync,
            )
            for p in self.providers.values()
        ]
    
    def delete_provider(self, provider_id: str) -> bool:
        """删除供应商"""
        if provider_id not in self.providers:
            return False
        del self.providers[provider_id]
        return True
    
    def update_enabled(self, provider_id: str, enabled: bool) -> bool:
        """启用/禁用供应商"""
        if provider_id not in self.providers:
            return False
        self.providers[provider_id].enabled = enabled
        return True
    
    async def sync_models(self, provider_id: str) -> List[ModelInfo]:
        """从供应商拉取模型列表"""
        provider = self.providers.get(provider_id)
        if not provider:
            raise ValueError(f"供应商不存在: {provider_id}")
        
        # 检查缓存
        if provider.models and (time.time() - provider.last_sync) < MODEL_LIST_CACHE_TTL:
            return provider.models
        
        try:
            if provider.protocol == Protocol.OPENAI:
                models = await self._fetch_openai_models(provider)
            else:
                models = await self._fetch_anthropic_models(provider)
            
            provider.models = models
            provider.last_sync = time.time()
            return models
        except Exception as e:
            logger.error(f"拉取模型列表失败 ({provider.name}): {e}")
            raise
    
    async def _fetch_openai_models(self, provider: CustomProvider) -> List[ModelInfo]:
        """从 OpenAI 兼容端点拉取模型列表"""
        url = f"{provider.base_url}/models"
        headers = {"Authorization": f"Bearer {provider.api_key}"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            # OpenAI 格式: {"data": [{"id": "..."}, ...]}
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if not model_id:
                    continue
                
                models.append(ModelInfo(
                    id=model_id,
                    name=item.get("name", model_id),
                    description=item.get("description", ""),
                    max_tokens=item.get("metadata", {}).get("max_context_tokens", 4096),
                    supports_vision="vision" in item.get("id", "").lower(),
                ))
            
            return models
    
    async def _fetch_anthropic_models(self, provider: CustomProvider) -> List[ModelInfo]:
        """Anthropic 没有公开的模型列表 API，使用已知模型列表"""
        # Anthropic 已知模型
        known_models = [
            ModelInfo(id="claude-sonnet-4-20250514", max_tokens=8192),
            ModelInfo(id="claude-opus-4-20250514", max_tokens=8192),
            ModelInfo(id="claude-3-5-sonnet-20241022", max_tokens=8192),
            ModelInfo(id="claude-3-5-haiku-20241022", max_tokens=8192),
            ModelInfo(id="claude-3-opus-20240229", max_tokens=4096),
            ModelInfo(id="claude-3-sonnet-20240229", max_tokens=4096),
            ModelInfo(id="claude-3-haiku-20240307", max_tokens=4096),
        ]
        return known_models
    
    async def test_connection(self, provider_id: str) -> tuple[bool, str]:
        """测试供应商连接"""
        provider = self.providers.get(provider_id)
        if not provider:
            return False, "供应商不存在"
        
        try:
            if provider.protocol == Protocol.OPENAI:
                success, message = await self._test_openai(provider)
            else:
                success, message = await self._test_anthropic(provider)
            
            return success, message
        except Exception as e:
            return False, f"连接失败: {str(e)}"
    
    async def _test_openai(self, provider: CustomProvider) -> tuple[bool, str]:
        """测试 OpenAI 兼容端点"""
        url = f"{provider.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code == 200:
                return True, "连接成功"
            elif resp.status_code == 401:
                return False, "API Key 无效"
            elif resp.status_code == 403:
                return False, "权限不足"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    
    async def _test_anthropic(self, provider: CustomProvider) -> tuple[bool, str]:
        """测试 Anthropic 端点"""
        url = f"{provider.base_url}/v1/messages"
        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hi"}],
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code == 200:
                return True, "连接成功"
            elif resp.status_code == 401:
                return False, "API Key 无效"
            elif resp.status_code == 403:
                return False, "权限不足"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:100]}"


# 全局单例
_custom_provider_manager: Optional[CustomProviderManager] = None


def get_custom_provider_manager() -> CustomProviderManager:
    """获取全局 CustomProviderManager 实例"""
    global _custom_provider_manager
    if _custom_provider_manager is None:
        _custom_provider_manager = CustomProviderManager()
    return _custom_provider_manager
