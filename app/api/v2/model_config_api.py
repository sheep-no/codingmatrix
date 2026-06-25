"""
统一模型配置 API

简化版模型管理接口，基于 unified_model_config.json

端点：
- GET    /api/v2/model-config/models          - 获取所有模型
- POST   /api/v2/model-config/models          - 添加模型
- PUT    /api/v2/model-config/models/{id}     - 更新模型
- DELETE /api/v2/model-config/models/{id}     - 删除模型
- PUT    /api/v2/model-config/models/{id}/toggle - 切换启用状态
- GET    /api/v2/model-config/providers       - 获取所有供应商
- POST   /api/v2/model-config/providers       - 添加供应商
- DELETE /api/v2/model-config/providers/{id}  - 删除供应商
- GET    /api/v2/model-config/agent           - 获取 Agent 配置
- PUT    /api/v2/model-config/agent/role      - 更新角色模型
- PUT    /api/v2/model-config/agent/fallback  - 更新降级链
- POST   /api/v2/model-config/reload          - 重新加载配置
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from app.utils.security import require_superadmin
from app.services.model_config_manager import (
    get_model_config_manager,
    reload_model_config,
    ModelConfig,
    ProviderConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-config", tags=["模型配置管理"])


# ==================== 请求模型 ====================

class AddModelRequest(BaseModel):
    id: str = Field(..., description="模型 ID (如 qwen3-8b)")
    name: str = Field(..., description="API 模型名 (如 Qwen/Qwen3-8B)")
    display_name: str = Field(..., description="显示名称")
    provider: str = Field("siliconflow", description="供应商 ID")
    model_type: str = Field("chat", description="类型: chat/embedding/image/vision/audio")
    context_length: int = Field(32768, description="上下文长度")
    max_output: int = Field(8192, description="最大输出")
    temperature: float = Field(0.7, description="温度")
    timeout: int = Field(300, description="超时(秒)")
    is_reasoning: bool = Field(False, description="是否推理模型")
    thinking_ratio: float = Field(0.0, description="思考比例")
    speed: float = Field(1.0, description="速度等级")
    tags: List[str] = Field(default_factory=list, description="标签")


class UpdateModelRequest(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    provider: Optional[str] = None
    model_type: Optional[str] = None
    context_length: Optional[int] = None
    max_output: Optional[int] = None
    temperature: Optional[float] = None
    timeout: Optional[int] = None
    is_reasoning: Optional[bool] = None
    thinking_ratio: Optional[float] = None
    speed: Optional[float] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None


class AddProviderRequest(BaseModel):
    id: str = Field(..., description="供应商 ID")
    name: str = Field(..., description="供应商名称")
    api_key: str = Field("", description="API Key")
    base_url: str = Field("", description="Base URL")


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., description="角色: architect/frontend/backend/reviewer/fallback")
    model_id: str = Field(..., description="模型 ID")


class UpdateFallbackRequest(BaseModel):
    chain: List[str] = Field(..., description="降级链模型 ID 列表")


# ==================== 模型管理 ====================

@router.get("/models", summary="获取所有模型")
async def list_models(
    model_type: Optional[str] = None,
    enabled_only: bool = False,
    current_user: dict = Depends(require_superadmin)
):
    """获取所有模型配置"""
    manager = get_model_config_manager()
    
    if model_type:
        models = manager.get_models_by_type(model_type)
    else:
        models = manager.get_all_models(enabled_only=enabled_only)
    
    return {
        "success": True,
        "models": [_model_to_dict(m) for m in models],
        "total": len(models)
    }


@router.post("/models", summary="添加模型")
async def add_model(
    request: AddModelRequest,
    current_user: dict = Depends(require_superadmin)
):
    """添加新模型"""
    manager = get_model_config_manager()
    
    # 检查是否已存在
    if manager.get_model(request.id):
        raise HTTPException(status_code=400, detail=f"模型 {request.id} 已存在")
    
    model = ModelConfig(
        id=request.id,
        name=request.name,
        display_name=request.display_name,
        provider=request.provider,
        model_type=request.model_type,
        context_length=request.context_length,
        max_output=request.max_output,
        temperature=request.temperature,
        timeout=request.timeout,
        is_reasoning=request.is_reasoning,
        thinking_ratio=request.thinking_ratio,
        speed=request.speed,
        tags=request.tags
    )
    
    if manager.add_model(model):
        logger.info(f"添加模型成功 | 操作用户={current_user.get('sub')} | 模型={request.id}")
        return {"success": True, "message": f"模型 {request.display_name} 已添加"}
    
    raise HTTPException(status_code=500, detail="保存配置失败")


@router.put("/models/{model_id}", summary="更新模型")
async def update_model(
    model_id: str,
    request: UpdateModelRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新模型配置"""
    manager = get_model_config_manager()
    
    if not manager.get_model(model_id):
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    
    updates = {k: v for k, v in request.dict().items() if v is not None}
    
    if manager.update_model(model_id, updates):
        logger.info(f"更新模型成功 | 操作用户={current_user.get('sub')} | 模型={model_id}")
        return {"success": True, "message": f"模型 {model_id} 已更新"}
    
    raise HTTPException(status_code=500, detail="更新失败")


