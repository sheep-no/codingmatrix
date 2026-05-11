"""
上下文隔离器

实现 aicloud 的上下文隔离功能：
- 保护系统关键路径
- 保护敏感文件
- 设置沙箱环境
"""

import fnmatch
import os
from typing import Dict, Optional

PROTECTED_PATHS = [
    "/etc/",
    "/root/",
    "/home/*/.ssh/",
    "/proc/",
    "/sys/",
    "/var/",
    "/usr/",
    "/boot/",
    "/dev/",
    "/run/",
    "/snap/",
    "/srv/",
    "/opt/",
]

PROTECTED_FILES = [
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "credentials.json",
    "secrets.json",
    "*.credentials",
    "id_rsa",
    "id_ed25519",
    ".git/config",
    ".git/credentials",
    "*.password",
    "*.secret",
]


class ContextIsolator:
    """上下文隔离器"""

    def __init__(self):
        self.main_project_env: Dict[str, str] = {}
        self.sandbox_env: Dict[str, str] = {}

    def setup_sandbox(self, user_id: int) -> None:
        """
        设置沙箱环境

        Args:
            user_id: 用户 ID
        """
        self.sandbox_env = {
            "HOME": f"/sandbox/{user_id}",
            "WORK_DIR": f"/sandbox/{user_id}/workspace",
        }
        self.main_project_env = {}

    def block_protected_paths(self, file_path: str) -> bool:
        """
        检查是否访问受保护路径

        Args:
            file_path: 文件路径

        Returns:
            True if path is protected
        """
        normalized_path = os.path.normpath(file_path)

        for pattern in PROTECTED_PATHS:
            if pattern.endswith("/*/"):
                prefix = pattern[:-3]
                if normalized_path.startswith(prefix):
                    return True
            elif pattern.endswith("/"):
                if normalized_path.startswith(pattern):
                    return True
            else:
                if pattern in normalized_path:
                    return True

        return False

    def block_protected_files(self, file_path: str) -> bool:
        """
        检查是否访问受保护文件

        Args:
            file_path: 文件路径

        Returns:
            True if file is protected
        """
        normalized_path = os.path.normpath(file_path)
        filename = os.path.basename(normalized_path)

        for pattern in PROTECTED_FILES:
            if fnmatch.fnmatch(filename, pattern):
                return True
            if "/" in pattern:
                if normalized_path.endswith(pattern):
                    return True
                path_parts = normalized_path.split("/")
                if pattern.lstrip("./") in path_parts:
                    return True

        return False


_isolator_instance: Optional[ContextIsolator] = None


def get_isolator() -> ContextIsolator:
    """获取全局上下文隔离器实例"""
    global _isolator_instance
    if _isolator_instance is None:
        _isolator_instance = ContextIsolator()
    return _isolator_instance


def is_protected_path(file_path: str) -> bool:
    """
    检查路径是否受保护

    Args:
        file_path: 文件路径

    Returns:
        True if path is protected
    """
    return get_isolator().block_protected_paths(file_path)


def is_protected_file(file_path: str) -> bool:
    """
    检查文件是否受保护

    Args:
        file_path: 文件路径

    Returns:
        True if file is protected
    """
    return get_isolator().block_protected_files(file_path)


def setup_sandbox(user_id: int) -> Dict[str, str]:
    """
    设置沙箱环境

    Args:
        user_id: 用户 ID

    Returns:
        沙箱环境变量字典
    """
    isolator = get_isolator()
    isolator.setup_sandbox(user_id)
    return isolator.sandbox_env
