"""
文件契约与审查数据模型

从 multi_model_agent.py 拆分而来，保持向后兼容。
"""

import re
import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, StrictBool

logger = logging.getLogger(__name__)


@dataclass
class FileContract:
    """
    文件契约 - 确保文件操作安全

    在执行文件操作前，必须定义契约，明确操作的范围和影响
    """
    operation: str  # read, write, delete, create, move, copy
    file_path: str
    expected_content: Optional[str] = None
    max_size: int = 1024 * 1024  # 1MB
    allowed_extensions: List[str] = field(default_factory=lambda: [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css",
        ".md", ".json", ".yaml", ".yml", ".txt", ".sh", ".bash",
        ".toml", ".xml", ".sql", ".env", ".gitignore", ".dockerfile"
    ])
    require_backup: bool = True
    validation_patterns: List[str] = field(default_factory=list)
    base_path: Optional[str] = None  # 可选，限制在特定项目目录下

    def validate_path(self) -> bool:
        """验证路径安全性"""
        try:
            abs_path = Path(self.file_path).resolve()
            abs_path_str = str(abs_path).lower()

            protected_paths = {
                "/etc", "/root", "/proc", "/sys", "/boot", "/dev",
                "/var/log", "/var/cache", "/var/run", "/tmp"
            }

            for protected in protected_paths:
                if abs_path_str.startswith(protected):
                    logger.warning(f"FileContract: 禁止访问系统路径 {self.file_path}")
                    return False

            protected_files = {
                ".env", ".git/config", "id_rsa", "id_ed25519",
                "known_hosts", "authorized_keys"
            }
            for protected in protected_files:
                if protected in abs_path_str:
                    logger.warning(f"FileContract: 禁止访问敏感文件 {self.file_path}")
                    return False

            if self.base_path:
                base_resolved = Path(self.base_path).resolve()
                if not str(abs_path).startswith(str(base_resolved)):
                    logger.warning(f"FileContract: 路径超出项目范围 {self.file_path}")
                    return False

            ext = Path(self.file_path).suffix.lower()
            if ext and ext not in self.allowed_extensions:
                logger.warning(f"FileContract: 不允许的扩展名 {ext}")
                return False

            return True
        except Exception as e:
            logger.error(f"FileContract: 路径验证异常 {e}")
            return False

    def validate_content(self, content: str) -> bool:
        """验证内容安全性"""
        if len(content) > self.max_size:
            logger.warning(f"FileContract: 内容过大 {len(content)} > {self.max_size}")
            return False

        dangerous_patterns = [
            # 系统命令执行
            r"rm\s+-rf\s+/",
            r"os\.system\s*\(",
            r"os\.popen\s*\(",
            r"os\.fork\s*\(",
            r"pty\.spawn\s*\(",
            r"subprocess\.call\s*\(",
            r"subprocess\.run\s*\(\s*.*,?\s*shell\s*=\s*True",
            r"subprocess\.Popen\s*\(",
            # Python 动态执行
            r"eval\s*\(",
            r"exec\s*\(\s*['\"]",
            r"compile\s*\([^)]*['\"]exec['\"]",
            r"__import__\s*\(\s*['\"]os",
            r"__import__\s*\(\s*['\"]subprocess",
            r"__import__\s*\(\s*['\"]sys",
            # Shell 注入
            r"fork\s*\(\s*\)\s*\{",
            r"system\s*\(\s*['\"]",
            # 危险模块
            r"import\s+ctypes\s",
            r"from\s+ctypes\s+import",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.warning(f"FileContract: 发现危险模式 {pattern}")
                return False

        return True


class ReviewResult(BaseModel):
    """审查结果"""
    approved: StrictBool
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "low"


class TaskStep(BaseModel):
    """任务步骤"""
    type: Literal["file_operation", "code_generation", "tool_call", "ai_call"]
    description: str
    params: Dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False  # 标记降级生成的步骤，供 review_plan 检测


def _degrade_step(task: str, reason: str) -> Dict[str, Any]:
    """构造一个降级执行步骤，供 decompose 在解析失败时使用"""
    return {
        "type": "ai_call",
        "description": f"降级执行（{reason}）",
        "params": {"task": task},
        "degraded": True,
    }
