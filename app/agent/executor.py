"""
Agent Executor - 扩展执行器

支持多种工具类型：
- file_operation: 文件操作
- api_call: HTTP API 调用
- database: 数据库操作
- search: 网络搜索
- code_execution: 代码执行
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from app.agent.tools import (
    _tool_read_file as _impl_read_file,
    _tool_list_files as _impl_list_files,
    _tool_write_file as _impl_write_file,
    _tool_execute_code as _impl_execute_code,
    _tool_partial_update as _impl_partial_update,
    _tool_insert_content as _impl_insert_content,
    _tool_regex_replace as _impl_regex_replace,
    _tool_run_command as _impl_run_command,
    _tool_read_symbols as _impl_read_symbols,
    _tool_read_imports as _impl_read_imports,
    _tool_summarize_file as _impl_summarize_file,
    _tool_git_status as _impl_git_status,
    _tool_git_diff as _impl_git_diff,
    _tool_git_commit as _impl_git_commit,
    _tool_git_log as _impl_git_log,
    _tool_web_search as _impl_web_search,
    _tool_http_request as _impl_http_request,
    _tool_delete_files_by_pattern as _impl_delete_files_by_pattern,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    tool_name: str = ""


def _wrap_sync(func, project_path: str, params: Dict) -> ToolResult:
    """将同步工具函数适配为 ToolResult"""
    import time
    start = time.time()
    try:
        result = func(project_path, **params)
        return ToolResult(
            success=result.get("success", True) if isinstance(result, dict) else True,
            result=result,
            error=result.get("error") if isinstance(result, dict) and not result.get("success", True) else None,
            execution_time=time.time() - start
        )
    except Exception as e:
        return ToolResult(False, None, str(e), time.time() - start)


async def _wrap_async(func, project_path: str, params: Dict) -> ToolResult:
    """将异步工具函数适配为 ToolResult"""
    import time
    start = time.time()
    try:
        result = await func(project_path, **params)
        return ToolResult(
            success=result.get("success", True) if isinstance(result, dict) else True,
            result=result,
            error=result.get("error") if isinstance(result, dict) and not result.get("success", True) else None,
            execution_time=time.time() - start
        )
    except Exception as e:
        return ToolResult(False, None, str(e), time.time() - start)


class ToolRegistry:
    """工具注册表"""

    _instance = None
    _tools: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（测试用）"""
        cls._instance = None
        cls._tools = {}

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters_schema: Optional[Dict] = None
    ) -> None:
        self._tools[name] = {
            "func": func,
            "description": description,
            "parameters": parameters_schema or {}
        }

    def get(self, name: str) -> Optional[Callable]:
        tool = self._tools.get(name)
        return tool["func"] if tool else None

    def get_schema(self, name: str) -> Optional[Dict]:
        tool = self._tools.get(name)
        return tool["parameters"] if tool else None

    def list_tools(self) -> List[Dict[str, str]]:
        return [
            {"name": name, "description": t["description"]}
            for name, t in self._tools.items()
        ]

    def get_all_schemas(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            }
            for name, tool in self._tools.items()
        ]


