"""
异常防护模块 - 多模型 Agent 系统的输入和异常处理防护

提供以下防护能力：
1. Prompt 注入检测
2. 输入长度校验
3. 会话 ID 格式验证
4. 路径安全增强
5. 请求速率限制
6. 资源使用监控
"""

import logging
import os
import re
import threading
import shutil
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Set
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ============================================================================
# Prompt 注入检测
# ============================================================================

class PromptInjectionDetector:
    """检测用户输入中的 Prompt 注入攻击模式"""
    
    # 常见注入模式
    INJECTION_PATTERNS = [
        # 系统指令覆盖
        r"(?i)(ignore|disregard|override)\s+(previous|all|system|above)\s+(instructions|rules|prompts|constraints)",
        r"(?i)ignore\s+all\s+(previous|above|system|instructions|rules)",
        r"(?i)(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(developer|admin|system|root)",
        r"(?i)(bypass|skip|disable)\s+(safety|security|guard|filter|restriction)",
        r"(?i)tell\s+me\s+(your|the)\s+(api\s*key|token|password|secret|credential)",
        # 敏感信息获取
        r"(?i)(show|reveal|display|print|output)\s+(api\s*key|token|password|secret|credential|system\s*config)",
        r"(?i)(泄露|暴露|显示|输出|告诉)\s*(密码|密钥|令牌|凭证|配置|系统)",
        # 代码执行
        r"(?i)(execute|run|eval)\s*(code|command|script|shell|python)",
        # 格式化输出控制
        r"(?i)output\s+in\s+(json|xml|yaml|raw)\s+format\s+without\s+(explanation|comment|filter)",
        r"(?i)(不要解释|直接输出|无需过滤)\s*(所有|全部|完整)",
    ]
    
    # 敏感关键词
    SENSITIVE_KEYWORDS = [
        "api_key", "api-key", "apikey", "secret_key", "access_token",
        "password", "credential", "token", "private_key",
    ]
    
    def __init__(self, max_injection_score: float = 0.7):
        self.max_injection_score = max_injection_score
        self._compiled_patterns = [
            re.compile(pattern) for pattern in self.INJECTION_PATTERNS
        ]
    
    def detect(self, text: str) -> Dict[str, Any]:
        """
        检测文本中的注入模式
        
        Returns:
            {
                "is_injection": bool,
                "score": float,
                "matched_patterns": List[str],
                "risk_level": "low" | "medium" | "high"
            }
        """
        if not text or len(text.strip()) == 0:
            return {
                "is_injection": False,
                "score": 0.0,
                "matched_patterns": [],
                "risk_level": "low"
            }
        
        matched = []
        score = 0.0
        
        # 检查正则模式
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(text):
                matched.append(self.INJECTION_PATTERNS[i])
                score += 0.3
        
        # 检查敏感关键词密度
        text_lower = text.lower()
        keyword_count = sum(1 for kw in self.SENSITIVE_KEYWORDS if kw in text_lower)
        if keyword_count > 0:
            keyword_score = min(keyword_count * 0.1, 0.3)
            score += keyword_score
        
        # 检查文本结构异常
        if self._has_abnormal_structure(text):
            score += 0.2
        
        score = min(score, 1.0)
        
        risk_level = "low"
        if score > 0.7:
            risk_level = "high"
        elif score > 0.4:
            risk_level = "medium"
        
        return {
            "is_injection": score >= self.max_injection_score,
            "score": round(score, 2),
            "matched_patterns": matched[:3],  # 只返回前 3 个匹配
            "risk_level": risk_level
        }
    
    def _has_abnormal_structure(self, text: str) -> bool:
        """检查文本结构是否异常（如过多换行、特殊字符）"""
        # 过多连续换行
        if "\n\n\n\n" in text:
            return True
        
        # 过多特殊字符
        special_chars = sum(1 for c in text if c in "<>[]{}()|\\")
        if len(text) > 0 and special_chars / len(text) > 0.1:
            return True
        
        # 包含代码块标记但非正常格式
        if text.count("```") % 2 != 0:
            return True
        
        return False


# ============================================================================
# 会话 ID 验证
# ============================================================================

