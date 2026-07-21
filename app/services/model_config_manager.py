"""
统一模型配置管理器

设计理念：
1. 简单直观 - 一个配置文件管理所有模型
2. 易于扩展 - 添加新模型只需一行配置
3. 自动适配 - 从供应商自动发现模型
4. 热更新 - 修改配置立即生效

配置文件格式：
{
  "providers": {
    "siliconflow": {
      "api_key": "sk-xxx",
      "base_url": "https://api.siliconflow.cn/v1"
    }
  },
  "models": {
    "qwen3-8b": {
      "name": "Qwen/Qwen3-8B",
      "display_name": "Qwen3 8B",
      "provider": "siliconflow",
      "type": "chat",  // chat/embedding/image/vision/audio
      "context_length": 131072,
      "max_output": 8192
    }
  },
  "agent": {
    "roles": {
      "architect": "qwen3-8b",
      "frontend": "deepseek-r1",
      "backend": "nex-n2-pro",
      "reviewer": "glm-z1-9b",
      "fallback": "qwen3-8b"
    },
    "fallback_chain": ["qwen3-8b", "glm-z1-9b"]
  }
}
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "data" / "unified_model_config.json"


@dataclass
class ModelConfig:
    """模型配置"""
    id: str                              # 模型 ID (简短)
    name: str                            # API 模型名
    display_name: str                    # 显示名称
    provider: str                        # 供应商 ID
    model_type: str = "chat"             # 类型: chat/embedding/image/vision/audio
    context_length: int = 32768          # 上下文长度
    max_output: int = 8192               # 最大输出
    temperature: float = 0.7             # 温度
    timeout: int = 300                   # 超时(秒)
    is_reasoning: bool = False           # 是否推理模型
    thinking_ratio: float = 0.0          # 思考比例
    speed: float = 1.0                   # 速度等级 (1=正常, >1=快, <1=慢)
    enabled: bool = True                 # 是否启用
    tags: List[str] = field(default_factory=list)


@dataclass
class ProviderConfig:
    """供应商配置"""
    id: str
    name: str
    api_key: str = ""
    base_url: str = ""
    enabled: bool = True


@dataclass
class AgentConfig:
    """Agent 配置"""
    roles: Dict[str, str] = field(default_factory=lambda: {
        "architect": "qwen3-8b",
        "frontend": "deepseek-r1",
        "backend": "nex-n2-pro",
        "reviewer": "glm-z1-9b",
        "fallback": "qwen3-8b"
    })
    fallback_chain: List[str] = field(default_factory=lambda: ["qwen3-8b", "glm-z1-9b"])


class ModelConfigManager:
    """统一模型配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else CONFIG_PATH
        self._models: Dict[str, ModelConfig] = {}
        self._providers: Dict[str, ProviderConfig] = {}
        self._agent_config = AgentConfig()
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._parse_config(data)
                logger.info(f"已加载模型配置: {self.config_path}")
            else:
                logger.info("配置文件不存在，使用默认配置")
                self._init_default_config()
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self._init_default_config()
    
    def _parse_config(self, data: Dict):
        """解析配置"""
        # 解析供应商
        for pid, pdata in data.get("providers", {}).items():
            self._providers[pid] = ProviderConfig(
                id=pid,
                name=pdata.get("name", pid),
                api_key=pdata.get("api_key", ""),
                base_url=pdata.get("base_url", ""),
                enabled=pdata.get("enabled", True)
            )
        
        # 解析模型
        for mid, mdata in data.get("models", {}).items():
            self._models[mid] = ModelConfig(
                id=mid,
                name=mdata.get("name", ""),
                display_name=mdata.get("display_name", mid),
                provider=mdata.get("provider", "siliconflow"),
                model_type=mdata.get("type", "chat"),
                context_length=mdata.get("context_length", 32768),
                max_output=mdata.get("max_output", 8192),
                temperature=mdata.get("temperature", 0.7),
                timeout=mdata.get("timeout", 300),
                is_reasoning=mdata.get("is_reasoning", False),
                thinking_ratio=mdata.get("thinking_ratio", 0.0),
                speed=mdata.get("speed", 1.0),
                enabled=mdata.get("enabled", True),
                tags=mdata.get("tags", [])
            )
        
        # 解析 Agent 配置
        agent_data = data.get("agent", {})
        self._agent_config = AgentConfig(
            roles=agent_data.get("roles", self._agent_config.roles),
            fallback_chain=agent_data.get("fallback_chain", self._agent_config.fallback_chain)
        )
    
    def _init_default_config(self):
        """初始化默认配置"""
        self._providers["siliconflow"] = ProviderConfig(
            id="siliconflow",
            name="SiliconFlow",
            base_url="https://api.siliconflow.cn/v1"
        )
        
        # 添加默认模型
        default_models = [
            ModelConfig(id="qwen3-8b", name="Qwen/Qwen3-8B", display_name="Qwen3 8B", 
                       provider="siliconflow", context_length=131072, tags=["通用"]),
            ModelConfig(id="deepseek-r1", name="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", 
                       display_name="DeepSeek R1", provider="siliconflow", 
                       is_reasoning=True, context_length=131072, tags=["推理"]),
            ModelConfig(id="glm-z1-9b", name="THUDM/GLM-Z1-9B-0414", display_name="GLM Z1 9B",
                       provider="siliconflow", context_length=131072, tags=["评测"]),
        ]
        for m in default_models:
            self._models[m.id] = m
    
    def save_config(self):
        """保存配置到 unified_model_config.json，并同步到 agent_model_config.json"""
        try:
            data = {
                "version": "5.0",
                "description": "统一模型配置",
                "last_updated": __import__('datetime').datetime.now().isoformat(),
                "providers": {
                    pid: {
                        "name": p.name,
                        "api_key": p.api_key,
                        "base_url": p.base_url,
                        "enabled": p.enabled
                    }
                    for pid, p in self._providers.items()
                },
                "models": {
                    mid: {
                        "name": m.name,
                        "display_name": m.display_name,
                        "provider": m.provider,
                        "type": m.model_type,
                        "context_length": m.context_length,
                        "max_output": m.max_output,
                        "temperature": m.temperature,
                        "timeout": m.timeout,
                        "is_reasoning": m.is_reasoning,
                        "thinking_ratio": m.thinking_ratio,
                        "speed": m.speed,
                        "enabled": m.enabled,
                        "tags": m.tags
                    }
                    for mid, m in self._models.items()
                },
                "agent": {
                    "roles": self._agent_config.roles,
                    "fallback_chain": self._agent_config.fallback_chain
                }
            }
            
            os.makedirs(self.config_path.parent, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存模型配置: {self.config_path}")
            
            # 同步到 agent_model_config.json（运行时读取的文件）
            self._sync_to_agent_config(data)
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def _sync_to_agent_config(self, unified_data: Dict):
        """将统一配置同步到 agent_model_config.json"""
        agent_config_path = self.config_path.parent / "agent_model_config.json"
        try:
            # 保留现有 agent_config.json 中 models 以外的所有字段
            existing = {}
            if agent_config_path.exists():
                with open(agent_config_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            
            # 构建 models 部分
            synced_models = {}
            for mid, m in unified_data.get("models", {}).items():
                synced_models[mid] = {
                    "name": m["name"],
                    "display_name": m.get("display_name", mid),
                    "provider": m.get("provider", "siliconflow"),
                    "is_reasoning": m.get("is_reasoning", False),
                    "context_length": m.get("context_length", 32768),
                    "thinking_ratio": m.get("thinking_ratio", 0.0),
                    "temperature": m.get("temperature", 0.7),
                    "timeout": m.get("timeout", 300),
                    "speed": m.get("speed", 1.0)
                }
            
            agent_config = {
                "version": "5.0",
                "description": "统一模型配置 - 由 unified_model_config.json 自动同步",
                "last_updated": unified_data.get("last_updated", ""),
                "models": synced_models,
                "roles": unified_data.get("agent", {}).get("roles", existing.get("roles", {})),
                "fallback_chain": unified_data.get("agent", {}).get("fallback_chain", existing.get("fallback_chain", [])),
                "error_type_models": existing.get("error_type_models", {}),
                "settings": existing.get("settings", {}),
                "cross_validation": existing.get("cross_validation", {}),
                "model_context_lengths": existing.get("model_context_lengths", {})
            }
            
            os.makedirs(agent_config_path.parent, exist_ok=True)
            with open(agent_config_path, 'w', encoding='utf-8') as f:
                json.dump(agent_config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已同步 Agent 模型配置: {agent_config_path}")
        except Exception as e:
            logger.error(f"同步 Agent 配置失败: {e}")
    
    # ==================== 模型管理 ====================
    
    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self._models.get(model_id)
    
    def get_all_models(self, enabled_only: bool = False) -> List[ModelConfig]:
        """获取所有模型"""
        models = list(self._models.values())
        if enabled_only:
            models = [m for m in models if m.enabled]
        return sorted(models, key=lambda m: m.id)
    
    def add_model(self, model: ModelConfig) -> bool:
        """添加模型"""
        self._models[model.id] = model
        return self.save_config()
    
    def update_model(self, model_id: str, updates: Dict[str, Any]) -> bool:
        """更新模型配置"""
        model = self._models.get(model_id)
        if not model:
            return False
        
        for key, value in updates.items():
            if hasattr(model, key):
                setattr(model, key, value)
        
        return self.save_config()
    
    def delete_model(self, model_id: str) -> bool:
        """删除模型"""
        if model_id in self._models:
            del self._models[model_id]
            return self.save_config()
        return False
    
    def toggle_model(self, model_id: str) -> bool:
        """切换模型启用状态"""
        model = self._models.get(model_id)
        if model:
            model.enabled = not model.enabled
            return self.save_config()
        return False
    
    # ==================== 供应商管理 ====================
    
    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """获取供应商配置"""
        return self._providers.get(provider_id)
    
    def get_all_providers(self) -> List[ProviderConfig]:
        """获取所有供应商"""
        return list(self._providers.values())
    
    def add_provider(self, provider: ProviderConfig) -> bool:
        """添加供应商"""
        self._providers[provider.id] = provider
        return self.save_config()
    
    def update_provider(self, provider_id: str, updates: Dict[str, Any]) -> bool:
        """更新供应商配置"""
        provider = self._providers.get(provider_id)
        if not provider:
            return False
        
        for key, value in updates.items():
            if hasattr(provider, key):
                setattr(provider, key, value)
        
        return self.save_config()
    
    def delete_provider(self, provider_id: str) -> bool:
        """删除供应商"""
        if provider_id in self._providers:
            del self._providers[provider_id]
            return self.save_config()
        return False
    
    # ==================== Agent 配置 ====================
    
    def get_agent_config(self) -> AgentConfig:
        """获取 Agent 配置"""
        return self._agent_config
    
    def update_agent_role(self, role: str, model_id: str) -> bool:
        """更新 Agent 角色模型"""
        if role not in ["architect", "frontend", "backend", "reviewer", "fallback"]:
            return False
        self._agent_config.roles[role] = model_id
        return self.save_config()
    
    def update_fallback_chain(self, chain: List[str]) -> bool:
        """更新降级链"""
        self._agent_config.fallback_chain = chain
        return self.save_config()
    
    # ==================== 工具方法 ====================
    
    def get_models_by_type(self, model_type: str) -> List[ModelConfig]:
        """按类型获取模型"""
        return [m for m in self._models.values() if m.model_type == model_type and m.enabled]
    
    def get_chat_models(self) -> List[ModelConfig]:
        """获取聊天模型"""
        return self.get_models_by_type("chat")
    
    def get_embedding_models(self) -> List[ModelConfig]:
        """获取嵌入模型"""
        return self.get_models_by_type("embedding")
    
    def get_vision_models(self) -> List[ModelConfig]:
        """获取视觉模型"""
        return self.get_models_by_type("vision") + self.get_models_by_type("image")
    
    def get_reasoning_models(self) -> List[ModelConfig]:
        """获取推理模型"""
        return [m for m in self._models.values() if m.is_reasoning and m.enabled]
    
    def get_model_by_name(self, name: str) -> Optional[ModelConfig]:
        """通过 API 名称获取模型"""
        for m in self._models.values():
            if m.name == name:
                return m
        return None
    
    def export_config(self) -> Dict:
        """导出配置为字典"""
        return {
            "providers": {pid: vars(p) for pid, p in self._providers.items()},
            "models": {mid: vars(m) for mid, m in self._models.items()},
            "agent": vars(self._agent_config)
        }


# 全局单例
import threading
_manager: Optional[ModelConfigManager] = None
_lock: threading.Lock = threading.Lock()


def get_model_config_manager() -> ModelConfigManager:
    """获取模型配置管理器单例"""
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = ModelConfigManager()
    return _manager


def reload_model_config():
    """重新加载配置"""
    global _manager
    with _lock:
        _manager = None
        _manager = ModelConfigManager()
    return _manager
