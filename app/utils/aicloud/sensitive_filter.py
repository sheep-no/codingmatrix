"""
敏感信息过滤器

实现敏感信息的检测和过滤，包括：
- API 密钥 (OpenAI, GitHub, GitLab 等)
- 密码
- JWT Token
- 私钥
- 数据库连接字符串
"""

import re
from typing import Dict, List

SENSITIVE_PATTERNS: Dict[str, str] = {
    r"sk-[a-zA-Z0-9]{48}": "[OPENAI_KEY]",
    r"ghp_[a-zA-Z0-9]{36}": "[GITHUB_TOKEN]",
    r"glpat-[a-zA-Z0-9\-]{20}": "[GITLAB_TOKEN]",
    r"password\s*[=:]\s*[\"']?[^\"'\\s]+[\"']?": "password=[REDACTED]",
    r"api[_-]?key\s*[=:]\s*[\"']?[^\"'\\s]+[\"']?": "api_key=[REDACTED]",
    r"-----BEGIN.*PRIVATE KEY-----[\s\S]*?-----END.*PRIVATE KEY-----": "[PRIVATE_KEY]",
    r"mongodb://[^:]+:[^@]+@": "mongodb://[REDACTED]@[HOST]",
    r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*": "[JWT_TOKEN]",
}

_compiled_patterns: Dict[str, re.Pattern] = {
    pattern: re.compile(pattern, re.IGNORECASE)
    for pattern in SENSITIVE_PATTERNS
}


def filter_sensitive_content(content: str) -> str:
    """
    过滤内容中的敏感信息

    Args:
        content: 原始内容

    Returns:
        过滤后的内容
    """
    if not content:
        return content

    filtered = content
    for pattern, re_pattern in _compiled_patterns.items():
        filtered = re_pattern.sub(SENSITIVE_PATTERNS[pattern], filtered)

    return filtered


def mask_api_keys(content: str) -> str:
    """
    专门过滤 API 密钥

    Args:
        content: 原始内容

    Returns:
        过滤后的内容
    """
    api_key_patterns = [
        r"sk-[a-zA-Z0-9]{48}",
        r"ghp_[a-zA-Z0-9]{36}",
        r"glpat-[a-zA-Z0-9\-]{20}",
        r"api[_-]?key\s*[=:]\s*[\"']?[^\"'\\s]+[\"']?",
    ]

    result = content
    for pattern in api_key_patterns:
        re_pattern = re.compile(pattern, re.IGNORECASE)
        if "sk-" in pattern:
            result = re_pattern.sub("[OPENAI_KEY]", result)
        elif "ghp_" in pattern:
            result = re_pattern.sub("[GITHUB_TOKEN]", result)
        elif "glpat-" in pattern:
            result = re_pattern.sub("[GITLAB_TOKEN]", result)
        else:
            result = re_pattern.sub("[API_KEY]", result)

    return result


def mask_passwords(content: str) -> str:
    """
    专门过滤密码

    Args:
        content: 原始内容

    Returns:
        过滤后的内容
    """
    password_patterns = [
        r"password\s*[=:]\s*.+?(?:\s|$)",
        r"passwd\s*[=:]\s*.+?(?:\s|$)",
        r"pwd\s*[=:]\s*.+?(?:\s|$)",
    ]

    result = content
    for pattern in password_patterns:
        re_pattern = re.compile(pattern, re.IGNORECASE)
        result = re_pattern.sub("password=[REDACTED]", result)

    return result


def mask_tokens(content: str) -> str:
    """
    专门过滤 Token

    Args:
        content: 原始内容

    Returns:
        过滤后的内容
    """
    token_patterns = [
        r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*",
        r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*",
        r"Token\s+[a-zA-Z0-9\-._~+/]+=*",
    ]

    result = content
    for pattern in token_patterns:
        re_pattern = re.compile(pattern, re.IGNORECASE)
        result = re_pattern.sub("[TOKEN]", result)

    return result


def detect_sensitive_info(content: str) -> List[str]:
    """
    检测内容中包含的敏感信息类型

    Args:
        content: 原始内容

    Returns:
        包含的敏感信息类型列表
    """
    if not content:
        return []

    detected = []
    for pattern_str, re_pattern in _compiled_patterns.items():
        if re_pattern.search(content):
            replacement = SENSITIVE_PATTERNS[pattern_str]
            if replacement == "[OPENAI_KEY]":
                detected.append("OpenAI API Key")
            elif replacement == "[GITHUB_TOKEN]":
                detected.append("GitHub Token")
            elif replacement == "[GITLAB_TOKEN]":
                detected.append("GitLab Token")
            elif replacement == "[PRIVATE_KEY]":
                detected.append("Private Key")
            elif replacement == "[JWT_TOKEN]":
                detected.append("JWT Token")
            elif "password" in pattern_str:
                detected.append("Password")
            elif "api" in pattern_str:
                detected.append("API Key")
            elif "mongodb" in pattern_str:
                detected.append("Database Credentials")

    return list(set(detected))
