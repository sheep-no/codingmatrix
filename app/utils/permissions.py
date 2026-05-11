"""
权限工具函数 - 三级权限体系

权限级别:
- normal: 普通用户（基础业务功能）
- admin: 管理员（用户管理、服务管理、系统监控、资源配置等）
- superadmin: 超级管理员（所有权限，含 Nginx 部署、配置恢复、限流管理等高危操作）
"""

# 权限级别定义
PERMISSION_NORMAL = "normal"
PERMISSION_ADMIN = "admin"
PERMISSION_SUPERADMIN = "superadmin"

# 权限层级（数值越大权限越高）
PERMISSION_HIERARCHY = {
    PERMISSION_NORMAL: 1,
    PERMISSION_ADMIN: 2,
    PERMISSION_SUPERADMIN: 3,
}

VALID_PERMISSION_LEVELS = [PERMISSION_NORMAL, PERMISSION_ADMIN, PERMISSION_SUPERADMIN]


def get_permission_level(value: str) -> int:
    """获取权限级别对应的数值"""
    return PERMISSION_HIERARCHY.get(value, 0)


def has_permission(user_level: str, required_level: str) -> bool:
    """
    检查用户是否具有所需权限级别

    Args:
        user_level: 用户当前权限级别
        required_level: 所需权限级别

    Returns:
        True 如果用户权限 >= 所需权限
    """
    return get_permission_level(user_level) >= get_permission_level(required_level)


def is_admin(user_level: str) -> bool:
    """检查用户是否为管理员及以上"""
    return has_permission(user_level, PERMISSION_ADMIN)


def is_superadmin(user_level: str) -> bool:
    """检查用户是否为超级管理员"""
    return user_level == PERMISSION_SUPERADMIN
