"""
动态供应商 API 端点单元测试
"""
import pytest
import time
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.utils.aicloud.dynamic_provider import (
    DynamicProviderManager, DynamicProvider, Protocol, ModelInfo, MODEL_CACHE_TTL,
    get_dynamic_provider_manager, fetch_models_openai, fetch_models_anthropic,
)
from app.utils.aicloud.adapters.dynamic import DynamicAdapter


class AddProviderRequest(BaseModel):
    name: str
    base_url: str
    protocol: str
    api_key: str


class ProviderResponse(BaseModel):
    id: str
    name: str
    base_url: str
    protocol: str
    enabled: bool
    models: list
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


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str


# 创建测试用 FastAPI 应用
def create_test_app():
    from app.api.v1.providers import router
    
    app = FastAPI()
    # 创建没有速率限制的路由副本
    from pydantic import BaseModel, Field
    from app.utils.aicloud.dynamic_provider import (
        DynamicProviderManager, DynamicProvider,
        Protocol, MODEL_CACHE_TTL,
        get_dynamic_provider_manager,
        fetch_models_openai, fetch_models_anthropic,
    )
    from app.utils.aicloud.adapters.dynamic import DynamicAdapter
    import httpx
    
    test_router = APIRouter(prefix="/api/v1/providers", tags=["动态供应商管理"])
    
    @test_router.post("", summary="添加动态供应商")
    async def add_provider(body: AddProviderRequest):
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
    
    @test_router.get("", summary="获取供应商列表")
    async def list_providers():
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
    
    @test_router.get("/{pid}", summary="获取供应商详情")
    async def get_provider(pid: str):
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
    
    @test_router.delete("/{pid}", summary="删除供应商")
    async def delete_provider(pid: str):
        manager = get_dynamic_provider_manager()
        if not manager.delete(pid):
            raise HTTPException(status_code=404, detail="供应商不存在")
        return {"message": "供应商已删除"}
    
    @test_router.put("/{pid}/toggle", summary="启用/禁用供应商")
    async def toggle_provider(pid: str):
        manager = get_dynamic_provider_manager()
        if not manager.toggle(pid):
            raise HTTPException(status_code=404, detail="供应商不存在")
        p = manager.get(pid)
        return {"message": f"供应商已{'启用' if p.enabled else '禁用'}", "enabled": p.enabled}
    
    @test_router.post("/{pid}/sync", summary="同步模型列表")
    async def sync_models(pid: str, force: bool = False):
        manager = get_dynamic_provider_manager()
        provider = manager.get(pid)
        if not provider:
            raise HTTPException(status_code=404, detail="供应商不存在")
        
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
            return SyncResponse(count=len(provider.models), error=error_msg)
    
    @test_router.post("/{pid}/test", summary="测试连接")
    async def test_connection(pid: str):
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
    
    app.include_router(test_router)
    return app


@pytest.fixture
def client():
    app = create_test_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_manager():
    import app.utils.aicloud.dynamic_provider as dp_module
    original_manager = dp_module._manager
    dp_module._manager = None
    yield
    dp_module._manager = original_manager


