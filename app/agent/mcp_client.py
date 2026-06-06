"""
MCP Client - Model Context Protocol 客户端

支持两种传输方式：
- stdio: 启动子进程，通过 stdin/stdout 通信（JSON-RPC 2.0）
- HTTP: 通过 HTTP POST 发送 JSON-RPC 请求

用法：
    from app.agent.mcp_client import MCPClientManager

    manager = MCPClientManager()
    await manager.load_servers()  # 从配置文件加载 MCP Server
    tools = manager.get_tools_as_specialist_format()  # 获取工具，合并到 ReActEngine
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from typing import Dict, Any, List, Optional, Callable

import httpx

logger = logging.getLogger(__name__)

# MCP 配置文件路径
MCP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../data/mcp_servers.json")

# MCP 连接超时（秒）
MCP_CONNECT_TIMEOUT = 30
MCP_CALL_TIMEOUT = 60


class MCPError(Exception):
    """MCP 调用错误"""
    pass


class MCPServerConnection:
    """单个 MCP Server 连接"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio")
        self._process: Optional[asyncio.subprocess.Process] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._url: Optional[str] = None
        self._initialized = False
        self._tools: List[Dict] = []
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """连接到 MCP Server"""
        try:
            if self.transport == "stdio":
                return await self._connect_stdio()
            elif self.transport == "http":
                return await self._connect_http()
            else:
                logger.error(f"[MCP:{self.name}] 不支持的传输方式: {self.transport}")
                return False
        except Exception as e:
            logger.error(f"[MCP:{self.name}] 连接失败: {e}")
            return False

    async def _connect_stdio(self) -> bool:
        """通过 stdio 连接"""
        command = self.config.get("command")
        args = self.config.get("args", [])
        env = self.config.get("env")

        if not command:
            logger.error(f"[MCP:{self.name}] 缺少 command 配置")
            return False

        # 如果 command 不是绝对路径，尝试查找
        if not os.path.isabs(command):
            full_command = shutil.which(command)
            if not full_command:
                logger.error(f"[MCP:{self.name}] 找不到命令: {command}")
                return False
            command = full_command

        cmd = [command] + args
        logger.info(f"[MCP:{self.name}] 启动: {' '.join(cmd)}")

        merged_env = {**os.environ}
        if env:
            merged_env.update(env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merged_env,
            )
        except FileNotFoundError:
            logger.error(f"[MCP:{self.name}] 命令不存在: {command}")
            return False

        # 启动读取任务
        self._read_task = asyncio.create_task(self._read_loop())

        # 发送 initialize
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "monkeycode-agent", "version": "1.0.0"}
        })

        if result is None:
            logger.error(f"[MCP:{self.name}] initialize 失败")
            await self.disconnect()
            return False

        # 发送 initialized 通知
        await self._send_notification("notifications/initialized", {})
        self._initialized = True
        logger.info(f"[MCP:{self.name}] stdio 连接成功")
        return True

    async def _connect_http(self) -> bool:
        """通过 HTTP 连接"""
        self._url = self.config.get("url")
        if not self._url:
            logger.error(f"[MCP:{self.name}] 缺少 url 配置")
            return False

        self._http_client = httpx.AsyncClient(timeout=MCP_CALL_TIMEOUT)
        self._initialized = True
        logger.info(f"[MCP:{self.name}] HTTP 连接就绪: {self._url}")
        return True

    async def _read_loop(self):
        """stdio 模式下的读取循环"""
        if not self._process or not self._process.stdout:
            return
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.debug(f"[MCP:{self.name}] 非 JSON 输出: {line[:100]}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[MCP:{self.name}] 读取循环异常: {e}")

    def _handle_message(self, msg: Dict):
        """处理收到的 JSON-RPC 消息"""
        msg_id = msg.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if "error" in msg:
                future.set_exception(MCPError(json.dumps(msg["error"])))
            else:
                future.set_result(msg.get("result"))

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: Dict, timeout: float = MCP_CONNECT_TIMEOUT) -> Optional[Any]:
        """发送 JSON-RPC 请求并等待响应"""
        req_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }

        if self.transport == "stdio":
            return await self._send_stdio_request(req_id, message, timeout)
        else:
            return await self._send_http_request(message, timeout)

    async def _send_stdio_request(self, req_id: int, message: Dict, timeout: float) -> Optional[Any]:
        """通过 stdio 发送请求"""
        if not self._process or not self._process.stdin:
            return None

        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            logger.error(f"[MCP:{self.name}] 请求超时: {message['method']}")
            return None

    async def _send_http_request(self, message: Dict, timeout: float) -> Optional[Any]:
        """通过 HTTP 发送请求"""
        if not self._http_client or not self._url:
            return None
        try:
            resp = await self._http_client.post(
                self._url,
                json=message,
                timeout=timeout
            )
            resp.raise_for_status()
            result = resp.json()
            if "error" in result:
                logger.error(f"[MCP:{self.name}] RPC 错误: {result['error']}")
                return None
            return result.get("result")
        except Exception as e:
            logger.error(f"[MCP:{self.name}] HTTP 请求失败: {e}")
            return None

    async def _send_notification(self, method: str, params: Dict):
        """发送 JSON-RPC 通知（无响应）"""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        if self.transport == "stdio" and self._process and self._process.stdin:
            data = json.dumps(message) + "\n"
            self._process.stdin.write(data.encode("utf-8"))
            await self._process.stdin.drain()

    async def list_tools(self) -> List[Dict]:
        """获取 MCP Server 提供的工具列表"""
        if not self._initialized:
            return []

        result = await self._send_request("tools/list", {})
        if result is None:
            return []

        self._tools = result.get("tools", [])
        logger.info(f"[MCP:{self.name}] 发现 {len(self._tools)} 个工具")
        return self._tools

    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """调用 MCP Server 的工具"""
        if not self._initialized:
            raise MCPError(f"MCP Server {self.name} 未连接")

        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        }, timeout=MCP_CALL_TIMEOUT)

        if result is None:
            raise MCPError(f"工具调用失败: {tool_name}")

        # MCP tools/call 返回 {"content": [...], "isError": bool}
        if result.get("isError"):
            content = result.get("content", [])
            error_text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            raise MCPError(f"工具执行错误: {error_text}")

        # 提取文本内容
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if len(texts) > 1 else (texts[0] if texts else str(content))

    async def disconnect(self):
        """断开连接"""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._process:
            try:
                self._process.stdin.close()
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except Exception as e:
                logger.debug(f"MCP 进程优雅退出失败，强制 kill：{e}")
                try:
                    self._process.kill()
                except Exception as kill_err:
                    logger.debug(f"MCP 进程 kill 失败：{kill_err}")
                    pass
            self._process = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._initialized = False
        logger.info(f"[MCP:{self.name}] 已断开连接")

    def get_tools_as_specialist_format(self) -> Dict[str, Dict]:
        """将 MCP 工具转换为 SPECIALIST_TOOLS 格式"""
        tools = {}
        for tool_def in self._tools:
            name = tool_def.get("name", "")
            if not name:
                continue

            # 添加 MCP 前缀避免与内置工具冲突
            prefixed_name = f"mcp_{self.name}_{name}"

            # 转换 JSON Schema 到 params 格式
            input_schema = tool_def.get("inputSchema", {})
            properties = input_schema.get("properties", {})
            params = {}
            for param_name, param_def in properties.items():
                param_type = param_def.get("type", "string")
                description = param_def.get("description", "")
                params[param_name] = f"{param_type}" + (f" ({description})" if description else "")

            description = tool_def.get("description", f"MCP 工具: {name}")

            # 创建调用闭包
            server_name = self.name
            tool_name = name

            async def _mcp_tool_fn(project_path: str = "", _sn=server_name, _tn=tool_name, **kwargs):
                manager = MCPClientManager._instance
                if not manager:
                    return {"success": False, "error": "MCPClientManager 未初始化"}
                server = manager.get_server(_sn)
                if not server:
                    return {"success": False, "error": f"MCP Server {_sn} 不存在"}
                try:
                    result = await server.call_tool(_tn, kwargs)
                    return {"success": True, "result": result}
                except MCPError as e:
                    return {"success": False, "error": str(e)}

            tools[prefixed_name] = {
                "fn": _mcp_tool_fn,
                "description": f"[MCP:{self.name}] {description}",
                "params": params,
                "_mcp_source": self.name,
                "_mcp_tool_name": name,
            }

        return tools


