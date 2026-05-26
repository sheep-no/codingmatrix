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
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from app.utils.crypto import get_rsa_key_manager
from app.utils.rate_limiter import limiter
from app.services.apikey_manager import (
    APIKeyManager, SUPPORTED_PROVIDERS, TTL_OPTIONS, get_apikey_manager
)
from app.services.provider_health import get_health_checker
import csv
import io
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent/apikey", tags=["API Key 管理"])


# --- 请求/响应模型 ---

class SubmitKeyRequest(BaseModel):
    """提交加密 Key 请求"""
    provider: str = Field(..., description="供应商名称")
    encrypted_key: str = Field(..., description="RSA 加密后的 Key (Base64)")
    ttl: str = Field(..., description="TTL 选项 (1h, 24h, 7d, 30d)")
    remark: str = Field(default="", description="备注")


class SubmitKeyResponse(BaseModel):
    """提交 Key 响应"""
    token: str
    provider: str
    expires_at: str


class TestKeyRequest(BaseModel):
    """测试 Key 请求"""
    token: str


class TestKeyResponse(BaseModel):
    """测试 Key 响应"""
    success: bool
    message: str


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


class BatchImportRequest(BaseModel):
    """批量导入请求"""
    keys: list[dict] = Field(..., description="Key 列表，每项包含 provider, encrypted_key, ttl, remark")


class BatchImportResponse(BaseModel):
    """批量导入响应"""
    success_count: int
    failed_count: int
    results: list[dict]


class BatchExportResponse(BaseModel):
    """批量导出响应"""
    format: str
    data: str
    count: int


# --- 辅助函数 ---

def get_current_user_id() -> str:
    """
    获取当前用户 ID
    
    TODO: 从认证中获取真实的 user_id
    临时使用固定值，实际应从 token/session 中获取
    """
    # 临时实现：从 request 中获取，或使用固定值
    return "default_user"


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
async def submit_key(request: Request, submit_request: SubmitKeyRequest):
    """提交加密后的 API Key，后端解密后存入 Redis"""
    user_id = get_current_user_id()
    
    # 验证供应商
    if submit_request.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的供应商：{submit_request.provider}")
    
    # 验证 TTL
    if submit_request.ttl not in TTL_OPTIONS:
        raise HTTPException(status_code=400, detail=f"无效的 TTL 选项：{submit_request.ttl}")
    
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
            ttl=submit_request.ttl,
            remark=submit_request.remark,
        )
        
        # 获取元数据
        meta = apikey_manager.get_metadata(user_id, token)
        
        return SubmitKeyResponse(
            token=token,
            provider=submit_request.provider,
            expires_at=meta.expires_at,
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
async def test_key(request: Request, test_request: TestKeyRequest):
    """测试 API Key 是否有效"""
    user_id = get_current_user_id()
    
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
async def delete_key(request: Request, token: str):
    """立即清除 API Key"""
    user_id = get_current_user_id()
    
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
async def list_keys(request: Request):
    """获取用户所有 API Key 的元数据列表（不含 Key 本身）"""
    user_id = get_current_user_id()
    
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
async def update_enabled(request: Request, token: str, enabled: bool = True):
    """启用或禁用 API Key"""
    user_id = get_current_user_id()
    
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


@router.post("/batch/import", summary="批量导入 API Key")
@limiter.limit("5/minute")
async def batch_import(request: Request, import_request: BatchImportRequest):
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
    user_id = get_current_user_id()
    results = []
    success_count = 0
    failed_count = 0
    
    try:
        apikey_manager = get_apikey_manager()
        
        for idx, key_data in enumerate(import_request.keys):
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
async def batch_export(request: Request, format: str = "json"):
    """批量导出 API Key 元数据（不导出 Key 本身）
    
    支持格式：json, csv
    
    返回：
    - format: 导出格式
    - data: 导出的数据
    - count: Key 数量
    """
    user_id = get_current_user_id()
    
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
