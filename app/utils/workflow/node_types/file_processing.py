"""
File Processing Node - 文件处理节点

使用公共 FileOperator 提供通用文件操作能力
"""

import logging
from typing import Any, Dict, List

from app.schema.workflow import TaskType
from app.utils.file_operator import FileOperator, PathSecurityError
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)


class FileProcessingNode(TaskNodeBase):
    """
    文件处理节点

    基于 FileOperator 提供通用文件操作：
    - read: 读取文件内容
    - write: 写入文件内容
    - copy: 复制文件
    - move: 移动/重命名文件
    - delete: 删除文件或目录
    - create_dir: 创建目录
    - list_dir: 列出目录内容

    安全限制由 FileOperator 统一提供
    """

    task_type = TaskType.FILE_PROCESSING

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)
        self._operator = FileOperator()

    def get_required_params(self) -> List[str]:
        operation = self.params.get("operation", "")
        if operation == "read":
            return ["path"]
        elif operation in ("write", "copy", "move", "delete", "create_dir", "list_dir"):
            return ["path"]
        return ["operation"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "encoding": "utf-8",
            "recursive": False,
            "parents": True,
        }

    def validate_params(self) -> List[str]:
        errors = []
        operation = self.params.get("operation", "")

        if not operation:
            errors.append("Missing required parameter: operation")
            return errors

        allowed_operations = {"read", "write", "copy", "move", "delete", "create_dir", "list_dir"}
        if operation not in allowed_operations:
            errors.append(f"Invalid operation: {operation}. Allowed: {', '.join(allowed_operations)}")
            return errors

        try:
            if operation in ("read", "write", "delete", "create_dir", "list_dir"):
                self._operator._validate_path(self.params["path"], check_extension=False)
            elif operation in ("copy", "move"):
                self._operator._validate_path(self.params["source"], check_extension=False)
                self._operator._validate_path(self.params["destination"], check_extension=False)
        except PathSecurityError as e:
            errors.append(str(e))

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行文件操作

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 执行结果
        """
        operation = self.params.get("operation", "")

        try:
            logger.info(f"[{self.node_id}] 开始执行文件操作 | operation={operation}")

            if operation == "read":
                return await self._read_file()
            elif operation == "write":
                return await self._write_file()
            elif operation == "copy":
                return await self._copy_file()
            elif operation == "move":
                return await self._move_file()
            elif operation == "delete":
                return await self._delete()
            elif operation == "create_dir":
                return await self._create_dir()
            elif operation == "list_dir":
                return await self._list_dir()
            else:
                return NodeResult.error_result(
                    error=f"Unsupported operation: {operation}",
                    metadata={"node_type": self.task_type.value}
                )

        except FileNotFoundError as e:
            error_msg = f"File not found: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value, "operation": operation}
            )
        except PermissionError as e:
            error_msg = f"Permission denied: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value, "operation": operation}
            )
        except PathSecurityError as e:
            error_msg = f"Path security error: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value, "operation": operation}
            )
        except Exception as e:
            error_msg = f"File operation failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value, "operation": operation}
            )

    async def _read_file(self) -> NodeResult:
        """读取文件内容"""
        result = await self._operator.read_async(
            path=self.params["path"],
            offset=self.params.get("offset", 0),
            limit=self.params.get("limit", 100),
            encoding=self.params.get("encoding", "utf-8"),
        )
        return NodeResult.success_result(data=result, metadata={"operation": "read"})

    async def _write_file(self) -> NodeResult:
        """写入文件内容"""
        result = await self._operator.write_async(
            path=self.params["path"],
            content=self.params.get("content", ""),
            encoding=self.params.get("encoding", "utf-8"),
            create_backup=self.params.get("create_backup", False),
        )
        return NodeResult.success_result(data=result, metadata={"operation": "write"})

    async def _copy_file(self) -> NodeResult:
        """复制文件"""
        result = self._operator.copy(
            source=self.params["source"],
            destination=self.params["destination"],
        )
        return NodeResult.success_result(data=result, metadata={"operation": "copy"})

    async def _move_file(self) -> NodeResult:
        """移动/重命名文件"""
        result = self._operator.move(
            source=self.params["source"],
            destination=self.params["destination"],
        )
        return NodeResult.success_result(data=result, metadata={"operation": "move"})

    async def _delete(self) -> NodeResult:
        """删除文件或目录"""
        result = self._operator.delete(
            path=self.params["path"],
            recursive=self.params.get("recursive", False),
        )
        return NodeResult.success_result(data=result, metadata={"operation": "delete"})

    async def _create_dir(self) -> NodeResult:
        """创建目录"""
        result = self._operator.create(
            path=self.params["path"],
            is_directory=True,
        )
        return NodeResult.success_result(data=result, metadata={"operation": "create_dir"})

    async def _list_dir(self) -> NodeResult:
        """列出目录内容"""
        result = await self._operator.list_dir_async(
            path=self.params["path"],
            recursive=self.params.get("recursive", False),
        )
        return NodeResult.success_result(data=result, metadata={"operation": "list_dir"})
