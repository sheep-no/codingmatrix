"""
Sandbox File Operator - AICloud 沙箱文件操作器

继承 FileOperator，提供 AICloud 沙箱场景的文件操作能力
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

from app.utils.file_operator import FileOperator, PathSecurityError


class SandboxFileOperator(FileOperator):
    """
    AICloud 沙箱专用文件操作器

    继承自 FileOperator，专门用于 /sandbox/{user_id}/workspace 目录
    复用统一的安全验证逻辑
    """

    SANDBOX_BASE_DIR = "/sandbox"

    PROTECTED_PATHS: Set[str] = {
        "/etc", "/root", "/proc", "/sys", "/boot", "/dev",
        "/var/log", "/var/cache", "/var/run",
    }

    def __init__(self, user_id: int, workspace_subdir: str = "workspace"):
        """
        初始化沙箱文件操作器

        Args:
            user_id: 用户 ID
            workspace_subdir: 工作目录子目录（默认 workspace）
        """
        self.user_id = user_id
        base_path = os.path.join(self.SANDBOX_BASE_DIR, str(user_id), workspace_subdir)
        super().__init__(base_path=base_path)

    def validate_sandbox_path(self, requested_path: str) -> bool:
        """
        验证路径是否在沙箱内

        Args:
            requested_path: 请求的路径

        Returns:
            True if path is within sandbox
        """
        normalized_requested = os.path.normpath(requested_path)
        normalized_sandbox = os.path.normpath(str(self.base_path))

        return normalized_requested.startswith(normalized_sandbox + os.sep) or \
               normalized_requested == normalized_sandbox

    def get_absolute_path(self, relative_path: str) -> str:
        """
        获取沙箱内的绝对路径

        Args:
            relative_path: 相对路径

        Returns:
            绝对路径
        """
        workspace_basename = os.path.basename(str(self.base_path))
        if relative_path.startswith(workspace_basename + "/"):
            relative_path = relative_path[len(workspace_basename) + 1:]
        return os.path.normpath(os.path.join(str(self.base_path), relative_path))

    async def read_with_review(
        self,
        path: str,
        require_review: bool = False,
    ) -> Dict[str, Any]:
        """
        读取文件（支持审查）

        Args:
            path: 文件路径
            require_review: 是否需要审查

        Returns:
            包含内容和元数据的字典
        """
        abs_path = self.get_absolute_path(path)

        if not self.validate_sandbox_path(abs_path):
            raise PathSecurityError(f"路径超出沙箱范围: {path}")

        self._validate_path(path, must_exist=True, check_extension=False)

        content = await self.read_async(path)

        from app.utils.aicloud.sensitive_filter import filter_sensitive_content
        from app.utils.aicloud.content_analyzer import analyze_content

        filtered = filter_sensitive_content(content.get("content", ""))
        ai_passed, warnings = await analyze_content(content.get("content", ""), "read")

        return {
            "content": filtered,
            "raw_content": content.get("content", ""),
            "ai_passed": ai_passed,
            "warnings": warnings,
            "path": path,
            "size": content.get("size", 0),
        }

    async def write_with_review(
        self,
        path: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        写入文件（支持审查）

        Args:
            path: 文件路径
            content: 文件内容

        Returns:
            包含审查结果的字典
        """
        abs_path = self.get_absolute_path(path)

        if not self.validate_sandbox_path(abs_path):
            raise PathSecurityError(f"路径超出沙箱范围: {path}")

        from app.utils.aicloud.content_analyzer import deep_content_analysis

        analysis = await deep_content_analysis(content, "write", self.user_id)

        if analysis.get("action") == "auto_approve":
            result = await self.write_async(path, content)
            result["review_status"] = "approved"
            result["analysis"] = analysis
            return result
        else:
            return {
                "success": False,
                "review_status": "pending",
                "analysis": analysis,
                "path": path,
            }
