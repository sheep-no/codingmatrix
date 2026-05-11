"""
守护合约 - 安全关键文件约束规则

定义核心文件/函数的保护规则，Agent 在修改代码前必须对照检查。
规则清单，机器可读，分为三级：
  - 🔴 严重 (CRITICAL): 涉及认证、加密、权限的核心函数，修改需用户确认
  - 🟡 警告 (WARNING): 影响面较大的函数，修改需简要说明风险
  - 🟢 通知 (NOTICE): 记录变更，不阻塞

用法:
    from app.utils.guard_contracts import GuardContracts, check_file_against_contracts
    violations = check_file_against_contracts(file_path, changes)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from pathlib import Path
import re
import logging

logger = logging.getLogger(__name__)


class Severity:
    CRITICAL = "critical"
    WARNING = "warning"
    NOTICE = "notice"


@dataclass
class GuardRule:
    """守护规则"""
    id: str
    severity: str
    description: str
    file_pattern: str  # 正则匹配文件路径
    protected_patterns: List[str]  # 保护的函数/类/变量名
    allowed_changes: List[str] = field(default_factory=list)  # 允许变更的白名单
    check_type: str = "existence"  # existence, signature, type_check


@dataclass
class Violation:
    """违规项"""
    rule_id: str
    severity: str
    description: str
    file_path: str
    line: Optional[int] = None
    suggestion: str = ""


class GuardContracts:
    """守护合约规则集"""

    def __init__(self):
        self.rules: List[GuardRule] = self._load_default_rules()

    def _load_default_rules(self) -> List[GuardRule]:
        """加载默认守护规则"""
        return [
            # 🔴 严重：认证与安全核心
            GuardRule(
                id="GC-001",
                severity=Severity.CRITICAL,
                description="认证核心函数禁止删除或修改签名",
                file_pattern=r".*(auth|Auth|permission|Permission).*.py",
                protected_patterns=[
                    "verify_token", "create_token", "decode_token",
                    "authenticate_user", "check_permission", "require_role",
                    "verify_password", "hash_password",
                    "verify_token", "get_current_user",
                ],
                check_type="signature",
            ),
            GuardRule(
                id="GC-002",
                severity=Severity.CRITICAL,
                description="加密相关函数禁止未授权修改",
                file_pattern=r".*(encrypt|decrypt|crypto|RSA|hash).*.py",
                protected_patterns=[
                    "encrypt", "decrypt", "encrypt_data", "decrypt_data",
                    "generate_key", "load_private_key", "load_public_key",
                    "rsa_encrypt", "rsa_decrypt",
                ],
                check_type="signature",
            ),
            GuardRule(
                id="GC-003",
                severity=Severity.CRITICAL,
                description="数据库核心模型禁止删除字段",
                file_pattern=r".*models.*.py",
                protected_patterns=[
                    "id", "user_id", "created_at", "updated_at",
                    "password_hash", "role", "is_active",
                ],
                check_type="existence",
            ),
            GuardRule(
                id="GC-004",
                severity=Severity.CRITICAL,
                description="安全中间件禁止移除",
                file_pattern=r".*middleware.*.py",
                protected_patterns=[
                    "CORS", "csrf", "rate_limit", "auth_middleware",
                    "security_headers",
                ],
                check_type="existence",
            ),

            # 🟡 警告：影响面较大的组件
            GuardRule(
                id="GC-005",
                severity=Severity.WARNING,
                description="API 路由变更需检查兼容性",
                file_pattern=r".*api.*.py",
                protected_patterns=[
                    "router", "@router.get", "@router.post", "@router.put",
                    "@router.delete", "@router.patch",
                ],
                check_type="existence",
            ),
            GuardRule(
                id="GC-006",
                severity=Severity.WARNING,
                description="任务队列核心配置变更需确认",
                file_pattern=r".*(task|queue|celery).*.py",
                protected_patterns=[
                    "TaskManager", "create_task", "update_progress",
                    "TaskQueue", "run_task",
                ],
                check_type="signature",
            ),
            GuardRule(
                id="GC-007",
                severity=Severity.WARNING,
                description="Agent 核心逻辑变更需审查",
                file_pattern=r".*(agent|orchestrat|generator).*.py",
                protected_patterns=[
                    "ProjectGeneratorAgent", "OrchestratorAgent",
                    "generate_project", "_execute_tools", "_call_llm",
                    "ToolRegistry",
                ],
                check_type="signature",
            ),
            GuardRule(
                id="GC-008",
                severity=Severity.WARNING,
                description="数据库连接配置变更需确认",
                file_pattern=r".*(db|database|sqlalchemy|config).*.py",
                protected_patterns=[
                    "DATABASE_URL", "get_db", "engine", "SessionLocal",
                    "async_session",
                ],
                check_type="existence",
            ),

            # 🟢 通知：记录变更
            GuardRule(
                id="GC-009",
                severity=Severity.NOTICE,
                description="工具函数变更已记录",
                file_pattern=r".*utils.*.py",
                protected_patterns=[],
                check_type="existence",
            ),
            GuardRule(
                id="GC-010",
                severity=Severity.NOTICE,
                description="Schema 变更已记录",
                file_pattern=r".*schema.*.py",
                protected_patterns=[],
                check_type="existence",
            ),
        ]

    def check_file(self, file_path: str, content: str) -> List[Violation]:
        """
        检查文件变更是否违反守护合约

        Args:
            file_path: 文件路径
            content: 文件内容（变更后的）

        Returns:
            违规项列表
        """
        violations = []

        for rule in self.rules:
            if not re.match(rule.file_pattern, file_path):
                continue

            violation = self._check_rule(rule, file_path, content)
            if violation:
                violations.append(violation)

        return violations

    def _check_rule(self, rule: GuardRule, file_path: str, content: str) -> Optional[Violation]:
        """检查单条规则"""
        for pattern in rule.protected_patterns:
            if rule.check_type == "existence":
                # 检查保护的模式是否存在于文件中
                if pattern not in content:
                    return Violation(
                        rule_id=rule.id,
                        severity=rule.severity,
                        description=f"[{rule.description}] 保护项 '{pattern}' 可能已被删除",
                        file_path=file_path,
                        suggestion=f"请确认是否有意移除 '{pattern}'。如确认，请在提交时说明原因。",
                    )

            elif rule.check_type == "signature":
                # 检查函数/类定义是否存在
                func_pattern = rf"(def|class)\s+{re.escape(pattern)}\s*[\(:]"
                if not re.search(func_pattern, content):
                    return Violation(
                        rule_id=rule.id,
                        severity=rule.severity,
                        description=f"[{rule.description}] 保护函数/类 '{pattern}' 可能已被删除或重命名",
                        file_path=file_path,
                        suggestion=f"请确认是否有意修改 '{pattern}'。签名变更可能影响下游依赖。",
                    )

        return None

    def get_rules_for_file(self, file_path: str) -> List[GuardRule]:
        """获取适用于指定文件的规则"""
        return [rule for rule in self.rules if re.match(rule.file_pattern, file_path)]

    def to_dict(self) -> Dict:
        """序列化为字典（供 Agent 加载到知识库）"""
        return {
            "version": "1.0",
            "rules": [
                {
                    "id": rule.id,
                    "severity": rule.severity,
                    "description": rule.description,
                    "file_pattern": rule.file_pattern,
                    "protected_patterns": rule.protected_patterns,
                    "check_type": rule.check_type,
                }
                for rule in self.rules
            ],
        }


# 全局单例
_contracts: Optional[GuardContracts] = None


def get_guard_contracts() -> GuardContracts:
    """获取守护合约单例"""
    global _contracts
    if _contracts is None:
        _contracts = GuardContracts()
    return _contracts


def check_file_against_contracts(file_path: str, content: str) -> List[Violation]:
    """便捷函数：检查文件是否违反守护合约"""
    contracts = get_guard_contracts()
    return contracts.check_file(file_path, content)


def get_applicable_rules(file_path: str) -> List[Dict]:
    """便捷函数：获取适用于指定文件的规则"""
    contracts = get_guard_contracts()
    rules = contracts.get_rules_for_file(file_path)
    return [
        {
            "id": rule.id,
            "severity": rule.severity,
            "description": rule.description,
            "protected_patterns": rule.protected_patterns,
        }
        for rule in rules
    ]


if __name__ == '__main__':
    import json
    contracts = GuardContracts()
    print(json.dumps(contracts.to_dict(), ensure_ascii=False, indent=2))
