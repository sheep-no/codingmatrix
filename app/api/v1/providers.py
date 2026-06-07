"""
动态供应商 API 路由

端点：
- POST /api/v1/providers - 添加供应商
- GET /api/v1/providers - 获取供应商列表
- GET /api/v1/providers/{id} - 获取供应商详情
- DELETE /api/v1/providers/{id} - 删除供应商
- PUT /api/v1/providers/{id}/toggle - 启用/禁用
- POST /api/v1/providers/{id}/sync - 同步模型列表
- POST /api/v1/providers/{id}/test - 测试连接
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field

from app.utils.aicloud.dynamic_provider import (
    DynamicProviderManager, DynamicProvider,
    Protocol, MODEL_CACHE_TTL,
    get_dynamic_provider_manager,
    fetch_models_openai, fetch_models_anthropic,
)
from app.utils.aicloud.adapters.dynamic import DynamicAdapter
from app.utils.rate_limiter import limiter
from app.utils.security import verify_token
import time
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/providers", tags=["动态供应商管理"])


class AddProviderRequest(BaseModel):
    name: str = Field(..., description="供应商名称")
    base_url: str = Field(..., description="API Base URL")
    protocol: str = Field(..., description="协议类型: openai / anthropic")
    api_key: str = Field(..., description="API Key")


class ProviderResponse(BaseModel):
    id: str
    name: str
    base_url: str
    protocol: str
    enabled: bool
    models: list[str]
    last_sync: float
    sync_error: str


class AddProviderResponse(BaseModel):
    id: str
    name: str
    message: str


class SyncResponse(BaseModel):
    count: int
    error: str = ""
    message: str


class TestResponse(BaseModel):
    success: bool
    message: str


@router.post("", summary="添加动态供应商")
@limiter.limit("10/minute")
async def add_provider(request: Request, body: AddProviderRequest, token: dict = Depends(verify_token)):
    manager = get_dynamic_provider_manager()
    
    if body.protocol not in ("openai", "anthropic"):
        raise HTTPException(status_code=400, detail="protocol 必须是 openai 或 anthropic")
    
    if not body.api_key or len(body.api_key) < 10:
        raise HTTPException(status_code=400, detail="API Key 格式无效")
    
    provider = manager.add(
        name=body.name,
        base_url=body.base_url,
        protocol=body.protocol,
        api_key=body.api_key,
    )
    
    return AddProviderResponse(
        id=provider.id,
        name=provider.name,
        message=f"供应商 {provider.name} 已添加，base_url: {provider.base_url}",
    )


@router.get("", summary="获取供应商列表")
@limiter.limit("30/minute")
async def list_providers(request: Request, token: dict = Depends(verify_token)):
    manager = get_dynamic_provider_manager()
    providers = manager.list()
    
    return [
        ProviderResponse(
            id=p.id,
            name=p.name,
            base_url=p.base_url,
            protocol=p.protocol.value,
            enabled=p.enabled,
            models=[m.id for m in p.models],
            last_sync=p.last_sync,
            sync_error=p.sync_error,
        )
        for p in providers
    ]


@router.get("/{pid}", summary="获取供应商详情")
@limiter.limit("30/minute")
async def get_provider(request: Request, pid: str, token: dict = Depends(verify_token)):
    manager = get_dynamic_provider_manager()
    p = manager.get(pid)
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    return ProviderResponse(
        id=p.id, name=p.name, base_url=p.base_url,
        protocol=p.protocol.value, enabled=p.enabled,
        models=[m.id for m in p.models],
        last_sync=p.last_sync, sync_error=p.sync_error,
    )


@router.delete("/{pid}", summary="删除供应商")
@limiter.limit("10/minute")
async def delete_provider(request: Request, pid: str, token: dict = Depends(verify_token)):
    manager = get_dynamic_provider_manager()
    if not manager.delete(pid):
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"message": "供应商已删除"}


@router.put("/{pid}/toggle", summary="启用/禁用供应商")
@limiter.limit("20/minute")
async def toggle_provider(request: Request, pid: str, token: dict = Depends(verify_token)):
    manager = get_dynamic_provider_manager()
    if not manager.toggle(pid):
        raise HTTPException(status_code=404, detail="供应商不存在")
    p = manager.get(pid)
    return {"message": f"供应商已{'启用' if p.enabled else '禁用'}", "enabled": p.enabled}


@router.post("/{pid}/sync", summary="同步模型列表")
@limiter.limit("10/minute")
async def sync_models(request: Request, pid: str, token: dict = Depends(verify_token), force: bool = False):
    manager = get_dynamic_provider_manager()
    provider = manager.get(pid)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    # 检查缓存（除非 force=True）
    if not force and provider.last_sync > 0:
        elapsed = time.time() - provider.last_sync
        if elapsed < MODEL_CACHE_TTL:
            return SyncResponse(
                count=len(provider.models),
                message=f"模型列表已缓存（{int(elapsed)}s 前同步）",
            )
    
    try:
        if provider.protocol.value == "anthropic":
            models = await fetch_models_anthropic(provider)
        else:
            models = await fetch_models_openai(provider)
        
        provider.models = models
        provider.last_sync = time.time()
        provider.sync_error = ""
        
        return SyncResponse(
            count=len(models),
            message=f"已同步 {len(models)} 个模型",
        )
    except Exception as e:
        error_msg = str(e)
        provider.sync_error = error_msg
        logger.error(f"模型同步失败 ({provider.name}): {error_msg}")
        return SyncResponse(count=len(provider.models), error=error_msg)


@router.post("/{pid}/test", summary="测试连接")
@limiter.limit("20/minute")
async def test_connection(request: Request, pid: str, token: dict = Depends(verify_token)):
    manager = get_dynamic_provider_manager()
    provider = manager.get(pid)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    try:
        if provider.protocol.value == "anthropic":
            url = f"{provider.base_url}/messages"
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
        else:
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
                return TestResponse(success=True, message="连接成功")
            elif resp.status_code == 401:
                return TestResponse(success=False, message="API Key 无效")
            elif resp.status_code == 403:
                return TestResponse(success=False, message="权限不足")
            elif resp.status_code == 429:
                return TestResponse(success=False, message="请求频率过高")
            else:
                return TestResponse(success=False, message=f"HTTP {resp.status_code}: {resp.text[:100]}")
    except httpx.TimeoutException:
        return TestResponse(success=False, message="请求超时")
    except Exception as e:
        return TestResponse(success=False, message=f"连接失败: {str(e)}")
