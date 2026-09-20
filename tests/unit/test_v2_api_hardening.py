"""v2 管理面的输入校验、白名单与权限边界回归。

覆盖本轮核实后修复的缺陷：
- 批量/恢复配置写入必须复用单点端点的键白名单
- 限流配置的 limit/window 必须为正数
- 备份时间戳必须匹配固定格式
- nginx 配置路径按路径段比较，拒绝 /etc/nginx-evil 前缀碰撞
- nginx 读写配置/备份端点要求 admin 及以上权限
- MCP 配置写入使用原子替换
"""

import json

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.api.v2 import guardian_router, mcp_admin
from app.models.server_config import ServerConfig
from app.utils.security import verify_token


# ==================== 配置键白名单 ====================

def test_valid_config_keys_single_source():
    """白名单直接来自 ServerConfig.DEFAULT_CONFIGS，避免多处硬编码漂移。"""
    assert set(guardian_router.VALID_CONFIG_KEYS) == set(ServerConfig.DEFAULT_CONFIGS)


@pytest.mark.asyncio
async def test_batch_update_rejects_unknown_key():
    request = guardian_router.BatchConfigUpdateRequest(
        configs={"docker_image": "alpha", "rm_rf_everything": "1"}
    )

    with pytest.raises(guardian_router.HTTPException) as error:
        await guardian_router.batch_update_configs(
            request=request, token={"sub": "1", "permission_level": "superadmin"}
        )

    assert error.value.status_code == 400
    assert "rm_rf_everything" in error.value.detail


@pytest.mark.asyncio
async def test_restore_rejects_unknown_key():
    backup_data = {"configs": {"arbitrary_key": {"value": "x", "description": ""}}}

    with pytest.raises(guardian_router.HTTPException) as error:
        await guardian_router.restore_backup(
            backup_data=backup_data,
            token={"sub": "1", "permission_level": "superadmin"},
        )

    assert error.value.status_code == 400
    assert "arbitrary_key" in error.value.detail


@pytest.mark.asyncio
async def test_restore_accepts_whitelisted_keys():
    """白名单内的键应放行到数据库写入阶段（此处以假会话断言越过了校验）。"""
    class _FakeResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, statement):
            return _FakeResult()

        def add(self, instance):
            self.added.append(instance)

        async def commit(self):
            self.committed = True

    fake = _FakeSession()

    class _SessionFactory:
        def __call__(self):
            return fake

    original = guardian_router.async_session
    guardian_router.async_session = _SessionFactory()
    try:
        result = await guardian_router.restore_backup(
            backup_data={"configs": {"docker_image": {"value": "alpha"}}},
            token={"sub": "1", "permission_level": "superadmin"},
        )
    finally:
        guardian_router.async_session = original

    assert result["restored_count"] == 1
    assert fake.committed is True


# ==================== 限流配置校验 ====================

@pytest.mark.parametrize("limit,window", [(0, 60), (-1, 60), (10, 0), (10, -5)])
def test_rate_limit_update_rejects_non_positive(limit, window):
    with pytest.raises(ValidationError):
        guardian_router.RateLimitUpdate(limit=limit, window=window)


def test_endpoint_rate_limit_rejects_non_positive_window():
    with pytest.raises(ValidationError):
        guardian_router.EndpointRateLimitUpdate(endpoint="/api/x", limit=5, window=0)


def test_rate_limit_update_accepts_positive():
    assert guardian_router.RateLimitUpdate(limit=10, window=60).limit == 10


# ==================== nginx 路径边界 ====================

def test_allowed_nginx_path_accepts_inside_allowlist():
    from app.api.v2 import nginx_api

    assert nginx_api._is_allowed_nginx_config_path("/etc/nginx/conf.d/app.conf") is True
    assert nginx_api._is_allowed_nginx_config_path("/usr/local/nginx/conf/nginx.conf") is True


def test_allowed_nginx_path_rejects_prefix_collision():
    from app.api.v2 import nginx_api

    assert nginx_api._is_allowed_nginx_config_path("/etc/nginx-evil/x.conf") is False
    assert nginx_api._is_allowed_nginx_config_path("/tmp/x.conf") is False


def test_nginx_config_endpoint_requires_admin():
    app.dependency_overrides[verify_token] = lambda: {"sub": "2", "permission_level": "normal"}
    try:
        client = TestClient(app)
        resp = client.get("/api/v2/nginx/config", params={"config_path": "/etc/nginx/nginx.conf"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403


def test_nginx_config_endpoint_rejects_prefix_collision_for_admin():
    app.dependency_overrides[verify_token] = lambda: {"sub": "1", "permission_level": "admin"}
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v2/nginx/config", params={"config_path": "/etc/nginx-evil/evil.conf"}
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "不允许访问" in resp.text


# ==================== 备份时间戳 ====================

@pytest.mark.asyncio
async def test_download_backup_rejects_traversal_timestamp():
    with pytest.raises(guardian_router.HTTPException) as error:
        await guardian_router.download_backup(
            timestamp="../../etc/passwd",
            token={"sub": "1", "permission_level": "admin"},
        )

    assert error.value.status_code == 400


# ==================== MCP 配置原子写入 ====================

def test_mcp_save_config_is_atomic(tmp_path):
    config_path = tmp_path / "mcp_servers.json"
    payload = {"mcp_servers": {"srv": {"transport": "stdio", "command": "echo"}}}

    original = mcp_admin.MCP_CONFIG_PATH
    mcp_admin.MCP_CONFIG_PATH = str(config_path)
    try:
        assert mcp_admin._save_config(payload) is True
    finally:
        mcp_admin.MCP_CONFIG_PATH = original

    assert json.loads(config_path.read_text(encoding="utf-8")) == payload
    assert list(tmp_path.glob("*.tmp")) == []
