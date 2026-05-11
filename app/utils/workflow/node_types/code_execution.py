"""
Code Execution Node - 代码执行节点

在安全环境中执行 Python/JS 代码
"""

import logging
import asyncio
import subprocess
import tempfile
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.schema.workflow import TaskType
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)


class CodeExecutionNode(TaskNodeBase):
    """
    代码执行节点

    在 Docker 容器中安全执行代码

    参数:
        code: 要执行的代码
        language: 语言 (python/javascript，默认 python)
        timeout: 超时时间（秒，默认 60）
    """

    task_type = TaskType.CODE_EXECUTION

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)

    def get_required_params(self) -> List[str]:
        return ["code"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "language": "python",
            "timeout": 60,
        }

    def validate_params(self) -> List[str]:
        errors = []

        if "code" not in self.params:
            errors.append("Missing required parameter: code")
        elif not isinstance(self.params["code"], str):
            errors.append("Parameter 'code' must be a string")
        elif len(self.params["code"].strip()) == 0:
            errors.append("Parameter 'code' cannot be empty")

        if "language" in self.params:
            lang = self.params["language"]
            if lang not in ("python", "javascript", "js"):
                errors.append("Parameter 'language' must be 'python' or 'javascript'")

        if "timeout" in self.params:
            if not isinstance(self.params["timeout"], (int, float)):
                errors.append("Parameter 'timeout' must be a number")
            elif self.params["timeout"] < 1 or self.params["timeout"] > 300:
                errors.append("Parameter 'timeout' must be between 1 and 300")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行代码

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 执行结果
        """
        code = self.params["code"]
        language = self.params.get("language", "python")
        timeout = self.params.get("timeout", 60)

        try:
            logger.info(f"[{self.node_id}] 开始执行代码 | language={language}")

            if language == "python":
                result = await self._execute_python(code, timeout)
            elif language in ("javascript", "js"):
                result = await self._execute_javascript(code, timeout)
            else:
                return NodeResult.error_result(
                    error=f"Unsupported language: {language}",
                    metadata={"node_type": self.task_type.value}
                )

            logger.info(f"[{self.node_id}] 代码执行完成 | exit_code={result['exit_code']}")

            if result["exit_code"] != 0:
                error_msg = f"Code execution failed with exit code {result['exit_code']}"
                if result["stderr"]:
                    error_msg += f": {result['stderr'].strip()}"
                return NodeResult.error_result(
                    error=error_msg,
                    metadata={
                        "node_type": self.task_type.value,
                        "language": language,
                        "exit_code": result["exit_code"],
                        "stdout": result["stdout"],
                        "stderr": result["stderr"],
                    }
                )

            return NodeResult.success_result(
                data={
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "exit_code": result["exit_code"],
                    "language": language,
                },
                metadata={
                    "node_type": self.task_type.value,
                    "language": language,
                    "exit_code": result["exit_code"],
                }
            )

        except asyncio.TimeoutError:
            error_msg = f"Code execution timeout after {timeout} seconds"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value, "timeout": timeout}
            )
        except Exception as e:
            error_msg = f"Code execution failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value}
            )

    async def _execute_python(self, code: str, timeout: int) -> Dict[str, Any]:
        """执行 Python 代码"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as f:
            f.write(code)
            temp_file = f.name

        try:
            process = await asyncio.create_subprocess_exec(
                'python3', temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise

            return {
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "exit_code": process.returncode,
            }
        finally:
            os.unlink(temp_file)

    async def _execute_javascript(self, code: str, timeout: int) -> Dict[str, Any]:
        """执行 JavaScript 代码"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False
        ) as f:
            f.write(code)
            temp_file = f.name

        try:
            process = await asyncio.create_subprocess_exec(
                'node', temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise

            return {
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "exit_code": process.returncode,
            }
        finally:
            os.unlink(temp_file)
