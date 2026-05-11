"""
aicloud - 简易版 AI 助手

具有 10 天记忆持久化、文件审查过滤、审计日志等安全机制。
仅限超级管理员使用，禁止修改当前项目。
"""

from app.utils.aicloud.sensitive_filter import filter_sensitive_content, mask_api_keys, mask_passwords, mask_tokens
from app.utils.aicloud.permission import check_aicloud_permission, get_user_permission_level
from app.utils.aicloud.context_isolator import ContextIsolator, is_protected_path, is_protected_file, setup_sandbox
from app.utils.aicloud.review_queue import (
    create_review,
    get_review,
    approve_review,
    reject_review,
    get_user_review_preferences,
)
from app.utils.aicloud.audit_logger import (
    log_operation,
    log_file_read,
    log_file_write,
    log_network_request,
    query_audit_logs,
)
from app.utils.aicloud.sandbox import (
    SANDBOX_BASE_DIR,
    ensure_user_sandbox,
    validate_sandbox_path,
    get_sandbox_path,
)
from app.utils.aicloud.content_analyzer import analyze_content, check_malicious_pattern, filter_file_content

__all__ = [
    "filter_sensitive_content",
    "mask_api_keys",
    "mask_passwords",
    "mask_tokens",
    "check_aicloud_permission",
    "get_user_permission_level",
    "ContextIsolator",
    "is_protected_path",
    "is_protected_file",
    "setup_sandbox",
    "create_review",
    "get_review",
    "approve_review",
    "reject_review",
    "get_user_review_preferences",
    "log_operation",
    "log_file_read",
    "log_file_write",
    "log_network_request",
    "query_audit_logs",
    "SANDBOX_BASE_DIR",
    "ensure_user_sandbox",
    "validate_sandbox_path",
    "get_sandbox_path",
    "analyze_content",
    "check_malicious_pattern",
    "filter_file_content",
]
