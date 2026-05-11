"""
统一错误码定义

分类规则:
- 认证错误 (AUTH_1xxx): 1000-1999
- 验证错误 (VAL_2xxx): 2000-2999
- 资源错误 (RES_3xxx): 3000-3999
- 业务错误 (BIZ_4xxx): 4000-4999
- 系统错误 (SYS_5xxx): 5000-5999

每个错误码格式: (code, message, http_status)
"""
from enum import Enum
from typing import Tuple


class ErrorCode(Enum):
    """统一错误码枚举"""

    # ========== 认证错误 (1xxx) ==========
    AUTH_REQUIRED = ("AUTH_1001", "需要认证", 401)
    TOKEN_EXPIRED = ("AUTH_1002", "Token 已过期", 401)
    TOKEN_INVALID = ("AUTH_1003", "Token 无效", 401)
    TOKEN_MISSING = ("AUTH_1004", "缺少认证 Token", 401)
    LOGIN_FAILED = ("AUTH_1005", "用户名或密码错误", 401)
    ACCOUNT_DISABLED = ("AUTH_1006", "账号已被禁用", 403)
    PERMISSION_DENIED = ("AUTH_1007", "权限不足", 403)
    SESSION_EXPIRED = ("AUTH_1008", "会话已过期", 401)
    REFRESH_TOKEN_EXPIRED = ("AUTH_1009", "刷新 Token 已过期", 401)
    OAUTH_PROVIDER_ERROR = ("AUTH_1010", "第三方认证失败", 502)

    # ========== 验证错误 (2xxx) ==========
    INVALID_INPUT = ("VAL_2001", "输入验证失败", 422)
    INVALID_FORMAT = ("VAL_2002", "数据格式错误", 422)
    INVALID_EMAIL = ("VAL_2003", "邮箱格式错误", 422)
    INVALID_PHONE = ("VAL_2004", "手机号格式错误", 422)
    PASSWORD_TOO_WEAK = ("VAL_2005", "密码强度不足", 422)
    FIELD_REQUIRED = ("VAL_2006", "必填字段缺失", 422)
    FIELD_TOO_LONG = ("VAL_2007", "字段长度超出限制", 422)
    FIELD_TOO_SHORT = ("VAL_2008", "字段长度不足", 422)
    INVALID_ENUM_VALUE = ("VAL_2009", "枚举值无效", 422)
    DUPLICATE_ENTRY = ("VAL_2010", "数据重复", 409)

    # ========== 资源错误 (3xxx) ==========
    NOT_FOUND = ("RES_3001", "资源不存在", 404)
    RESOURCE_DELETED = ("RES_3002", "资源已被删除", 410)
    RESOURCE_CONFLICT = ("RES_3003", "资源冲突", 409)
    RESOURCE_LOCKED = ("RES_3004", "资源已被锁定", 423)
    FILE_NOT_FOUND = ("RES_3005", "文件不存在", 404)
    FILE_TOO_LARGE = ("RES_3006", "文件大小超出限制", 413)
    FILE_TYPE_NOT_ALLOWED = ("RES_3007", "文件类型不允许", 415)
    STORAGE_FULL = ("RES_3008", "存储空间已满", 507)
    IMAGE_PROCESS_FAILED = ("RES_3009", "图片处理失败", 500)

    # ========== 业务错误 (4xxx) ==========
    OPERATION_FAILED = ("BIZ_4001", "操作失败", 500)
    DATA_NOT_READY = ("BIZ_4002", "数据未就绪", 202)
    TASK_TIMEOUT = ("BIZ_4003", "任务执行超时", 504)
    TASK_CANCELLED = ("BIZ_4004", "任务已取消", 499)
    INSUFFICIENT_BALANCE = ("BIZ_4005", "余额不足", 402)
    QUOTA_EXCEEDED = ("BIZ_4006", "配额已用完", 429)
    WORKFLOW_ERROR = ("BIZ_4007", "工作流执行错误", 500)
    AGENT_ERROR = ("BIZ_4008", "AI Agent 执行错误", 500)
    KNOWLEDGE_SYNC_FAILED = ("BIZ_4009", "知识库同步失败", 500)
    EXPORT_FAILED = ("BIZ_4010", "导出失败", 500)

    # ========== 系统错误 (5xxx) ==========
    INTERNAL_ERROR = ("SYS_5001", "服务器内部错误", 500)
    SERVICE_UNAVAILABLE = ("SYS_5002", "服务暂时不可用", 503)
    RATE_LIMITED = ("SYS_5003", "请求过于频繁", 429)
    DATABASE_ERROR = ("SYS_5004", "数据库错误", 500)
    CACHE_ERROR = ("SYS_5005", "缓存服务异常", 500)
    EXTERNAL_SERVICE_ERROR = ("SYS_5006", "外部服务调用失败", 502)
    TIMEOUT = ("SYS_5007", "请求超时", 504)
    CONFIG_ERROR = ("SYS_5008", "配置错误", 500)
    DEGRADED_MODE = ("SYS_5009", "服务降级模式", 503)
    MAINTENANCE = ("SYS_5010", "系统维护中", 503)

    def __init__(self, code: str, message: str, http_status: int):
        self._code = code
        self._message = message
        self._http_status = http_status

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def http_status(self) -> int:
        return self._http_status

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "code": self.code,
            "message": self.message,
            "http_status": self.http_status,
        }

    def with_message(self, custom_message: str) -> tuple:
        """返回自定义消息的错误码元组"""
        return (self.code, custom_message, self.http_status)