@router.delete("/models/{model_id}", summary="删除模型")
async def delete_model(
    model_id: str,
    current_user: dict = Depends(require_superadmin)
):
    """删除模型"""
    manager = get_model_config_manager()
    
    if manager.delete_model(model_id):
        logger.info(f"删除模型成功 | 操作用户={current_user.get('sub')} | 模型={model_id}")
        return {"success": True, "message": f"模型 {model_id} 已删除"}
    
    raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")


@router.put("/models/{model_id}/toggle", summary="切换模型状态")
async def toggle_model(
    model_id: str,
    current_user: dict = Depends(require_superadmin)
):
    """切换模型启用/禁用状态"""
    manager = get_model_config_manager()
    
    model = manager.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    
    if manager.toggle_model(model_id):
        new_status = "启用" if not model.enabled else "禁用"
        logger.info(f"切换模型状态 | 操作用户={current_user.get('sub')} | 模型={model_id} -> {new_status}")
        return {"success": True, "message": f"模型 {model_id} 已{new_status}"}
    
    raise HTTPException(status_code=500, detail="操作失败")


# ==================== 供应商管理 ====================

@router.get("/providers", summary="获取所有供应商")
async def list_providers(
    current_user: dict = Depends(require_superadmin)
):
    """获取所有供应商配置"""
    manager = get_model_config_manager()
    providers = manager.get_all_providers()
    
    return {
        "success": True,
        "providers": [_provider_to_dict(p) for p in providers],
        "total": len(providers)
    }


@router.post("/providers", summary="添加供应商")
async def add_provider(
    request: AddProviderRequest,
    current_user: dict = Depends(require_superadmin)
):
    """添加新供应商"""
    manager = get_model_config_manager()
    
    if manager.get_provider(request.id):
        raise HTTPException(status_code=400, detail=f"供应商 {request.id} 已存在")
    
    provider = ProviderConfig(
        id=request.id,
        name=request.name,
        api_key=request.api_key,
        base_url=request.base_url
    )
    
    if manager.add_provider(provider):
        logger.info(f"添加供应商成功 | 操作用户={current_user.get('sub')} | 供应商={request.id}")
        return {"success": True, "message": f"供应商 {request.name} 已添加"}
    
    raise HTTPException(status_code=500, detail="保存配置失败")


@router.delete("/providers/{provider_id}", summary="删除供应商")
async def delete_provider(
    provider_id: str,
    current_user: dict = Depends(require_superadmin)
):
    """删除供应商"""
    manager = get_model_config_manager()
    
    if manager.delete_provider(provider_id):
        logger.info(f"删除供应商成功 | 操作用户={current_user.get('sub')} | 供应商={provider_id}")
        return {"success": True, "message": f"供应商 {provider_id} 已删除"}
    
    raise HTTPException(status_code=404, detail=f"供应商 {provider_id} 不存在")


# ==================== Agent 配置 ====================

@router.get("/agent", summary="获取 Agent 配置")
async def get_agent_config(
    current_user: dict = Depends(require_superadmin)
):
    """获取 Agent 角色和降级链配置"""
    manager = get_model_config_manager()
    config = manager.get_agent_config()
    
    return {
        "success": True,
        "roles": config.roles,
        "fallback_chain": config.fallback_chain
    }


@router.put("/agent/role", summary="更新角色模型")
async def update_agent_role(
    request: UpdateRoleRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新 Agent 角色使用的模型"""
    manager = get_model_config_manager()
    
    # 验证模型存在
    if not manager.get_model(request.model_id):
        raise HTTPException(status_code=404, detail=f"模型 {request.model_id} 不存在")
    
    if manager.update_agent_role(request.role, request.model_id):
        logger.info(f"更新角色模型 | 操作用户={current_user.get('sub')} | {request.role} -> {request.model_id}")
        return {"success": True, "message": f"角色 {request.role} 已使用模型 {request.model_id}"}
    
    raise HTTPException(status_code=400, detail=f"无效的角色: {request.role}")


@router.put("/agent/fallback", summary="更新降级链")
async def update_fallback_chain(
    request: UpdateFallbackRequest,
    current_user: dict = Depends(require_superadmin)
):
    """更新 Agent 降级链"""
    manager = get_model_config_manager()
    
    # 验证所有模型存在
    for model_id in request.chain:
        if not manager.get_model(model_id):
            raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    
    if manager.update_fallback_chain(request.chain):
        logger.info(f"更新降级链 | 操作用户={current_user.get('sub')} | 链={request.chain}")
        return {"success": True, "message": "降级链已更新"}
    
    raise HTTPException(status_code=500, detail="更新失败")


# ==================== 工具方法 ====================

@router.post("/reload", summary="重新加载配置")
async def reload_config(
    current_user: dict = Depends(require_superadmin)
):
    """重新从文件加载配置"""
    reload_model_config()
    logger.info(f"重新加载配置 | 操作用户={current_user.get('sub')}")
    return {"success": True, "message": "配置已重新加载"}


def _model_to_dict(m: ModelConfig) -> Dict:
    """模型转字典"""
    return {
        "id": m.id,
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


def _provider_to_dict(p: ProviderConfig) -> Dict:
    """供应商转字典"""
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "enabled": p.enabled,
        "has_api_key": bool(p.api_key)
    }
