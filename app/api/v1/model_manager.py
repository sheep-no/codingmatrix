"""
模型浏览接口（用户端）

功能：
1. 查看所有可用的免费模型
2. 获取当前默认模型
3. 按能力筛选模型
4. 查看 Agent 模型配置（只读）
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any, Optional, List, Dict

from app.utils.aicloud.model_registry import (
    MODEL_REGISTRY,
    get_model,
    get_default_model,
    ModelCapability
)
from app.utils.security import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["模型浏览"])


# ==================== 响应模型 ====================

class ModelInfoResponse(BaseModel):
    id: str
    name: str
    model_key: str
    description: str
    capabilities: List[str]
    tags: List[str]
    is_default: bool = False


class ModelListResponse(BaseModel):
    models: List[ModelInfoResponse]
    total: int
    default_model: str


class AgentModelConfigResponse(BaseModel):
    version: str
    description: str
    last_updated: str
    roles: Dict[str, str] = {}
    fallback_chain: Optional[List[str]] = None
    error_type_models: Optional[Dict[str, str]] = None
    settings: Optional[Dict[str, Any]] = None
    global_thinking_ratio: float = 0.5
    models: Dict[str, Dict[str, Any]] = {}


# ==================== 全局状态 ====================

_runtime_default_model: Optional[str] = None


def get_current_default_model_id() -> str:
    """获取当前默认模型 ID"""
    if _runtime_default_model:
        return _runtime_default_model
    return get_default_model().id


# ==================== API 端点 ====================

@router.get("/", response_model=ModelListResponse, summary="获取所有可用模型")
async def list_models(
    capability: Optional[str] = None,
    free_only: bool = False
):
    """获取所有可用的免费模型"""
    models = []
    for model_id, model in MODEL_REGISTRY.items():
        if capability:
            try:
                cap = ModelCapability(capability)
                if cap not in model.capabilities:
                    continue
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的能力类型：{capability}")

        caps = [c.value for c in model.capabilities]
        is_default = model_id == get_current_default_model_id()
        models.append(ModelInfoResponse(
            id=model_id,
            name=model.name,
            model_key=model.model_key,
            description=model.description,
            capabilities=caps,
            tags=model.tags,
            is_default=is_default
        ))

    return ModelListResponse(
        models=models,
        total=len(models),
        default_model=get_current_default_model_id()
    )


@router.get("/default", response_model=ModelInfoResponse, summary="获取当前默认模型")
async def get_default():
    """获取当前默认模型的详细信息"""
    model_id = get_current_default_model_id()
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    caps = [c.value for c in model.capabilities]
    return ModelInfoResponse(
        id=model_id,
        name=model.name,
        model_key=model.model_key,
        description=model.description,
        capabilities=caps,
        tags=model.tags,
        is_default=True
    )


@router.get("/capabilities/list", summary="列出所有可用能力")
async def list_capabilities():
    """列出所有可用的模型能力类型"""
    return {
        "capabilities": [cap.value for cap in ModelCapability],
        "description": {
            "text": "文本生成与对话",
            "code": "代码生成与理解",
            "vision": "视觉理解与图像分析",
            "reasoning": "逻辑推理",
            "fast": "轻量快速响应"
        }
    }


@router.get("/agent-config", response_model=AgentModelConfigResponse, summary="获取 Agent 模型配置")
async def get_agent_model_config(token: dict = Depends(verify_token)):
    """获取当前 Agent 各环节使用的模型配置（只读）"""
    from app.agent.dynamic_model_router import (
        load_agent_model_config,
        _load_roles_assignment,
        MODEL_KEY_TO_ID,
    )

    config = load_agent_model_config()
    if not config:
        assignment = _load_roles_assignment()
        roles = {
            "architect": MODEL_KEY_TO_ID.get(assignment.architect_model, assignment.architect_model),
            "frontend": MODEL_KEY_TO_ID.get(assignment.frontend_model, assignment.frontend_model),
            "backend": MODEL_KEY_TO_ID.get(assignment.backend_model, assignment.backend_model),
            "reviewer": MODEL_KEY_TO_ID.get(assignment.reviewer_model, assignment.reviewer_model),
            "fallback": MODEL_KEY_TO_ID.get(assignment.fallback_model, assignment.fallback_model),
        }
        return AgentModelConfigResponse(
            version="3.1",
            description="Agent 模型配置 - 按角色分配模型",
            last_updated="未配置",
            roles=roles,
            fallback_chain=[],
            error_type_models={},
            settings={},
            global_thinking_ratio=0.5,
            models={}
        )
    roles = config.get("roles", {})
    # 兼容 v2.0 格式：从 assignments 中提取
    if not roles and "assignments" in config:
        medium = config["assignments"].get("MEDIUM") or config["assignments"].get("LARGE") or {}
        roles = {k.removesuffix("_model"): v for k, v in medium.items() if k.endswith("_model")}
    return AgentModelConfigResponse(
        version=config.get("version", "3.1"),
        description=config.get("description", ""),
        last_updated=config.get("last_updated", ""),
        roles=roles,
        fallback_chain=config.get("fallback_chain") or config.get("fallback_chains", {}).get("default"),
        error_type_models=config.get("error_type_models"),
        settings=config.get("settings"),
        global_thinking_ratio=config.get("global_thinking_ratio", 0.5),
        models=config.get("models", {})
    )


@router.get("/{model_id}", response_model=ModelInfoResponse, summary="获取指定模型信息")
async def get_model_info(model_id: str):
    """获取指定模型的详细信息"""
    model = get_model(model_id)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"模型 {model_id} 不存在，可用模型：{', '.join(MODEL_REGISTRY.keys())}"
        )
    caps = [c.value for c in model.capabilities]
    is_default = model_id == get_current_default_model_id()
    return ModelInfoResponse(
        id=model_id,
        name=model.name,
        model_key=model.model_key,
        description=model.description,
        capabilities=caps,
        tags=model.tags,
        is_default=is_default
    )
