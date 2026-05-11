"""
沙箱管理

实现 aicloud 的沙箱功能：
- 沙箱根目录管理
- 用户沙箱目录确保
- 沙箱路径验证
"""

import os

SANDBOX_BASE_DIR = "/sandbox"


def get_sandbox_path(user_id: int) -> str:
    """
    获取用户的沙箱路径

    Args:
        user_id: 用户 ID

    Returns:
        沙箱路径
    """
    return os.path.join(SANDBOX_BASE_DIR, str(user_id))


def get_sandbox_workspace_path(user_id: int) -> str:
    """
    获取用户的沙箱工作目录

    Args:
        user_id: 用户 ID

    Returns:
        工作目录路径
    """
    return os.path.join(get_sandbox_path(user_id), "workspace")


async def ensure_user_sandbox(user_id: int) -> str:
    """
    确保用户沙箱目录存在

    Args:
        user_id: 用户 ID

    Returns:
        沙箱路径
    """
    sandbox_path = get_sandbox_path(user_id)
    workspace_path = get_sandbox_workspace_path(user_id)

    os.makedirs(sandbox_path, exist_ok=True)
    os.makedirs(workspace_path, exist_ok=True)

    return sandbox_path


def validate_sandbox_path(user_id: int, requested_path: str) -> bool:
    """
    验证请求的路径是否在用户沙箱内

    Args:
        user_id: 用户 ID
        requested_path: 请求的路径

    Returns:
        True if path is valid
    """
    sandbox_path = get_sandbox_path(user_id)

    # 使用 realpath 解析符号链接和规范化路径
    normalized_requested = os.path.realpath(requested_path)
    normalized_sandbox = os.path.realpath(sandbox_path)

    # 精确匹配沙箱目录或其子目录
    return (normalized_requested == normalized_sandbox or
            normalized_requested.startswith(normalized_sandbox + os.sep))


def get_absolute_sandbox_path(user_id: int, relative_path: str) -> str:
    """
    获取沙箱内的绝对路径

    Args:
        user_id: 用户 ID
        relative_path: 相对路径

    Returns:
        绝对路径
    """
    workspace_path = get_sandbox_workspace_path(user_id)
    workspace_basename = os.path.basename(workspace_path)
    if relative_path.startswith(workspace_basename + "/"):
        relative_path = relative_path[len(workspace_basename) + 1:]
    return os.path.normpath(os.path.join(workspace_path, relative_path))


def sanitize_path(path: str) -> str:
    """
    清理路径，防止路径穿越

    Args:
        path: 原始路径

    Returns:
        清理后的路径
    """
    return os.path.normpath(path)


def is_path_safe(path: str) -> bool:
    """
    检查路径是否安全（不包含危险字符且不在受保护路径）

    Args:
        path: 路径

    Returns:
        True if path is safe
    """
    dangerous_patterns = [
        "..",
        "~",
        "$",
        "`",
        ";",
        "|",
        "&",
        "&&",
        "||",
    ]

    protected_paths = [
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

    normalized = os.path.normpath(path)

    for pattern in dangerous_patterns:
        if pattern in path:
            return False

    for protected in protected_paths:
        if protected.endswith("/*/"):
            prefix = protected[:-3]
            if normalized.startswith(prefix):
                return False
        elif normalized.startswith(protected):
            return False

    return True