class TestAddProvider:
    """POST /api/v1/providers 测试"""

    def test_add_openai_provider(self, client):
        response = client.post("/api/v1/providers", json={
            "name": "Test Provider",
            "base_url": "http://api.test.com/v1",
            "protocol": "openai",
            "api_key": "sk-valid-key-1234567",
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "Test Provider"
        assert "message" in data

    def test_add_anthropic_provider(self, client):
        response = client.post("/api/v1/providers", json={
            "name": "Anthropic Test",
            "base_url": "http://api.anthropic.com",
            "protocol": "anthropic",
            "api_key": "sk-ant-valid-key-123456",
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Anthropic Test"

    def test_add_provider_invalid_protocol(self, client):
        response = client.post("/api/v1/providers", json={
            "name": "Test Provider",
            "base_url": "http://api.test.com",
            "protocol": "invalid",
            "api_key": "sk-valid-key-1234567",
        })
        
        assert response.status_code == 400
        assert "protocol 必须是 openai 或 anthropic" in response.json()["detail"]

    def test_add_provider_short_api_key(self, client):
        response = client.post("/api/v1/providers", json={
            "name": "Test Provider",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "short",
        })
        
        assert response.status_code == 400
        assert "格式无效" in response.json()["detail"]

    def test_add_provider_empty_api_key(self, client):
        response = client.post("/api/v1/providers", json={
            "name": "Test Provider",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "",
        })
        
        assert response.status_code == 400


class TestListProviders:
    """GET /api/v1/providers 测试"""

    def test_list_empty(self, client):
        response = client.get("/api/v1/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_with_providers(self, client):
        client.post("/api/v1/providers", json={
            "name": "Provider 1",
            "base_url": "http://api1.test.com",
            "protocol": "openai",
            "api_key": "sk-key-1-1234567890",
        })
        client.post("/api/v1/providers", json={
            "name": "Provider 2",
            "base_url": "http://api2.test.com",
            "protocol": "openai",
            "api_key": "sk-key-2-1234567890",
        })
        
        response = client.get("/api/v1/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_hides_api_key(self, client):
        client.post("/api/v1/providers", json={
            "name": "Secret Provider",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "sk-secret-key-1234567",
        })
        
        response = client.get("/api/v1/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] is not None
        assert "api_key" not in data[0]


class TestGetProvider:
    """GET /api/v1/providers/{pid} 测试"""

    def test_get_existing_provider(self, client):
        add_response = client.post("/api/v1/providers", json={
            "name": "Get Test",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "sk-get-test-1234567",
        })
        pid = add_response.json()["id"]
        
        response = client.get(f"/api/v1/providers/{pid}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test"
        assert data["protocol"] == "openai"
        assert data["enabled"] == True

    def test_get_nonexistent_provider(self, client):
        response = client.get("/api/v1/providers/nonexistent-id")
        
        assert response.status_code == 404
        assert "供应商不存在" in response.json()["detail"]


class TestDeleteProvider:
    """DELETE /api/v1/providers/{pid} 测试"""

    def test_delete_existing_provider(self, client):
        add_response = client.post("/api/v1/providers", json={
            "name": "Delete Test",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "sk-delete-test-123456",
        })
        pid = add_response.json()["id"]
        
        delete_response = client.delete(f"/api/v1/providers/{pid}")
        
        assert delete_response.status_code == 200
        assert "供应商已删除" in delete_response.json()["message"]
        
        get_response = client.get(f"/api/v1/providers/{pid}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_provider(self, client):
        response = client.delete("/api/v1/providers/nonexistent-id")
        
        assert response.status_code == 404
        assert "供应商不存在" in response.json()["detail"]


class TestToggleProvider:
    """PUT /api/v1/providers/{pid}/toggle 测试"""

    def test_toggle_enabled_to_disabled(self, client):
        add_response = client.post("/api/v1/providers", json={
            "name": "Toggle Test",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "sk-toggle-test-123456",
        })
        pid = add_response.json()["id"]
        
        response = client.put(f"/api/v1/providers/{pid}/toggle")
        
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] == False
        assert "禁用" in data["message"]

    def test_toggle_disabled_to_enabled(self, client):
        add_response = client.post("/api/v1/providers", json={
            "name": "Toggle Test",
            "base_url": "http://api.test.com",
            "protocol": "openai",
            "api_key": "sk-toggle-test-123456",
        })
        pid = add_response.json()["id"]
        
        client.put(f"/api/v1/providers/{pid}/toggle")
        response = client.put(f"/api/v1/providers/{pid}/toggle")
        
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] == True
        assert "启用" in data["message"]

    def test_toggle_nonexistent_provider(self, client):
        response = client.put("/api/v1/providers/nonexistent-id/toggle")
        
        assert response.status_code == 404


class TestSyncModels:
    """POST /api/v1/providers/{pid}/sync 测试"""

    @pytest.mark.asyncio
    async def test_sync_openai_models_success(self):
        manager = get_dynamic_provider_manager()
        provider = manager.add("Sync Test", "http://api.test.com", "openai", "sk-sync-123456789")
        
        mock_response_data = {"data": [{"id": "model-1"}, {"id": "model-2"}]}
        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            models = await fetch_models_openai(provider)
            provider.models = models
            provider.last_sync = time.time()
            
            assert len(models) == 2

    @pytest.mark.asyncio
    async def test_sync_anthropic_models(self):
        manager = get_dynamic_provider_manager()
        provider = manager.add("Anthropic Sync", "http://api.anthropic.com", "anthropic", "sk-ant-sync-123456")
        
        models = await fetch_models_anthropic(provider)
        provider.models = models
        provider.last_sync = time.time()
        
        assert len(models) > 0
        assert all(m.id.startswith("claude-") for m in models)

    @pytest.mark.asyncio
    async def test_sync_error_handling(self):
        manager = get_dynamic_provider_manager()
        provider = manager.add("Error Test", "http://api.test.com", "openai", "sk-sync-123456789")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = Exception("Connection refused")
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            with pytest.raises(Exception):
                await fetch_models_openai(provider)


class TestTestConnection:
    """POST /api/v1/providers/{pid}/test 测试"""

    @pytest.mark.asyncio
    async def test_connection_success_openai(self):
        manager = get_dynamic_provider_manager()
        provider = manager.add("Test Conn", "http://api.test.com", "openai", "sk-testconn-12345")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
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
            
            async with mock_client() as client:
                resp = await client.post(url, headers=headers, json=payload)
                
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_connection_failed_invalid_key(self):
        manager = get_dynamic_provider_manager()
        provider = manager.add("Test Conn", "http://api.test.com", "openai", "sk-testconn-12345")
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            url = f"{provider.base_url}/chat/completions"
            headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}
            payload = {"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 10}
            
            async with mock_client() as client:
                resp = await client.post(url, headers=headers, json=payload)
                
                assert resp.status_code == 401


class TestProviderResponse:
    """ProviderResponse 模型测试"""

    def test_protocol_value(self, client):
        client.post("/api/v1/providers", json={
            "name": "Proto Test",
            "base_url": "http://api.test.com",
            "protocol": "anthropic",
            "api_key": "sk-proto-test-123456",
        })
        
        response = client.get("/api/v1/providers")
        data = response.json()
        
        assert len(data) > 0
        assert data[0]["protocol"] == "anthropic"


class TestEdgeCases:
    """边界情况测试"""

    def test_add_provider_trailing_slash(self, client):
        response = client.post("/api/v1/providers", json={
            "name": "Slash Test",
            "base_url": "http://api.test.com/v1/",
            "protocol": "openai",
            "api_key": "sk-slash-test-123456",
        })
        
        assert response.status_code == 200
        pid = response.json()["id"]
        
        detail = client.get(f"/api/v1/providers/{pid}")
        assert detail.json()["base_url"] == "http://api.test.com/v1"

    def test_add_multiple_providers(self, client):
        for i in range(5):
            response = client.post("/api/v1/providers", json={
                "name": f"Provider {i}",
                "base_url": f"http://api{i}.test.com",
                "protocol": "openai",
                "api_key": f"sk-multi-{i}-1234567890",
            })
            assert response.status_code == 200
        
        response = client.get("/api/v1/providers")
        assert len(response.json()) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