class EnhancedExecutor:
    """增强的执行器

    使用 tools.py 中的统一工具实现，避免重复代码。
    """

    def __init__(self, file_operator=None, project_path: str = "."):
        self.file_operator = file_operator
        self.project_path = project_path
        self.tool_registry = ToolRegistry.get_instance()
        if not self.tool_registry._tools:
            self._register_default_tools()
        self._mcp_loaded = False

    async def load_mcp_tools(self) -> int:
        """加载 MCP 工具并注册到 ToolRegistry

        Returns:
            注册的 MCP 工具数量
        """
        if self._mcp_loaded:
            return 0
        try:
            from app.agent.mcp_client import MCPClientManager
            manager = MCPClientManager()
            connected = await manager.load_servers()
            if connected > 0:
                mcp_tools = manager.get_all_tools()
                for name, tool_info in mcp_tools.items():
                    self.tool_registry.register(
                        name=name,
                        func=tool_info["fn"],
                        description=tool_info["description"],
                        parameters_schema=self._params_to_schema(tool_info.get("params", {}))
                    )
                self._mcp_loaded = True
                return len(mcp_tools)
        except Exception as e:
            logger.debug(f"MCP 工具加载失败（可忽略）: {e}")
        self._mcp_loaded = True
        return 0

    @staticmethod
    def _params_to_schema(params: Dict[str, str]) -> Dict:
        """将 SPECIALIST_TOOLS 的 params 格式转为 JSON Schema"""
        if not params:
            return {"type": "object", "properties": {}, "required": []}
        properties = {}
        required = []
        for name, type_desc in params.items():
            type_str = type_desc.split(" ")[0] if " " in type_desc else type_desc
            json_type = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "object": "object", "list": "array"}.get(type_str, "string")
            properties[name] = {"type": json_type, "description": type_desc}
            if "(可选)" not in type_desc and "optional" not in type_desc.lower():
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}

    def _register_default_tools(self) -> None:
        """注册默认工具（从 tools.py 导入实现）"""

        def _adapt_sync(fn):
            """将 tools.py 的同步函数适配为 (params) -> ToolResult"""
            async def wrapper(params: Dict) -> ToolResult:
                return await asyncio.to_thread(_wrap_sync, fn, self.project_path, params)
            wrapper.__name__ = getattr(fn, '__name__', 'adapted')
            return wrapper

        def _adapt_async(fn):
            """将 tools.py 的异步函数适配为 (params) -> ToolResult"""
            async def wrapper(params: Dict) -> ToolResult:
                return await _wrap_async(fn, self.project_path, params)
            wrapper.__name__ = getattr(fn, '__name__', 'adapted')
            return wrapper

        tool_defs = [
            ("read_file", _adapt_sync(_impl_read_file), "读取文件内容（支持分页）", {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "description": "起始行号"},
                    "limit": {"type": "integer", "description": "行数"}
                },
                "required": ["file_path"]
            }),
            ("list_files", _adapt_sync(_impl_list_files), "列出目录结构", {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "目录路径"},
                    "max_depth": {"type": "integer", "description": "递归深度"}
                },
                "required": ["directory"]
            }),
            ("write_file", _adapt_sync(_impl_write_file), "写入文件内容", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"}
                },
                "required": ["path", "content"]
            }),
            ("execute_code", _adapt_sync(_impl_execute_code), "沙箱执行代码（Python/JavaScript）", {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "代码"},
                    "language": {"type": "string", "description": "语言: python/javascript"},
                    "timeout": {"type": "integer", "description": "超时秒数"}
                },
                "required": ["code"]
            }),
            ("partial_update", _adapt_sync(_impl_partial_update), "精准替换文件中的函数或代码块", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "target": {"type": "string", "description": "目标代码块文本"},
                    "replacement": {"type": "string", "description": "新代码块文本"},
                    "function_name": {"type": "string", "description": "目标函数名"}
                },
                "required": ["path"]
            }),
            ("insert_content", _adapt_sync(_impl_insert_content), "在文件指定位置插入内容", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要插入的内容"},
                    "line": {"type": "integer", "description": "行号（1-based）"},
                    "anchor": {"type": "string", "description": "锚点文本"}
                },
                "required": ["path", "content"]
            }),
            ("regex_replace", _adapt_sync(_impl_regex_replace), "基于正则表达式的批量替换", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径或 glob 模式"},
                    "pattern": {"type": "string", "description": "正则表达式"},
                    "replacement": {"type": "string", "description": "替换文本"},
                    "recursive": {"type": "boolean", "description": "是否递归"}
                },
                "required": ["path", "pattern", "replacement"]
            }),
            ("run_command", _adapt_sync(_impl_run_command), "执行终端命令", {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "命令"},
                    "cwd": {"type": "string", "description": "工作目录"},
                    "timeout": {"type": "integer", "description": "超时秒数"}
                },
                "required": ["command"]
            }),
            ("read_symbols", _adapt_sync(_impl_read_symbols), "提取文件的函数和类签名", {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"}
                },
                "required": ["file_path"]
            }),
            ("read_imports", _adapt_sync(_impl_read_imports), "提取文件的 import 语句", {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"}
                },
                "required": ["file_path"]
            }),
            ("summarize_file", _adapt_sync(_impl_summarize_file), "返回文件摘要", {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"}
                },
                "required": ["file_path"]
            }),
            ("git_status", _adapt_sync(_impl_git_status), "查看 Git 工作区状态", {
                "type": "object",
                "properties": {},
                "required": []
            }),
            ("git_diff", _adapt_sync(_impl_git_diff), "查看 Git 文件差异", {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "指定文件"},
                    "staged": {"type": "boolean", "description": "是否查看暂存区"}
                },
                "required": []
            }),
            ("git_commit", _adapt_sync(_impl_git_commit), "提交 Git 修改", {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "提交信息"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "要暂存的文件列表"}
                },
                "required": ["message"]
            }),
            ("git_log", _adapt_sync(_impl_git_log), "查看 Git 提交历史", {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "显示条数"},
                    "file_path": {"type": "string", "description": "过滤特定文件"}
                },
                "required": []
            }),
            ("web_search", _adapt_async(_impl_web_search), "搜索网络信息", {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "返回数量"}
                },
                "required": ["query"]
            }),
            ("http_request", _adapt_async(_impl_http_request), "发送 HTTP 请求（带 SSRF 防护）", {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "url": {"type": "string", "description": "请求 URL"},
                    "headers": {"type": "object", "description": "请求头"},
                    "body": {"type": "object", "description": "请求体"}
                },
                "required": ["method", "url"]
            }),
            ("delete_files_by_pattern", _adapt_sync(_impl_delete_files_by_pattern), "按模式批量删除文件", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"},
                    "pattern": {"type": "string", "description": "Glob 匹配模式"},
                    "recursive": {"type": "boolean", "description": "是否递归"}
                },
                "required": ["path", "pattern"]
            }),
        ]

        for name, func, desc, schema in tool_defs:
            self.tool_registry.register(name=name, func=func, description=desc, parameters_schema=schema)

    async def execute_tool(self, tool_name: str, params: Dict) -> ToolResult:
        """执行单个工具"""
        func = self.tool_registry.get(tool_name)
        if not func:
            return ToolResult(False, None, f"未知工具: {tool_name}", 0, tool_name)
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(params)
            else:
                result = await asyncio.to_thread(func, params)
            return result
        except Exception as e:
            return ToolResult(False, None, str(e), 0, tool_name)

    async def execute(self, step: Dict) -> ToolResult:
        """执行单个步骤"""
        step_type = step.get("type")
        params = step.get("params", {})

        if step_type in ("tool_call", "function_call"):
            tool_name = params.get("tool") or params.get("name")
            tool_params = params.get("arguments") or params.get("params", {})
            return await self.execute_tool(tool_name, tool_params)

        elif step_type == "file_operation":
            return await self.execute_file_operation(params)

        elif step_type == "api_call":
            return await self._adapt_http(params)

        elif step_type == "code_execution":
            return await self.execute_tool("execute_code", {"code": params.get("code", ""), "timeout": params.get("timeout", 30)})

        return ToolResult(False, None, f"未知步骤类型: {step_type}", 0, step_type)

    async def execute_file_operation(self, params: Dict) -> ToolResult:
        """执行文件操作"""
        operation = params.get("operation", "read")
        path = params.get("path", "")
        if operation == "read":
            return await self.execute_tool("read_file", {"file_path": path})
        elif operation == "write":
            return await self.execute_tool("write_file", {"path": path, "content": params.get("content", "")})
        elif operation == "list":
            return await self.execute_tool("list_files", {"directory": path})
        return ToolResult(False, None, f"未知文件操作: {operation}", 0, "file_operation")

    async def _adapt_http(self, params: Dict) -> ToolResult:
        """适配 API 调用步骤"""
        return await self.execute_tool("http_request", params)


class StreamingExecutor(EnhancedExecutor):
    """支持流式输出的执行器"""

    def __init__(self, file_operator=None, project_path: str = "."):
        super().__init__(file_operator, project_path)
        self._stream_callback: Optional[Callable[[str], None]] = None

    def set_stream_callback(self, callback: Callable[[str], None]) -> None:
        self._stream_callback = callback

    async def _stream_output(self, text: str) -> None:
        """流式输出"""
        if self._stream_callback:
            try:
                self._stream_callback(text)
            except Exception as e:
                logger.error(f"流式输出回调失败: {e}")

    async def execute_with_stream(self, step: Dict) -> ToolResult:
        """带流式输出的执行"""
        step_type = step.get("type")
        await self._stream_output(f"[开始执行: {step_type}]\n")
        result = await self.execute(step)
        if result.success:
            await self._stream_output(f"[成功] {result.result}\n")
        else:
            await self._stream_output(f"[失败] {result.error}\n")
        return result