class SessionIdValidator:
    """验证会话 ID 格式和安全性"""
    
    # 允许的字符模式
    VALID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    
    # 长度限制
    MIN_LENGTH = 5
    MAX_LENGTH = 128
    
    # 保留前缀（防止与系统内部 ID 冲突）
    RESERVED_PREFIXES = ("sys_", "admin_", "internal_", "test_")
    
    @classmethod
    def validate(cls, session_id: Optional[str]) -> tuple[bool, str]:
        """
        验证会话 ID
        
        Returns:
            (is_valid, error_message)
        """
        if not session_id:
            return False, "会话 ID 不能为空"
        
        if len(session_id) < cls.MIN_LENGTH:
            return False, f"会话 ID 长度不能少于 {cls.MIN_LENGTH} 个字符"
        
        if len(session_id) > cls.MAX_LENGTH:
            return False, f"会话 ID 长度不能超过 {cls.MAX_LENGTH} 个字符"
        
        if not cls.VALID_PATTERN.match(session_id):
            return False, "会话 ID 只能包含字母、数字、下划线和连字符"
        
        if session_id.lower().startswith(cls.RESERVED_PREFIXES):
            return False, "会话 ID 不能使用保留前缀"
        
        return True, ""


# ============================================================================
# 路径安全
# ============================================================================

class PathSecurityChecker:
    """检查文件路径安全性"""
    
    # 禁止的路径模式
    FORBIDDEN_PATTERNS = [
        r"\.\./",  # 父目录遍历
        r"\.\.\\",  # Windows 父目录遍历
        r"^/",  # 绝对路径
        r"^[a-zA-Z]:",  # Windows 绝对路径
        r"(^|/|\\)(etc|proc|sys|dev|var/run|var/log)($|/|\\)",  # 系统目录
        r"\.(env|ini|conf|cfg)$",  # 配置文件
    ]
    
    # 最大路径深度
    MAX_DEPTH = 20
    
    @classmethod
    def check(cls, path: str, base_dir: Optional[str] = None) -> tuple[bool, str]:
        """
        检查路径安全性
        
        Returns:
            (is_safe, error_message)
        """
        if not path:
            return False, "路径不能为空"
        
        # 检查禁止模式
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, path):
                return False, f"路径包含不安全的模式：{pattern}"
        
        # 检查路径深度
        depth = path.count("/") + path.count("\\")
        if depth > cls.MAX_DEPTH:
            return False, f"路径深度超过限制（{depth} > {cls.MAX_DEPTH}）"
        
        # 如果指定了 base_dir，检查路径是否在其范围内
        if base_dir:
            resolved_path = (Path(base_dir) / path).resolve()
            resolved_base = Path(base_dir).resolve()
            
            if not str(resolved_path).startswith(str(resolved_base)):
                return False, "路径超出允许的目录范围"
        
        return True, ""


# ============================================================================
# 磁盘空间监控
# ============================================================================

@dataclass
class DiskSpaceStatus:
    """磁盘空间状态"""
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float
    is_low_space: bool
    available_for_new_session: bool


class DiskSpaceMonitor:
    """监控磁盘空间使用情况"""
    
    # 最小可用空间阈值（字节）
    MIN_FREE_SPACE_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB
    MIN_FREE_PERCENT = 10.0  # 最小可用百分比
    
    def check(self, path: str = ".") -> DiskSpaceStatus:
        """检查指定路径的磁盘空间"""
        try:
            stat = shutil.disk_usage(path)
            usage_percent = (stat.used / stat.total) * 100 if stat.total > 0 else 100
            free_percent = 100 - usage_percent
            
            is_low_space = (
                stat.free < self.MIN_FREE_SPACE_BYTES or
                free_percent < self.MIN_FREE_PERCENT
            )
            
            available_for_new_session = not is_low_space
            
            return DiskSpaceStatus(
                total_bytes=stat.total,
                used_bytes=stat.used,
                free_bytes=stat.free,
                usage_percent=round(usage_percent, 2),
                is_low_space=is_low_space,
                available_for_new_session=available_for_new_session
            )
        except Exception as e:
            logger.warning(f"检查磁盘空间失败：{e}")
            return DiskSpaceStatus(
                total_bytes=0,
                used_bytes=0,
                free_bytes=0,
                usage_percent=0.0,
                is_low_space=False,  # 无法检查时不阻止
                available_for_new_session=True
            )


# ============================================================================
# 请求速率限制器（内存级）
# ============================================================================

