"""守护合约语义修复回归（GC1/GC3/GC6）。

- GC1：existence 检查原先只看变更后内容，缺基线导致「保护项删除」假阳性；
  现仅在提供 `original_content` 且基线中确有该保护项时才判删除。
- GC3：signature 检查原先只做 `def name` 前缀匹配，签名变更漏报；
  现提供基线时用 AST 比对参数列表/基类。
- GC6：保护项原先按子串匹配，`id` 命中 `identifier` 等；标识符类保护项改为整词匹配。
"""

from __future__ import annotations

from app.utils.guard_contracts import GuardContracts, GuardRule, Severity


def _signature_contracts() -> GuardContracts:
    """只保留一条 signature 规则的合约，隔离被测语义。"""
    contracts = GuardContracts()
    contracts.rules = [
        GuardRule(
            id="GC-TEST",
            severity=Severity.CRITICAL,
            description="测试签名规则",
            file_pattern=r".*auth.*\.py",
            protected_patterns=["verify_token"],
            check_type="signature",
        )
    ]
    return contracts


class TestExistenceBaseline:
    def test_deletion_reported_with_baseline(self):
        contracts = GuardContracts()
        original = "class User:\n    id = 1\n    role = 'admin'\n"
        changed = "class User:\n    id = 1\n"
        violations = contracts.check_file("app/models/user.py", changed, original)
        assert any("role" in v.description for v in violations)
        assert all(v.rule_id == "GC-003" for v in violations)

    def test_no_false_positive_without_baseline(self):
        """无基线时不再声称「已删除」——修复 GC1 的假阳性。"""
        contracts = GuardContracts()
        changed = "class User:\n    id = 1\n"
        assert contracts.check_file("app/models/user.py", changed) == []

    def test_pattern_absent_in_baseline_is_not_a_deletion(self):
        contracts = GuardContracts()
        original = "class User:\n    id = 1\n"
        changed = "class User:\n    id = 1\n"
        assert contracts.check_file("app/models/user.py", changed, original) == []

    def test_retained_pattern_not_flagged(self):
        contracts = GuardContracts()
        original = "role = 'admin'\n"
        changed = "role = 'user'\n"
        assert contracts.check_file("app/models/user.py", changed, original) == []


class TestIdentifierWordBoundary:
    def test_short_identifier_not_matched_inside_word(self):
        contracts = GuardContracts()
        original = "class User:\n    id = 1\n"
        # identifier 中含 "id" 子串，但不存在独立的 id 标识符
        changed = "class User:\n    identifier = 1\n"
        violations = contracts.check_file("app/models/user.py", changed, original)
        assert any("'id'" in v.description for v in violations)

    def test_full_identifier_present_is_retained(self):
        contracts = GuardContracts()
        original = "class User:\n    id = 1\n"
        changed = "class User:\n    id = 2\n"
        assert contracts.check_file("app/models/user.py", changed, original) == []


class TestSignatureComparison:
    def test_parameter_change_reported(self):
        contracts = _signature_contracts()
        original = "def verify_token(user, token):\n    return True\n"
        changed = "def verify_token(user):\n    return True\n"
        violations = contracts.check_file("app/auth/service.py", changed, original)
        assert any("签名已变更" in v.description for v in violations)

    def test_unchanged_signature_not_reported(self):
        contracts = _signature_contracts()
        original = "def verify_token(user, token):\n    return True\n"
        changed = "def verify_token(user, token):\n    return False\n"
        assert contracts.check_file("app/auth/service.py", changed, original) == []

    def test_removed_function_still_reported(self):
        contracts = _signature_contracts()
        original = "def verify_token(user, token):\n    return True\n"
        changed = "def other():\n    return True\n"
        violations = contracts.check_file("app/auth/service.py", changed, original)
        assert any("可能已被删除或重命名" in v.description for v in violations)

    def test_signature_change_without_baseline_not_asserted(self):
        """无基线时只做存在性检查，不声称签名变更。"""
        contracts = _signature_contracts()
        changed = "def verify_token(user):\n    return True\n"
        assert contracts.check_file("app/auth/service.py", changed) == []
