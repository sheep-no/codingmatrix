"""
动态供应商管理

支持用户通过 base_url 和协议类型（OpenAI 兼容 / Anthropic 原生）添加自定义供应商，
自动拉取模型列表并进行调用。
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import time
import logging
import uuid
import httpx
import json

logger = logging.getLogger(__name__)

MODEL_CACHE_TTL = 300  # 5 min


class Protocol(Enum):
    """API 协议类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str = ""
    max_tokens: int = 4096
    context_length: int = 4096


@dataclass
class DynamicProvider:
    """动态供应商配置"""
    id: str
    name: str
    base_url: str
    protocol: Protocol
    api_key: str
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    models: List[ModelInfo] = field(default_factory=list)
    last_sync: float = 0.0
    sync_error: str = ""


class DynamicProviderManager:
    """动态供应商管理器（内存存储）"""
    
    def __init__(self):
        self.providers: Dict[str, DynamicProvider] = {}
    
    def add(self, name: str, base_url: str, protocol: str, api_key: str) -> DynamicProvider:
        pid = str(uuid.uuid4())[:8]
        p = DynamicProvider(
            id=pid, name=name, base_url=base_url.rstrip("/"),
            protocol=Protocol(protocol), api_key=api_key,
        )
        self.providers[pid] = p
        return p
    
    def get(self, pid: str) -> Optional[DynamicProvider]:
        return self.providers.get(pid)
    
    def get_by_model(self, model_id: str) -> Optional[DynamicProvider]:
        """根据模型名查找供应商"""
        for p in self.providers.values():
            if not p.enabled:
                continue
            for m in p.models:
                if m.id == model_id:
                    return p
        return None
    
    def list(self) -> List[DynamicProvider]:
        """列表（隐藏 API Key）"""
        return [
            DynamicProvider(
                id=p.id, name=p.name, base_url=p.base_url,
                protocol=p.protocol, api_key="", enabled=p.enabled,
                models=p.models, last_sync=p.last_sync, sync_error=p.sync_error,
            )
            for p in self.providers.values()
        ]
    
    def delete(self, pid: str) -> bool:
        if pid not in self.providers:
            return False
        del self.providers[pid]
        return True
    
    def toggle(self, pid: str) -> bool:
        if pid not in self.providers:
            return False
        self.providers[pid].enabled = not self.providers[pid].enabled
        return True


# 全局单例
_manager: Optional[DynamicProviderManager] = None


def get_dynamic_provider_manager() -> DynamicProviderManager:
    global _manager
    if _manager is None:
        _manager = DynamicProviderManager()
    return _manager


async def fetch_models_openai(provider: DynamicProvider) -> List[ModelInfo]:
    """从 OpenAI 兼容端点 /v1/models 拉取"""
    url = f"{provider.base_url}/models"
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    
    models = []
    for item in data.get("data", []):
        mid = item.get("id", "")
        if not mid:
            continue
        models.append(ModelInfo(
            id=mid,
            name=item.get("name", mid),
            max_tokens=item.get("metadata", {}).get("max_tokens", 4096),
        ))
    return models


async def fetch_models_anthropic(provider: DynamicProvider) -> List[ModelInfo]:
    """Anthropic 无公开模型列表 API，用已知模型"""
    known = [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]
    return [ModelInfo(id=m, max_tokens=8192) for m in known]
