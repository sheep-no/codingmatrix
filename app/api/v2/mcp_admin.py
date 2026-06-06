"""
MCP Server 管理接口

功能：
1. 获取所有 MCP Server 配置
2. 添加/更新/删除 MCP Server
3. 测试 MCP Server 连接
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Optional, List

from app.agent.mcp_client import MCPClientManager, MCP_CONFIG_PATH
from app.utils.security import require_superadmin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP 管理"])


# ==================== 请求模型 ====================

class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Server 名称（唯一标识）")
    transport: str = Field("stdio", description="传输方式: stdio / http")
    enabled: bool = Field(True, description="是否启用")
    command: Optional[str] = Field(None, description="stdio 模式的命令路径")
    args: Optional[List[str]] = Field(default_factory=list, description="命令参数")
    env: Optional[Dict[str, str]] = Field(default_factory=dict, description="环境变量")
    url: Optional[str] = Field(None, description="HTTP 模式的 URL")
    description: Optional[str] = Field("", description="描述")


class MCPServerUpdate(BaseModel):
    transport: Optional[str] = None
    enabled: Optional[bool] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    description: Optional[str] = None


# ==================== 工具函数 ====================

def _load_config() -> Dict:
    """加载 MCP 配置"""
    import json, os
    if not os.path.exists(MCP_CONFIG_PATH):
        return {"mcp_servers": {}}
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"mcp_servers": {}}


def _save_config(config: Dict) -> bool:
    """保存 MCP 配置"""
    import json, os
    try:
        os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存 MCP 配置失败: {e}")
        return False


# ==================== 接口 ====================

@router.get("/servers")
async def list_mcp_servers(token: dict = Depends(require_superadmin)):
    """获取所有 MCP Server 配置"""
    config = _load_config()
    servers = config.get("mcp_servers", {})
    result = []
    for name, server_config in servers.items():
        result.append({
            "name": name,
            "transport": server_config.get("transport", "stdio"),
            "enabled": server_config.get("enabled", True),
            "command": server_config.get("command"),
            "args": server_config.get("args", []),
            "env": {k: "***" if k.upper().endswith(("KEY", "SECRET", "TOKEN", "PASSWORD")) else v
                    for k, v in server_config.get("env", {}).items()},
            "url": server_config.get("url"),
            "description": server_config.get("description", ""),
        })
    return {"servers": result}


@router.post("/servers")
async def add_mcp_server(req: MCPServerCreate, token: dict = Depends(require_superadmin)):
    """添加 MCP Server"""
    config = _load_config()
    servers = config.get("mcp_servers", {})

    if req.name in servers:
        raise HTTPException(status_code=409, detail=f"MCP Server '{req.name}' 已存在")

    if req.transport == "stdio" and not req.command:
        raise HTTPException(status_code=400, detail="stdio 模式需要 command 参数")
    if req.transport == "http" and not req.url:
        raise HTTPException(status_code=400, detail="http 模式需要 url 参数")

    server_config = {
        "enabled": req.enabled,
        "transport": req.transport,
        "description": req.description,
    }
    if req.transport == "stdio":
        server_config["command"] = req.command
        server_config["args"] = req.args or []
        if req.env:
            server_config["env"] = req.env
    else:
        server_config["url"] = req.url

    servers[req.name] = server_config
    config["mcp_servers"] = servers

    if not _save_config(config):
        raise HTTPException(status_code=500, detail="保存配置失败")

    return {"success": True, "message": f"MCP Server '{req.name}' 已添加"}


@router.put("/servers/{name}")
async def update_mcp_server(name: str, req: MCPServerUpdate, token: dict = Depends(require_superadmin)):
    """更新 MCP Server 配置"""
    config = _load_config()
    servers = config.get("mcp_servers", {})

    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP Server '{name}' 不存在")

    server_config = servers[name]

    if req.transport is not None:
        server_config["transport"] = req.transport
    if req.enabled is not None:
        server_config["enabled"] = req.enabled
    if req.command is not None:
        server_config["command"] = req.command
    if req.args is not None:
        server_config["args"] = req.args
    if req.env is not None:
        server_config["env"] = req.env
    if req.url is not None:
        server_config["url"] = req.url
    if req.description is not None:
        server_config["description"] = req.description

    servers[name] = server_config
    config["mcp_servers"] = servers

    if not _save_config(config):
        raise HTTPException(status_code=500, detail="保存配置失败")

    return {"success": True, "message": f"MCP Server '{name}' 已更新"}


@router.delete("/servers/{name}")
async def delete_mcp_server(name: str, token: dict = Depends(require_superadmin)):
    """删除 MCP Server"""
    config = _load_config()
    servers = config.get("mcp_servers", {})

    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP Server '{name}' 不存在")

    del servers[name]
    config["mcp_servers"] = servers

    if not _save_config(config):
        raise HTTPException(status_code=500, detail="保存配置失败")

    return {"success": True, "message": f"MCP Server '{name}' 已删除"}


@router.post("/servers/{name}/toggle")
async def toggle_mcp_server(name: str, token: dict = Depends(require_superadmin)):
    """切换 MCP Server 启用/禁用状态"""
    config = _load_config()
    servers = config.get("mcp_servers", {})

    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP Server '{name}' 不存在")

    current = servers[name].get("enabled", True)
    servers[name]["enabled"] = not current
    config["mcp_servers"] = servers

    if not _save_config(config):
        raise HTTPException(status_code=500, detail="保存配置失败")

    return {"success": True, "enabled": not current}


@router.post("/servers/{name}/test")
async def test_mcp_server(name: str, token: dict = Depends(require_superadmin)):
    """测试 MCP Server 连接"""
    config = _load_config()
    servers = config.get("mcp_servers", {})

    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP Server '{name}' 不存在")

    server_config = servers[name]
    from app.agent.mcp_client import MCPServerConnection

    server = MCPServerConnection(name, server_config)
    try:
        connected = await server.connect()
        if not connected:
            return {"success": False, "error": "连接失败，请检查配置"}

        tools = await server.list_tools()
        await server.disconnect()

        return {
            "success": True,
            "tools_count": len(tools),
            "tools": [{"name": t.get("name"), "description": t.get("description", "")} for t in tools]
        }
    except Exception as e:
        await server.disconnect()
        return {"success": False, "error": str(e)}
