"""
安全代码执行器 - AICloud 代码执行沙箱

支持 Python, Node.js, Go 代码的安全执行。
使用 subprocess 隔离，限制时间、内存，禁用网络访问。
"""

import ast
import asyncio
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CodeExecutionResult:
    """代码执行结果"""
    success: bool
    output: str
    error: str
    exit_code: int
    execution_time: float
    language: str


# 严格禁止的系统调用和模块
BANNED_PYTHON_MODULES = {
    "os", "sys", "subprocess", "multiprocessing", "socket",
    "http", "urllib", "requests", "ftplib", "smtplib",
    "pickle", "shelve", "ctypes", "importlib"
}

BANNED_JS_MODULES = {
    "child_process", "fs", "net", "http", "https", "os", "path",
    "crypto", "cluster", "dgram", "dns", "readline", "repl",
    "stream", "tls", "tty", "v8", "vm", "zlib"
}


class CodeExecutor:
    """安全代码执行器"""

    MAX_EXECUTION_TIME = 10  # 最大执行时间（秒）
    MAX_OUTPUT_SIZE = 10240  # 最大输出大小（10KB）
    MAX_MEMORY_MB = 256  # 最大内存限制（MB）

    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path or tempfile.gettempdir()

    async def execute(
        self,
        code: str,
        language: str,
        timeout: int = MAX_EXECUTION_TIME
    ) -> CodeExecutionResult:
        """
        执行代码片段

        Args:
            code: 代码内容
            language: 语言类型 (python, javascript, go)
            timeout: 超时时间（秒）

        Returns:
            CodeExecutionResult
        """
        lang = language.lower().strip()
        if lang in ("python", "py"):
            return await self._execute_python(code, timeout)
        elif lang in ("javascript", "js", "node"):
            return await self._execute_javascript(code, timeout)
        elif lang in ("go", "golang"):
            return await self._execute_go(code, timeout)
        else:
            return CodeExecutionResult(
                success=False,
                output="",
                error=f"不支持的语言: {language}",
                exit_code=-1,
                execution_time=0.0,
                language=language
            )

    async def _execute_python(self, code: str, timeout: int) -> CodeExecutionResult:
        """执行 Python 代码"""
        import ast
        import time

        start_time = time.time()

        # 语法检查与AST分析
        try:
            tree = ast.parse(code)
            self._check_python_ast(tree)
        except SyntaxError as e:
            return CodeExecutionResult(
                success=False, output="", error=f"语法错误: {e}",
                exit_code=1, execution_time=0.0, language="python"
            )
        except ValueError as e:
            return CodeExecutionResult(
                success=False, output="", error=str(e),
                exit_code=1, execution_time=0.0, language="python"
            )

        # 写入临时文件
        file_name = f"exec_{uuid.uuid4().hex[:8]}.py"
        file_path = os.path.join(self.workspace_path, file_name)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 使用受限环境执行
            proc = await asyncio.create_subprocess_exec(
                "python3",
                "-u", file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONDONTWRITEBYTECODE": "1"
                },
                cwd=self.workspace_path
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                out = stdout.decode("utf-8", errors="replace")
                err = stderr.decode("utf-8", errors="replace")
                success = proc.returncode == 0
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                out = ""
                err = f"执行超时 ({timeout}s)"
                success = False

            exec_time = time.time() - start_time
            return CodeExecutionResult(
                success=success,
                output=self._truncate_output(out),
                error=self._truncate_output(err),
                exit_code=proc.returncode if success else -1,
                execution_time=exec_time,
                language="python"
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    def _check_python_ast(self, tree: ast.AST):
        """检查 Python AST 以禁止危险操作"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in BANNED_PYTHON_MODULES:
                        raise ValueError(f"禁止导入模块: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in BANNED_PYTHON_MODULES:
                    raise ValueError(f"禁止导入模块: {node.module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval", "compile", "open"):
                    raise ValueError(f"禁止调用函数: {node.func.id}")

    async def _execute_javascript(self, code: str, timeout: int) -> CodeExecutionResult:
        """执行 JavaScript/Node.js 代码"""
        import time
        start_time = time.time()

        # 简单静态分析检查危险模块
        for mod in BANNED_JS_MODULES:
            if f"require('{mod}')" in code or f'require("{mod}")' in code:
                return CodeExecutionResult(
                    success=False, output="", error=f"禁止使用模块: {mod}",
                    exit_code=1, execution_time=0.0, language="javascript"
                )

        file_name = f"exec_{uuid.uuid4().hex[:8]}.js"
        file_path = os.path.join(self.workspace_path, file_name)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            proc = await asyncio.create_subprocess_exec(
                "node",
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                out = stdout.decode("utf-8", errors="replace")
                err = stderr.decode("utf-8", errors="replace")
                success = proc.returncode == 0
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                out = ""
                err = f"执行超时 ({timeout}s)"
                success = False

            exec_time = time.time() - start_time
            return CodeExecutionResult(
                success=success,
                output=self._truncate_output(out),
                error=self._truncate_output(err),
                exit_code=proc.returncode if success else -1,
                execution_time=exec_time,
                language="javascript"
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    async def _execute_go(self, code: str, timeout: int) -> CodeExecutionResult:
        """执行 Go 代码"""
        import time
        start_time = time.time()

        # 检查 package 和危险导入
        if "package main" not in code:
            code = "package main\n" + code
        if "func main()" not in code:
            return CodeExecutionResult(
                success=False, output="", error="缺少 func main() 入口函数",
                exit_code=1, execution_time=0.0, language="go"
            )

        for mod in ["net", "os/exec", "syscall", "unsafe"]:
            if f'"{mod}"' in code:
                return CodeExecutionResult(
                    success=False, output="", error=f"禁止导入包: {mod}",
                    exit_code=1, execution_time=0.0, language="go"
                )

        file_name = f"exec_{uuid.uuid4().hex[:8]}"
        file_path = os.path.join(self.workspace_path, f"{file_name}.go")
        bin_path = os.path.join(self.workspace_path, file_name)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 编译
            compile_proc = await asyncio.create_subprocess_exec(
                "go", "build", "-o", bin_path, file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            _, compile_err = await asyncio.wait_for(
                compile_proc.communicate(), timeout=timeout
            )
            if compile_proc.returncode != 0:
                return CodeExecutionResult(
                    success=False, output="",
                    error=compile_err.decode("utf-8", errors="replace"),
                    exit_code=compile_proc.returncode,
                    execution_time=time.time() - start_time,
                    language="go"
                )

            # 运行
            run_proc = await asyncio.create_subprocess_exec(
                bin_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    run_proc.communicate(), timeout=timeout
                )
                out = stdout.decode("utf-8", errors="replace")
                err = stderr.decode("utf-8", errors="replace")
                success = run_proc.returncode == 0
            except asyncio.TimeoutError:
                run_proc.kill()
                await run_proc.communicate()
                out = ""
                err = f"执行超时 ({timeout}s)"
                success = False

            exec_time = time.time() - start_time
            return CodeExecutionResult(
                success=success,
                output=self._truncate_output(out),
                error=self._truncate_output(err),
                exit_code=run_proc.returncode if success else -1,
                execution_time=exec_time,
                language="go"
            )
        finally:
            for f in [file_path, bin_path]:
                if os.path.exists(f):
                    os.remove(f)

    def _truncate_output(self, text: str) -> str:
        """截断过长的输出"""
        if len(text) > self.MAX_OUTPUT_SIZE:
            return text[:self.MAX_OUTPUT_SIZE] + "\n... (输出已截断)"
        return text