class MCPClientManager:
    """MCP 客户端管理器 - 管理多个 MCP Server 连接"""

    _instance: Optional["MCPClientManager"] = None

    def __init__(self):
        self._servers: Dict[str, MCPServerConnection] = {}
        self._all_tools: Dict[str, Dict] = {}
        MCPClientManager._instance = self

    @classmethod
    def get_instance(cls) -> Optional["MCPClientManager"]:
        return cls._instance

    async def load_servers(self, config_path: Optional[str] = None) -> int:
        """从配置文件加载 MCP Server

        Returns:
            成功连接的 Server 数量
        """
        path = config_path or MCP_CONFIG_PATH
        if not os.path.exists(path):
            logger.info(f"MCP 配置文件不存在: {path}，跳过 MCP 加载")
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"读取 MCP 配置失败: {e}")
            return 0

        servers_config = config.get("mcp_servers", {})
        if not servers_config:
            logger.info("MCP 配置中无 mcp_servers，跳过")
            return 0

        connected = 0
        for name, server_config in servers_config.items():
            if not server_config.get("enabled", True):
                logger.info(f"[MCP:{name}] 已禁用，跳过")
                continue

            server = MCPServerConnection(name, server_config)
            if await server.connect():
                tools = await server.list_tools()
                if tools:
                    self._servers[name] = server
                    specialist_tools = server.get_tools_as_specialist_format()
                    self._all_tools.update(specialist_tools)
                    connected += 1
                else:
                    await server.disconnect()
            else:
                logger.warning(f"[MCP:{name}] 连接失败，跳过")

        logger.info(f"MCP 加载完成: {connected}/{len(servers_config)} 个 Server 连接成功，共 {len(self._all_tools)} 个工具")
        return connected

    def get_server(self, name: str) -> Optional[MCPServerConnection]:
        return self._servers.get(name)

    def get_all_tools(self) -> Dict[str, Dict]:
        """获取所有 MCP 工具（SPECIALIST_TOOLS 格式）"""
        return self._all_tools

    def get_tool_names(self) -> List[str]:
        return list(self._all_tools.keys())

    async def disconnect_all(self):
        """断开所有连接"""
        for server in self._servers.values():
            await server.disconnect()
        self._servers.clear()
        self._all_tools.clear()
        logger.info("所有 MCP Server 已断开")

    @staticmethod
    def create_default_config(path: Optional[str] = None) -> str:
        """创建默认配置文件"""
        config_path = path or MCP_CONFIG_PATH
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        default_config = {
            "mcp_servers": {
                "filesystem": {
                    "enabled": False,
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
                    "description": "文件系统操作（需要 Node.js）"
                },
                "brave-search": {
                    "enabled": False,
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                    "env": {"BRAVE_API_KEY": "your-api-key-here"},
                    "description": "Brave 搜索（需要 API Key）"
                }
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        logger.info(f"已创建默认 MCP 配置: {config_path}")
        return config_path
