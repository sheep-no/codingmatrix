"""
API Key 管理接口

端点：
- GET /api/v1/public-key - 获取 RSA 公钥
- POST /api/v1/agent/apikey - 提交加密 Key
- POST /api/v1/agent/apikey/test - 测试 Key
- DELETE /api/v1/agent/apikey/{token} - 清除 Key
- GET /api/v1/agent/apikeys - 获取 Key 列表
- PUT /api/v1/agent/apikey/{token}/enabled - 启用/禁用 Key
"""
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from app.utils.crypto import get_rsa_key_manager
from app.utils.rate_limiter import limiter
from app.services.apikey_manager import (
    APIKeyManager, SUPPORTED_PROVIDERS, TTL_OPTIONS, get_apikey_manager
)
from app.services.provider_health import get_health_checker
from app.api.v1.auth import verify_token
import csv
import io
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent/apikey", tags=["API Key 管理"])


# --- 供应商 Base URL 映射 ---

_PROVIDER_BASE_URLS = {
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "deepseek": "https://api.deepseek.com/v1",
}

# OpenAI 兼容协议的供应商（支持 /v1/models 端点）
_OPENAI_COMPAT_PROVIDERS = {"siliconflow", "openai", "bailian", "glm", "deepseek"}


async def _sync_provider_models(provider: str, api_key: str):
    """同步供应商模型列表到 CustomProviderManager（后台执行）"""
    try:
        from app.services.custom_provider_manager import get_custom_provider_manager
        cp_manager = get_custom_provider_manager()
        
        base_url = _PROVIDER_BASE_URLS.get(provider)
        if not base_url:
            return
        
        protocol = "anthropic" if provider == "anthropic" else "openai"
        
        # 检查是否已有该供应商的条目（按 name 匹配）
        existing = None
        for p in cp_manager.providers.values():
            if p.name == f"user_{provider}":
                existing = p
                break
        
        if existing:
            # 更新 API Key
            existing.api_key = api_key
            existing.last_sync = 0  # 强制重新同步
            provider_id = existing.id
        else:
            # 创建新条目
            cp = cp_manager.add_provider(
                name=f"user_{provider}",
                base_url=base_url,
                protocol=protocol,
                api_key=api_key,
            )
            provider_id = cp.id
        
        # 同步模型列表
        await cp_manager.sync_models(provider_id)
        logger.info(f"用户供应商 {provider} 模型同步完成，provider_id={provider_id}")
    except Exception as e:
        logger.warning(f"用户供应商 {provider} 模型同步失败（不影响 Key 存储）：{e}")


# --- Pydantic 模型 ---

class SubmitKeyRequest(BaseModel):
    """提交 API Key 请求"""
    encrypted_key: str = Field(..., description="RSA 加密后的 API Key")
    provider: str = Field(..., description="供应商名称")
    ttl: int = Field(default=86400, description="TTL 秒数")
    remark: str = Field(default="", description="备注")

class SubmitKeyResponse(BaseModel):
    """提交 API Key 响应"""
    success: bool
    token: str
    message: str

class TestKeyRequest(BaseModel):
    """测试 API Key 请求"""
    token: str = Field(..., description="Key Token")

class TestKeyResponse(BaseModel):
    """测试 API Key 响应"""
    success: bool
    message: str
    models: list = Field(default_factory=list)

class BatchImportRequest(BaseModel):
    """批量导入请求"""
    keys: list = Field(..., description="Key 列表")

class BatchImportResponse(BaseModel):
    """批量导入响应"""
    success_count: int
    failed_count: int
    results: list

class BatchExportResponse(BaseModel):
    """批量导出响应"""
    format: str
    data: str
    count: int

class KeyMetadataResponse(BaseModel):
    """Key 元数据响应"""
    token: str
    provider: str
    remark: str
    status: str
    created_at: str
    expires_at: str
    ttl_seconds: int
    enabled: bool


def get_current_user_id(token: dict = Depends(verify_token)) -> str:
    """
    从 JWT token 中获取当前用户 ID
    """
    return token.get("sub", "default_user")


# --- API 端点 ---

