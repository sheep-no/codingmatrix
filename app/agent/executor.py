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
import json
import re
import subprocess
from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """工具类型"""
    FILE_OPERATION = "file_operation"
    API_CALL = "api_call"
    DATABASE = "database"
    WEB_SEARCH = "web_search"
    CODE_EXECUTION = "code_execution"
    FUNCTION_CALL = "function_call"


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    tool_name: str = ""


class ToolRegistry:
    """工具注册表"""

    _instance = None
    _tools: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters_schema: Dict = None
    ) -> None:
        self._tools[name] = {
            "func": func,
            "description": description,
            "parameters": parameters_schema or {}
        }
        logger.info(f"工具注册: {name}")

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
        schemas = []
        for name, tool in self._tools.items():
            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            }
            schemas.append(schema)
        return schemas


class EnhancedExecutor:
    """增强的执行器"""

    def __init__(self, file_operator=None):
        self.file_operator = file_operator
        self.tool_registry = ToolRegistry.get_instance()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """注册默认工具"""

        self.tool_registry.register(
            name="read_file",
            func=self._tool_read_file,
            description="读取文件内容",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"}
                },
                "required": ["path"]
            }
        )

        self.tool_registry.register(
            name="write_file",
            func=self._tool_write_file,
            description="写入文件内容",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"}
                },
                "required": ["path", "content"]
            }
        )

        self.tool_registry.register(
            name="list_files",
            func=self._tool_list_files,
            description="列出目录中的文件",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"},
                    "pattern": {"type": "string", "description": "文件匹配模式（可选）"}
                },
                "required": ["path"]
            }
        )

        self.tool_registry.register(
            name="execute_code",
            func=self._tool_execute_code,
            description="执行 Python 代码",
            parameters_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 代码"},
                    "timeout": {"type": "integer", "description": "超时时间（秒）"}
                },
                "required": ["code"]
            }
        )

        self.tool_registry.register(
            name="web_search",
            func=self._tool_web_search,
            description="搜索网络信息",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "返回结果数量"}
                },
                "required": ["query"]
            }
        )

        self.tool_registry.register(
            name="http_request",
            func=self._tool_http_request,
            description="发送 HTTP 请求",
            parameters_schema={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "url": {"type": "string", "description": "请求 URL"},
                    "headers": {"type": "object"},
                    "body": {"type": "object"}
                },
                "required": ["method", "url"]
            }
        )

        self.tool_registry.register(
            name="screenshot_diagnose",
            func=self._tool_screenshot_diagnose,
            description="浏览器截图 + 前端诊断：用 Playwright 打开浏览器截图，检查组件渲染、控制台错误、布局问题",
            parameters_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要诊断的前端 URL（默认 http://localhost:3001/）"},
                    "viewport": {"type": "object", "description": "视口大小，默认 1920x1080"},
                    "checks": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["components", "errors", "layout", "text_labels"]},
                        "description": "检查类型列表：components（组件渲染）、errors（控制台错误）、layout（布局问题）、text_labels（文本标签残留）"
                    }
                },
                "required": []
            }
        )

    async def _tool_read_file(self, params: Dict) -> ToolResult:
        """读取文件工具"""
        import time
        start = time.time()

        try:
            path = params.get("path")
            if not path:
                return ToolResult(False, None, "缺少 path 参数", time.time() - start)

            if self.file_operator:
                content = await self.file_operator.read_async(path)
                return ToolResult(True, content, None, time.time() - start, "read_file")
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return ToolResult(True, content, None, time.time() - start, "read_file")

        except FileNotFoundError:
            return ToolResult(False, None, f"文件不存在: {path}", time.time() - start, "read_file")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "read_file")

    async def _tool_write_file(self, params: Dict) -> ToolResult:
        """写入文件工具"""
        import time
        start = time.time()

        try:
            path = params.get("path")
            content = params.get("content", "")

            if not path:
                return ToolResult(False, None, "缺少 path 参数", time.time() - start)

            if self.file_operator:
                await self.file_operator.write_async(path, content)
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)

            return ToolResult(True, {"path": path, "size": len(content)}, None, time.time() - start, "write_file")

        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "write_file")

    async def _tool_list_files(self, params: Dict) -> ToolResult:
        """列出文件工具"""
        import time
        import glob
        start = time.time()

        try:
            path = params.get("path", ".")
            pattern = params.get("pattern", "*")

            full_pattern = f"{path}/{pattern}" if not pattern.startswith("/") else pattern
            files = glob.glob(full_pattern, recursive=True)

            return ToolResult(True, {"files": files[:100], "count": len(files)}, None, time.time() - start, "list_files")

        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "list_files")

    async def _tool_execute_code(self, params: Dict) -> ToolResult:
        """执行代码工具"""
        import time
        start = time.time()

        try:
            code = params.get("code")
            timeout = params.get("timeout", 30)

            if not code:
                return ToolResult(False, None, "缺少 code 参数", time.time() - start)

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._execute_python(code, timeout)
            )

            return ToolResult(True, result, None, time.time() - start, "execute_code")

        except asyncio.TimeoutError:
            return ToolResult(False, None, "代码执行超时", time.time() - start, "execute_code")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "execute_code")

    def _execute_python(self, code: str, timeout: int) -> Dict:
        """执行 Python 代码（受限沙箱环境）"""
        import io
        import sys
        import ast

        old_stdout = sys.stdout
        old_stderr = sys.stderr

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        try:
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                return {
                    "output": "",
                    "error": f"语法错误 第{e.lineno}行: {e.msg}",
                    "success": False
                }

            # 禁止危险语句
            dangerous_nodes = (ast.Import, ast.ImportFrom, ast.Call, ast.Attribute)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    func_name = ""
                    if isinstance(func, ast.Name):
                        func_name = func.id
                    elif isinstance(func, ast.Attribute):
                        func_name = func.attr

                    if func_name in ("exec", "eval", "compile", "__import__", "open",
                                     "getattr", "setattr", "delattr", "globals", "locals"):
                        return {
                            "output": "",
                            "error": f"安全限制: 不允许调用 {func_name}() 函数",
                            "success": False
                        }

            # 受限的全局命名空间
            safe_globals = {
                "__builtins__": {
                    "print": print,
                    "len": len,
                    "range": range,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "abs": abs,
                    "min": min,
                    "max": max,
                    "sum": sum,
                    "sorted": sorted,
                    "reversed": reversed,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "isinstance": isinstance,
                    "issubclass": issubclass,
                    "type": type,
                    "id": id,
                    "hash": hash,
                    "repr": repr,
                    "format": format,
                    "input": None,  # 禁止 input
                    "open": None,   # 禁止 open
                    "exec": None,   # 禁止 exec
                    "eval": None,   # 禁止 eval
                    "compile": None,
                    "__import__": None,
                }
            }

            exec(code, safe_globals)
            output = stdout_capture.getvalue()
            error = stderr_capture.getvalue()

            return {
                "output": output,
                "error": error if error else None,
                "success": True
            }
        except Exception as e:
            return {
                "output": stdout_capture.getvalue(),
                "error": str(e),
                "success": False
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    async def _tool_web_search(self, params: Dict) -> ToolResult:
        """网络搜索工具"""
        import time
        import httpx
        start = time.time()

        try:
            query = params.get("query")
            limit = params.get("limit", 5)

            if not query:
                return ToolResult(False, None, "缺少 query 参数", time.time() - start)

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1}
                )

            data = response.json()
            results = []

            if "RelatedTopics" in data:
                for item in data["RelatedTopics"][:limit]:
                    if "Text" in item:
                        results.append(item["Text"])

            return ToolResult(True, {"results": results, "query": query}, None, time.time() - start, "web_search")

        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "web_search")

    async def _tool_screenshot_diagnose(self, params: Dict) -> ToolResult:
        """浏览器截图 + 前端诊断工具（使用 Playwright Async API）"""
        import time
        start = time.time()
        url = params.get("url", "http://localhost:3001/")
        viewport = params.get("viewport", {"width": 1920, "height": 1080})
        checks = params.get("checks", ["components", "errors", "layout"])

        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_viewport_size(viewport)

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)

            screenshot_path = f"/tmp/frontend_screenshot_{int(time.time())}.png"
            await page.screenshot(path=screenshot_path, full_page=True)

            diagnosis = {
                "url": url,
                "screenshot": screenshot_path,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

            if "components" in checks:
                component_checks = {
                    "#leftlist": await page.query_selector("#leftlist") is not None,
                    ".main-content": await page.query_selector(".main-content") is not None,
                    ".bottom-wrapper": await page.query_selector(".bottom-wrapper") is not None,
                    ".center-content-wrapper": await page.query_selector(".center-content-wrapper") is not None,
                    ".login-modal": await page.query_selector(".login-modal") is not None,
                }
                diagnosis["components"] = component_checks

            if "errors" in checks:
                console_errors = []
                page_errors = []
                page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                await page.reload(wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                diagnosis["console_errors"] = console_errors[:10]
                diagnosis["page_errors"] = page_errors[:5]

            if "layout" in checks:
                layout_checks = await page.evaluate("""() => {
                    const results = {};
                    const app = document.querySelector('#app');
                    results['app_exists'] = app !== null;
                    results['app_innerHTML_length'] = app ? app.innerHTML.length : 0;
                    results['main_content'] = document.querySelector('.main-content') !== null;
                    results['bottom_wrapper'] = document.querySelector('.bottom-wrapper') !== null;
                    const centerContent = document.querySelector('.center-content-wrapper');
                    if (centerContent) {
                        results['center_content_has_messages'] = centerContent.classList.contains('has-messages');
                        const emptyState = centerContent.querySelector('.empty-state');
                        results['center_content_has_empty_state'] = emptyState !== null;
                    }
                    results['has_access_token'] = localStorage.getItem('access_token') !== null;
                    return results;
                }""")
                diagnosis["layout"] = layout_checks

            if "text_labels" in checks:
                page_content = await page.content()
                has_text_labels = any(label in page_content for label in ['[WEB]', '[STATS]', '[CONFIG]', '[APP]', '[FILE]'])
                diagnosis["has_text_labels"] = has_text_labels

            await browser.close()
            await pw.stop()

            elapsed = time.time() - start
            return ToolResult(True, diagnosis, None, elapsed, "screenshot_diagnose")
            
        except Exception as e:
            elapsed = time.time() - start
            return ToolResult(False, None, f"浏览器诊断失败: {str(e)}", elapsed, "screenshot_diagnose")

    async def _tool_http_request(self, params: Dict) -> ToolResult:
        """HTTP 请求工具（带 SSRF 防护）"""
        import time
        import httpx
        from urllib.parse import urlparse
        import ipaddress
        start = time.time()

        try:
            method = params.get("method", "GET")
            url = params.get("url")
            headers = params.get("headers", {})
            body = params.get("body")

            if not url:
                return ToolResult(False, None, "缺少 url 参数", time.time() - start)

            # SSRF 防护：禁止内网和回环地址
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return ToolResult(False, None, "仅支持 http/https 协议", time.time() - start)

            host = parsed.hostname
            if host:
                try:
                    ip = ipaddress.ip_address(host)
                    if ip.is_private or ip.is_loopback or ip.is_reserved:
                        return ToolResult(False, None, "不允许访问内网地址", time.time() - start)
                except ValueError:
                    # 域名无法直接判断，允许访问（生产环境应使用 DNS 解析后再次校验）
                    pass

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=body
                )

            return ToolResult(
                True,
                {
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:5000]
                },
                None,
                time.time() - start,
                "http_request"
            )

        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "http_request")

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

        if step_type == "tool_call" or step_type == "function_call":
            tool_name = params.get("tool") or params.get("name")
            tool_params = params.get("arguments") or params.get("params", {})
            return await self.execute_tool(tool_name, tool_params)

        elif step_type == "file_operation":
            return await self.execute_file_operation(params)

        elif step_type == "api_call":
            return await self.execute_api_call(params)

        elif step_type == "code_execution":
            return await self.execute_code_execution(params)

        else:
            return ToolResult(False, None, f"未知步骤类型: {step_type}", 0, step_type)

    async def execute_file_operation(self, params: Dict) -> ToolResult:
        """执行文件操作"""
        import time
        start = time.time()

        operation = params.get("operation", "read")
        path = params.get("path", "")

        if operation == "read":
            return await self._tool_read_file({"path": path})
        elif operation == "write":
            content = params.get("content", "")
            return await self._tool_write_file({"path": path, "content": content})
        elif operation == "list":
            return await self._tool_list_files({"path": path})
        else:
            return ToolResult(False, None, f"未知文件操作: {operation}", time.time() - start, "file_operation")

    async def execute_api_call(self, params: Dict) -> ToolResult:
        """执行 API 调用"""
        return await self._tool_http_request(params)

    async def execute_code_execution(self, params: Dict) -> ToolResult:
        """执行代码"""
        code = params.get("code", "")
        return await self._tool_execute_code({"code": code, "timeout": params.get("timeout", 30)})


class StreamingExecutor(EnhancedExecutor):
    """支持流式输出的执行器"""

    def __init__(self, file_operator=None):
        super().__init__(file_operator)
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