@dataclass
class RateLimitEntry:
    """速率限制条目"""
    count: int
    window_start: datetime
    last_request: datetime


class InMemoryRateLimiter:
    """基于内存的请求速率限制器"""
    
    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        cleanup_interval_seconds: int = 300
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval_seconds
        self._entries: Dict[str, RateLimitEntry] = {}
        self._last_cleanup: datetime = datetime.now()
        self._lock = threading.Lock()
    
    def check(self, key: str) -> tuple[bool, str]:
        """
        检查请求是否允许
        
        Returns:
            (is_allowed, error_message)
        """
        now = datetime.now()
        
        with self._lock:
            # 定期清理过期条目
            if (now - self._last_cleanup).total_seconds() > self.cleanup_interval:
                self._cleanup_expired()
                self._last_cleanup = now
            
            entry = self._entries.get(key)
            
            if entry is None:
                self._entries[key] = RateLimitEntry(
                    count=1,
                    window_start=now,
                    last_request=now
                )
                return True, ""
            
            # 检查时间窗口
            window_elapsed = (now - entry.window_start).total_seconds()
            if window_elapsed >= self.window_seconds:
                # 重置窗口
                self._entries[key] = RateLimitEntry(
                    count=1,
                    window_start=now,
                    last_request=now
                )
                return True, ""
            
            # 检查请求次数
            if entry.count >= self.max_requests:
                remaining_seconds = self.window_seconds - window_elapsed
                return False, f"请求过于频繁，请在 {int(remaining_seconds)} 秒后重试"
            
            # 更新计数
            entry.count += 1
            entry.last_request = now
            return True, ""
    
    def _cleanup_expired(self):
        """清理过期的速率限制条目"""
        now = datetime.now()
        expired_keys = []
        
        for key, entry in self._entries.items():
            if (now - entry.window_start).total_seconds() > self.window_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._entries[key]


# ============================================================================
# 全局防护上下文
# ============================================================================

@dataclass
class GuardrailContext:
    """防护上下文"""
    prompt_injection_detector: PromptInjectionDetector = field(default_factory=PromptInjectionDetector)
    session_id_validator: SessionIdValidator = field(default_factory=SessionIdValidator)
    path_security_checker: PathSecurityChecker = field(default_factory=PathSecurityChecker)
    disk_space_monitor: DiskSpaceMonitor = field(default_factory=DiskSpaceMonitor)
    rate_limiter: InMemoryRateLimiter = field(default_factory=lambda: InMemoryRateLimiter(
        max_requests=10,
        window_seconds=60
    ))


# 全局单例
_guardrail_context: Optional[GuardrailContext] = None


def get_guardrail_context() -> GuardrailContext:
    """获取全局防护上下文"""
    global _guardrail_context
    if _guardrail_context is None:
        _guardrail_context = GuardrailContext()
    return _guardrail_context


# ============================================================================
# 便捷函数
# ============================================================================

def check_prompt_safety(text: str) -> tuple[bool, str]:
    """
    检查 Prompt 安全性
    
    Returns:
        (is_safe, error_message)
    """
    if not text or len(text.strip()) == 0:
        return False, "内容不能为空"
    
    ctx = get_guardrail_context()
    result = ctx.prompt_injection_detector.detect(text)
    
    if result["is_injection"]:
        return False, f"检测到潜在的注入攻击（风险等级：{result['risk_level']}）"
    
    return True, ""


def validate_session_id(session_id: Optional[str]) -> tuple[bool, str]:
    """验证会话 ID"""
    if session_id is None or session_id == "":
        return False, "会话 ID 不能为空"
    return SessionIdValidator.validate(session_id)


def check_path_safety(path: str, base_dir: Optional[str] = None) -> tuple[bool, str]:
    """检查路径安全性"""
    return PathSecurityChecker.check(path, base_dir)


def check_disk_space(path: str = ".") -> tuple[bool, str]:
    """检查磁盘空间"""
    ctx = get_guardrail_context()
    status = ctx.disk_space_monitor.check(path)
    
    if not status.available_for_new_session:
        return False, f"磁盘空间不足（可用：{status.free_bytes / (1024**3):.2f} GB）"
    
    return True, ""


def check_rate_limit(key: str) -> tuple[bool, str]:
    """检查请求速率"""
    ctx = get_guardrail_context()
    return ctx.rate_limiter.check(key)
