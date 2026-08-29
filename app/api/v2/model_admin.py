"""
模型管理接口（管理员端）

⚠️ 已废弃：请使用新的 /api/v2/model-config/* 接口

本文件保留用于向后兼容，将在未来版本中移除。

新接口：
- GET    /api/v2/model-config/models      - 获取所有模型
- POST   /api/v2/model-config/models      - 添加模型
- PUT    /api/v2/model-config/models/{id} - 更新模型
- DELETE /api/v2/model-config/models/{id} - 删除模型
- GET    /api/v2/model-config/agent       - 获取 Agent 配置
- PUT    /api/v2/model-config/agent/role  - 更新角色模型
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List

from app.utils.aicloud.model_registry import MODEL_REGISTRY, get_model
from app.utils.security import require_superadmin
from app.agent.dynamic_model_router import (
    load_agent_model_config,
    save_agent_model_config,
    reload_roles_config,
    MODEL_ID_TO_KEY,
    MODEL_CONTEXT_LENGTHS,
    get_context_length,
    _LayeredModelRouterCompat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["模型管理"])


# ==================== 请求模型 ====================

class SwitchModelRequest(BaseModel):
    model_id: str


class UpdateAgentModelRequest(BaseModel):
    complexity: str = Field("MEDIUM", description="复杂度: SIMPLE, SMALL, MEDIUM, LARGE, ENTERPRISE")
    role: str = Field(..., description="角色: architect, frontend, backend, reviewer, fallback")
    model_id: str = Field(..., description="模型 ID (如 qwen3-8b, deepseek-r1)")


class UpdateFallbackChainRequest(BaseModel):
    chain_name: str = Field(..., description="降级链名称: default, error_recovery, code_generation")
    models: List[str] = Field(..., description="模型 ID 列表（按优先级排序）")


class UpdateErrorTypeModelRequest(BaseModel):
    error_type: str = Field(..., description="错误类型: NameError, AttributeError, ImportError 等")
    model_id: str = Field(..., description="模型 ID")


class UpdateContextLengthRequest(BaseModel):
    model_key: str = Field(..., description="模型 Key (如 Qwen/Qwen3-8B)")
    context_length: int = Field(..., ge=1, description="上下文窗口长度 (token)")


# ==================== 默认模型管理 ====================

@router.post("/default", summary="切换默认免费模型")
async def switch_default_model(
    request: SwitchModelRequest,
    current_user: dict = Depends(require_superadmin)
):
    """切换运行时默认模型（仅超级管理员）"""
    from app.api.v1.model_manager import get_current_default_model_id, _runtime_default_model as _orig

    model = get_model(request.model_id)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"模型 {request.model_id} 不存在，可用模型：{', '.join(MODEL_REGISTRY.keys())}"
        )

    import app.api.v1.model_manager as mm
    mm._runtime_default_model = request.model_id

    logger.info(f"默认模型已切换 | 操作用户={current_user.get('sub')} | 新默认={request.model_id}")
    return {
        "success": True,
        "message": f"默认模型已切换为 {model.name}",
        "new_default": request.model_id
    }


# ==================== Agent 模型配置管理 ====================

@router.put("/agent-config", summary="更新 Agent 模型配置")
async def update_agent_model_config(
    request: UpdateAgentModelRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新指定角色的模型配置（仅超级管理员）"""
    valid_complexities = {"SIMPLE", "SMALL", "MEDIUM", "LARGE", "ENTERPRISE"}
    if request.complexity.upper() not in valid_complexities:
        raise HTTPException(status_code=400, detail=f"无效的复杂度: {request.complexity}")
    valid_roles = ["architect", "frontend", "backend", "reviewer", "fallback"]
    if request.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"无效的角色: {request.role}，可用: {', '.join(valid_roles)}"
        )

    if request.model_id not in MODEL_ID_TO_KEY:
        raise HTTPException(
            status_code=400,
            detail=f"无效的模型 ID: {request.model_id}，可用: {', '.join(MODEL_ID_TO_KEY.keys())}"
        )

    config = load_agent_model_config()
    if not config:
        config = {
            "version": "3.0",
            "description": "Agent 模型配置",
            "last_updated": "",
            "roles": {}
        }

    if "roles" not in config:
        config["roles"] = {}

    config["roles"][request.role] = request.model_id
    config["last_updated"] = datetime.now().isoformat()

    if not save_agent_model_config(config):
        raise HTTPException(status_code=500, detail="保存配置文件失败")

    reload_roles_config()
    _LayeredModelRouterCompat.reload_config()
    logger.info(f"Agent 模型配置已更新 | 操作用户={current_user.get('sub')} | roles.{request.role} = {request.model_id}")

    return {
        "success": True,
        "message": f"已更新 {request.role} 为 {request.model_id}",
        "config": config
    }


@router.post("/agent-config/reload", summary="重新加载 Agent 模型配置")
async def reload_agent_model_config_endpoint(
    current_user: dict = Depends(require_superadmin)
):
    """重新从配置文件加载 Agent 模型配置（仅超级管理员）"""
    reload_roles_config()
    _LayeredModelRouterCompat.reload_config()
    config = load_agent_model_config()
    return {
        "success": True,
        "message": "配置已重新加载",
        "config": config
    }