@router.get("/public-key", summary="获取 RSA 公钥")
@limiter.limit("30/minute")
async def get_public_key(request: Request):
    """获取 RSA 公钥，用于前端加密 API Key"""
    try:
        key_manager = get_rsa_key_manager()
        public_key_pem = key_manager.get_public_key_pem()
        return {"public_key": public_key_pem}
    except Exception as e:
        logger.error(f"获取公钥失败：{e}")
        raise HTTPException(status_code=500, detail="获取公钥失败")


@router.post("", summary="提交加密 API Key", response_model=SubmitKeyResponse)
@limiter.limit("10/minute")
async def submit_key(request: Request, submit_request: SubmitKeyRequest, user_id: str = Depends(get_current_user_id)):
    """提交加密后的 API Key，后端解密后存入 Redis"""
    
    # 验证供应商
    if submit_request.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的供应商：{submit_request.provider}")
    
    # 验证 TTL - 支持预设选项或自定义秒数
    from app.services.apikey_manager import resolve_ttl, MAX_CUSTOM_TTL
    try:
        ttl_seconds = resolve_ttl(submit_request.ttl)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        # 解密 API Key
        key_manager = get_rsa_key_manager()
        api_key = key_manager.decrypt(submit_request.encrypted_key)
        
        if not api_key or len(api_key.strip()) < 10:
            raise HTTPException(status_code=400, detail="API Key 格式无效")
        
        # 存储到 Redis
        apikey_manager = get_apikey_manager()
        token = apikey_manager.store_key(
            user_id=user_id,
            provider=submit_request.provider,
            api_key=api_key.strip(),
            ttl=submit_request.ttl,  # 直接传递原始输入，由 resolve_ttl 解析
            remark=submit_request.remark,
        )
        
        # 获取元数据
        meta = apikey_manager.get_metadata(user_id, token)
        
        # 后台同步供应商模型列表（提取 context_length 等信息）
        if submit_request.provider in _OPENAI_COMPAT_PROVIDERS:
            asyncio.create_task(_sync_provider_models(submit_request.provider, api_key.strip()))
        
        return SubmitKeyResponse(
            success=True,
            token=token,
            message="API Key 提交成功",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"提交 Key 失败：{e}")
        raise HTTPException(status_code=500, detail="提交 Key 失败")


