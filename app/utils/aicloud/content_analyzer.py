"""
AI 内容分析器

实现 aicloud 的 AI 内容分析功能：
- AI 内容分析
- 恶意代码检测
- 文件内容过滤
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple

MALICIOUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r":\(\)\{:\|:&\};:",
    r"fork\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*:\s*&[^}]*\}",
    r"exec\s*\(\s*['\"].*;.*['\"]\s*\)",
    r"eval\s*\(\s*['\"]",
    r"__import__\s*\(\s*['\"](?:os|subprocess|pty|socket)",
    r"subprocess\.call\s*\(",
    r"os\.system\s*\(",
    r"os\.popen\s*\(",
    r"socket\.socket\s*\([^)]*\)\.connect\s*\(",
    r"pty\.spawn\s*\(",
    r"base64\.b64decode\s*\(",
]

DANGEROUS_FILE_EXTENSIONS = [
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bat",
    ".cmd",
    ".ps1",
    ".vbs",
    ".scr",
    ".msi",
    ".deb",
    ".rpm",
    ".appimage",
]

SAFE_FILE_EXTENSIONS = [
    # 代码文件
    ".txt", ".md", ".json", ".yaml", ".yml", ".toml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue",
    ".html", ".css", ".scss", ".sass", ".less",
    ".java", ".c", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".rb", ".php",
    ".sql",
    ".xml", ".csv", ".log",
    # 前端构建文件
    ".sh", ".bash",
    # 配置文件
    ".conf", ".config", ".ini",
    # 图片资源
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    # 字体
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # 其他
    ".txt", ".pdf",
]

COMPILED_MALICIOUS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in MALICIOUS_PATTERNS
]


async def analyze_content(
    content: str,
    operation_type: str
) -> Tuple[bool, List[str]]:
    """
    AI 内容分析

    Args:
        content: 内容
        operation_type: 操作类型 ('read' or 'write')

    Returns:
        (是否通过, 警告列表)
    """
    if not content:
        return True, []

    warnings = []

    has_malicious, malicious_found = check_malicious_pattern(content)
    if has_malicious:
        warnings.extend([f"Dangerous pattern detected: {p}" for p in malicious_found])
        return False, warnings

    if operation_type == "write":
        warnings.append("File write requires review for safety")
        return True, warnings

    return True, warnings


def check_malicious_pattern(content: str) -> Tuple[bool, List[str]]:
    """
    检测恶意代码模式

    Args:
        content: 内容

    Returns:
        (是否有恶意代码, 发现的恶意模式列表)
    """
    found = []

    for pattern in COMPILED_MALICIOUS_PATTERNS:
        if pattern.search(content):
            found.append(pattern.pattern)

    return len(found) > 0, found


def check_dangerous_extensions(filename: str) -> Optional[str]:
    """
    检查危险文件扩展名

    Args:
        filename: 文件名

    Returns:
        警告信息或 None
    """
    filename_lower = filename.lower()

    for ext in SAFE_FILE_EXTENSIONS:
        if filename_lower.endswith(ext):
            return None

    for ext in DANGEROUS_FILE_EXTENSIONS:
        if filename_lower.endswith(ext):
            return f"Dangerous file extension: {ext}"

    return f"Potentially unsafe file extension: {os.path.splitext(filename)[1]}"


def filter_file_content(content: str) -> str:
    """
    过滤文件内容（简单实现）

    Args:
        content: 文件内容

    Returns:
        过滤后的内容
    """
    from app.utils.aicloud.sensitive_filter import filter_sensitive_content
    return filter_sensitive_content(content)


async def deep_content_analysis(
    content: str,
    operation_type: str,
    user_id: int
) -> Dict[str, Any]:
    """
    深度内容分析

    Args:
        content: 内容
        operation_type: 操作类型
        user_id: 用户 ID

    Returns:
        分析结果
    """
    passed, warnings = await analyze_content(content, operation_type)

    result = {
        "passed": passed,
        "warnings": warnings,
        "operation_type": operation_type,
        "content_length": len(content) if content else 0,
    }

    if not passed:
        result["risk_level"] = "high"
        result["action"] = "require_human_review"
    elif warnings:
        result["risk_level"] = "medium"
        result["action"] = "require_human_review"
    else:
        result["risk_level"] = "low"
        result["action"] = "auto_approve"

    return result