@router.put("/agent-config/fallback-chain", summary="更新降级链配置")
async def update_fallback_chain(
    request: UpdateFallbackChainRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新降级链的模型列表（仅超级管理员）"""
    valid_chain_names = {"default", "error_recovery", "code_generation"}
    if request.chain_name not in valid_chain_names:
        raise HTTPException(status_code=400, detail=f"无效的降级链名称: {request.chain_name}")
    for model_id in request.models:
        if model_id not in MODEL_ID_TO_KEY:
            raise HTTPException(
                status_code=400,
                detail=f"无效的模型 ID: {model_id}，可用: {', '.join(MODEL_ID_TO_KEY.keys())}"
            )

    config = load_agent_model_config()
    if not config:
        config = {
            "version": "3.0",
            "description": "Agent 模型配置",
            "last_updated": "",
            "roles": {},
            "fallback_chain": [],
        }

    config["fallback_chain"] = request.models
    config["last_updated"] = datetime.now().isoformat()

    if not save_agent_model_config(config):
        raise HTTPException(status_code=500, detail="保存配置文件失败")

    reload_roles_config()
    _LayeredModelRouterCompat.reload_config()
    logger.info(f"降级链配置已更新 | 操作用户={current_user.get('sub')} | {request.chain_name} = {request.models}")

    return {
        "success": True,
        "message": f"已更新降级链 '{request.chain_name}'",
        "config": config
    }


@router.put("/agent-config/error-type-model", summary="更新错误类型模型映射")
async def update_error_type_model(
    request: UpdateErrorTypeModelRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新错误类型到模型的映射（仅超级管理员）"""
    if request.model_id not in MODEL_ID_TO_KEY:
        raise HTTPException(
            status_code=400,
            detail=f"无效的模型 ID: {request.model_id}，可用: {', '.join(MODEL_ID_TO_KEY.keys())}"
        )

    config = load_agent_model_config()
    if not config:
        config = {
            "version": "3.0",
            "description": "Agent 模型配置",
            "last_updated": "",
            "roles": {},
            "error_type_models": {},
        }

    if "error_type_models" not in config:
        config["error_type_models"] = {}

    config["error_type_models"][request.error_type] = request.model_id
    config["last_updated"] = datetime.now().isoformat()

    if not save_agent_model_config(config):
        raise HTTPException(status_code=500, detail="保存配置文件失败")

    logger.info(f"错误类型模型映射已更新 | 操作用户={current_user.get('sub')} | {request.error_type} = {request.model_id}")

    return {
        "success": True,
        "message": f"已更新错误类型 '{request.error_type}' 的模型为 {request.model_id}",
        "config": config
    }


# ==================== 上下文长度管理 ====================

@router.get("/context-lengths", summary="获取所有模型上下文长度")
async def get_context_lengths(
    current_user: dict = Depends(require_superadmin)
):
    """获取所有模型的上下文窗口长度配置（仅超级管理员）"""
    config = load_agent_model_config() or {}
    file_lengths = config.get("model_context_lengths", {})

    # 合并：配置文件 + 代码映射，配置文件优先
    result = {}
    all_keys = set(list(MODEL_CONTEXT_LENGTHS.keys()) + list(file_lengths.keys()))
    for key in sorted(all_keys):
        val = file_lengths.get(key) or MODEL_CONTEXT_LENGTHS.get(key)
        if val and val > 0:
            source = "config" if key in file_lengths else "builtin"
            result[key] = {"context_length": val, "source": source}

    return {"success": True, "models": result}


@router.put("/context-length", summary="更新模型上下文长度")
async def update_context_length(
    request: UpdateContextLengthRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新指定模型的上下文窗口长度（仅超级管理员）"""
    config = load_agent_model_config()
    if not config:
        config = {
            "version": "1.0",
            "description": "Agent 模型配置",
            "last_updated": "",
            "model_context_lengths": {},
        }

    if "model_context_lengths" not in config:
        config["model_context_lengths"] = {}

    old_val = config["model_context_lengths"].get(request.model_key)
    config["model_context_lengths"][request.model_key] = request.context_length
    config["last_updated"] = datetime.now().isoformat()

    if not save_agent_model_config(config):
        raise HTTPException(status_code=500, detail="保存配置文件失败")

    logger.info(
        f"模型上下文长度已更新 | 操作用户={current_user.get('sub')} "
        f"| {request.model_key}: {old_val} -> {request.context_length}"
    )

    return {
        "success": True,
        "message": f"已更新 {request.model_key} 上下文长度为 {request.context_length}",
        "model_key": request.model_key,
        "context_length": request.context_length,
    }


@router.delete("/context-length/{model_key:path}", summary="删除模型上下文长度配置")
async def delete_context_length(
    model_key: str,
    current_user: dict = Depends(require_superadmin)
):
    """删除指定模型的上下文长度配置（恢复为代码内置默认值）"""
    config = load_agent_model_config() or {}
    lengths = config.get("model_context_lengths", {})

    if model_key not in lengths:
        raise HTTPException(status_code=404, detail=f"未找到 {model_key} 的上下文长度配置")

    del lengths[model_key]
    config["last_updated"] = datetime.now().isoformat()
    save_agent_model_config(config)

    fallback = MODEL_CONTEXT_LENGTHS.get(model_key, 32768)
    return {
        "success": True,
        "message": f"已删除 {model_key} 的自定义上下文长度，恢复为默认值 {fallback}",
    }