@router.post("/test", summary="测试 API Key", response_model=TestKeyResponse)
@limiter.limit("20/minute")
async def test_key(request: Request, test_request: TestKeyRequest, user_id: str = Depends(get_current_user_id)):
    """测试 API Key 是否有效"""
    
    try:
        # 获取 Key
        apikey_manager = get_apikey_manager()
        api_key = apikey_manager.get_key(user_id, test_request.token)
        
        if api_key is None:
            raise HTTPException(status_code=404, detail="Key 不存在或已过期")
        
        # 获取元数据
        meta = apikey_manager.get_metadata(user_id, test_request.token)
        if meta is None:
            raise HTTPException(status_code=404, detail="Key 不存在或已过期")
        
        # 测试连接
        health_checker = get_health_checker()
        success, message = await health_checker.check(meta.provider, api_key)
        
        # 更新状态
        if success:
            apikey_manager.update_status(user_id, test_request.token, "verified")
        else:
            apikey_manager.update_status(user_id, test_request.token, "invalid")
        
        return TestKeyResponse(success=success, message=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试 Key 失败：{e}")
        raise HTTPException(status_code=500, detail="测试 Key 失败")


@router.delete("/{token}", summary="清除 API Key")
@limiter.limit("10/minute")
async def delete_key(request: Request, token: str, user_id: str = Depends(get_current_user_id)):
    """立即清除 API Key"""
    
    try:
        apikey_manager = get_apikey_manager()
        success = apikey_manager.delete_key(user_id, token)
        
        if not success:
            raise HTTPException(status_code=404, detail="Key 不存在")
        
        return {"message": "Key 已清除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Key 失败：{e}")
        raise HTTPException(status_code=500, detail="删除 Key 失败")


@router.get("s", summary="获取 API Key 列表", response_model=list[KeyMetadataResponse])
@limiter.limit("30/minute")
async def list_keys(request: Request, user_id: str = Depends(get_current_user_id)):
    """获取用户所有 API Key 的元数据列表（不含 Key 本身）"""
    
    try:
        apikey_manager = get_apikey_manager()
        keys = apikey_manager.list_keys(user_id)
        
        return [
            KeyMetadataResponse(
                token=k.token,
                provider=k.provider,
                remark=k.remark,
                status=k.status,
                created_at=k.created_at,
                expires_at=k.expires_at,
                ttl_seconds=k.ttl_seconds,
                enabled=k.enabled,
            )
            for k in keys
        ]
    except Exception as e:
        logger.error(f"获取 Key 列表失败：{e}")
        raise HTTPException(status_code=500, detail="获取 Key 列表失败")


@router.put("/{token}/enabled", summary="启用/禁用 API Key")
@limiter.limit("20/minute")
async def update_enabled(request: Request, token: str, enabled: bool = True, user_id: str = Depends(get_current_user_id)):
    """启用或禁用 API Key"""
    
    try:
        apikey_manager = get_apikey_manager()
        success = apikey_manager.update_enabled(user_id, token, enabled)
        
        if not success:
            raise HTTPException(status_code=404, detail="Key 不存在")
        
        return {"message": f"Key 已{'启用' if enabled else '禁用'}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Key 状态失败：{e}")
        raise HTTPException(status_code=500, detail="更新 Key 状态失败")


class UpdateContextLengthsRequest(BaseModel):
    """更新模型 context_length 配置请求"""
    context_lengths: dict = Field(default_factory=dict, description="模型 context_length 配置 {model_id: context_length}")


@router.put("/{token}/context-lengths", summary="更新模型 context_length 配置")
@limiter.limit("20/minute")
async def update_context_lengths(
    request: Request,
    token: str,
    update_request: UpdateContextLengthsRequest,
    user_id: str = Depends(get_current_user_id)
):
    """更新 API Key 的模型 context_length 配置"""
    
    try:
        apikey_manager = get_apikey_manager()
        success = apikey_manager.update_context_lengths(user_id, token, update_request.context_lengths)
        
        if not success:
            raise HTTPException(status_code=404, detail="Key 不存在")
        
        return {"message": "context_length 配置已更新", "context_lengths": update_request.context_lengths}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 context_lengths 失败：{e}")
        raise HTTPException(status_code=500, detail="更新 context_length 配置失败")


class UpdateFallbackPreferenceRequest(BaseModel):
    """更新降级链偏好请求"""
    fallback_preference: str = Field(
        default="use_admin_default",
        description="降级链偏好: use_admin_default | custom | disabled"
    )
    custom_fallback_chain: list = Field(
        default_factory=list,
        description="自定义降级链模型列表（仅 fallback_preference='custom' 时生效）"
    )


@router.put("/{token}/fallback-preference", summary="更新降级链偏好")
@limiter.limit("20/minute")
async def update_fallback_preference(
    request: Request,
    token: str,
    update_request: UpdateFallbackPreferenceRequest,
    user_id: str = Depends(get_current_user_id)
):
    """更新 API Key 的降级链偏好

    - use_admin_default: 使用管理员配置的降级链（默认）
    - custom: 使用用户自定义的降级链
    - disabled: 禁用降级，只用自己的模型
    """
    valid = ("use_admin_default", "custom", "disabled")
    if update_request.fallback_preference not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"无效的偏好: {update_request.fallback_preference}，可选: {', '.join(valid)}"
        )

    try:
        apikey_manager = get_apikey_manager()
        success = apikey_manager.update_fallback_preference(
            user_id, token,
            update_request.fallback_preference,
            update_request.custom_fallback_chain if update_request.fallback_preference == "custom" else None,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Key 不存在")

        return {
            "message": "降级链偏好已更新",
            "fallback_preference": update_request.fallback_preference,
            "custom_fallback_chain": update_request.custom_fallback_chain if update_request.fallback_preference == "custom" else [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新降级链偏好失败：{e}")
        raise HTTPException(status_code=500, detail="更新降级链偏好失败")


@router.get("/{token}/fallback-preference", summary="获取降级链偏好")
@limiter.limit("60/minute")
async def get_fallback_preference(
    request: Request,
    token: str,
    user_id: str = Depends(get_current_user_id)
):
    """获取 API Key 的降级链偏好配置"""
    try:
        apikey_manager = get_apikey_manager()
        meta = apikey_manager.get_metadata(user_id, token)

        if not meta:
            raise HTTPException(status_code=404, detail="Key 不存在")

        return {
            "fallback_preference": meta.fallback_preference,
            "custom_fallback_chain": meta.custom_fallback_chain,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取降级链偏好失败：{e}")
        raise HTTPException(status_code=500, detail="获取降级链偏好失败")


@router.post("/batch/import", summary="批量导入 API Key")
@limiter.limit("5/minute")
async def batch_import(request: Request, import_request: BatchImportRequest, user_id: str = Depends(get_current_user_id)):
    """批量导入多个 API Key
    
    请求格式：
    {
        "keys": [
            {"provider": "siliconflow", "encrypted_key": "xxx", "ttl": "24h", "remark": "Key 1"},
            {"provider": "openai", "encrypted_key": "yyy", "ttl": "7d", "remark": "Key 2"}
        ]
    }
    
    返回成功和失败的数量及详情
    """
    results = []
    success_count = 0
    failed_count = 0
    
    try:
        apikey_manager = get_apikey_manager()
        
        for idx, key_data in enumerate(import_request.keys, 1):
            try:
                # 验证供应商
                provider = key_data.get('provider')
                if provider not in SUPPORTED_PROVIDERS:
                    raise ValueError(f"不支持的供应商：{provider}")
                
                # 验证必要字段
                if not key_data.get('encrypted_key'):
                    raise ValueError("缺少加密的 Key")
                
                ttl = key_data.get('ttl', '24h')
                if ttl not in [t[0] for t in TTL_OPTIONS]:
                    raise ValueError(f"不支持的 TTL: {ttl}")
                
                # 存储 Key
                token = apikey_manager.store_key(
                    user_id=user_id,
                    provider=provider,
                    encrypted_key=key_data['encrypted_key'],
                    ttl=ttl,
                    remark=key_data.get('remark', '')
                )
                
                results.append({
                    "index": idx,
                    "success": True,
                    "token": token,
                    "provider": provider,
                    "message": "导入成功"
                })
                success_count += 1
                
            except Exception as e:
                results.append({
                    "index": idx,
                    "success": False,
                    "provider": key_data.get('provider', 'unknown'),
                    "error": str(e)
                })
                failed_count += 1
        
        return BatchImportResponse(
            success_count=success_count,
            failed_count=failed_count,
            results=results
        )
        
    except Exception as e:
        logger.error(f"批量导入失败：{e}")
        raise HTTPException(status_code=500, detail="批量导入失败")


@router.get("/batch/export", summary="批量导出 API Key")
@limiter.limit("10/minute")
async def batch_export(request: Request, format: str = "json", user_id: str = Depends(get_current_user_id)):
    """批量导出 API Key 元数据（不导出 Key 本身）
    
    支持格式：json, csv
    
    返回：
    - format: 导出格式
    - data: 导出的数据
    - count: Key 数量
    """
    
    try:
        apikey_manager = get_apikey_manager()
        keys = apikey_manager.list_keys(user_id)
        
        if format == "json":
            # JSON 格式导出
            data = [
                {
                    "token": k.token,
                    "provider": k.provider,
                    "remark": k.remark,
                    "status": k.status,
                    "created_at": k.created_at,
                    "expires_at": k.expires_at,
                    "ttl_seconds": k.ttl_seconds,
                    "enabled": k.enabled
                }
                for k in keys
            ]
            return BatchExportResponse(
                format="json",
                data=json.dumps(data, ensure_ascii=False, indent=2),
                count=len(keys)
            )
        
        elif format == "csv":
            # CSV 格式导出
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 写入表头
            writer.writerow(['token', 'provider', 'remark', 'status', 'created_at', 'expires_at', 'ttl_seconds', 'enabled'])
            
            # 写入数据
            for k in keys:
                writer.writerow([
                    k.token,
                    k.provider,
                    k.remark,
                    k.status,
                    k.created_at,
                    k.expires_at,
                    k.ttl_seconds,
                    k.enabled
                ])
            
            return BatchExportResponse(
                format="csv",
                data=output.getvalue(),
                count=len(keys)
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式：{format}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量导出失败：{e}")
        raise HTTPException(status_code=500, detail="批量导出失败")
