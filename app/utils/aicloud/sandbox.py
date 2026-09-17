"""
沙箱管理

实现 aicloud 的沙箱目录管理。路径归属与安全校验统一由
`app.utils.file_operator.FileOperator` 负责，此处不再提供平行的路径校验实现。
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

