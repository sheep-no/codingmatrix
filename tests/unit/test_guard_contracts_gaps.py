"""guard_contracts 子串匹配、签名解析与便捷函数补测。"""

from app.utils import guard_contracts as module


def test_pattern_present_identifier_vs_substring():
    contracts = module.GuardContracts()

    assert contracts._pattern_present("id", "user_id = 1") is False
    assert contracts._pattern_present("id", "id = 1") is True
    assert contracts._pattern_present("@router.get", "x = '@router.get'") is True


def test_extract_signatures_handles_syntax_error():
    contracts = module.GuardContracts()
    assert contracts._extract_signatures("def broken(") == {}


def test_extract_signatures_for_function_and_class():
    contracts = module.GuardContracts()
    signatures = contracts._extract_signatures(
        "def run(a, b=1):\n    pass\nclass Child(Base, Mixin):\n    pass\n"
    )

    assert signatures["run"] == "def(a, b=1)"
    assert signatures["Child"] == "class(Base,Mixin)"


def test_signature_rule_flags_missing_function():
    contracts = module.GuardContracts()
    violations = contracts.check_file("app/auth/service.py", "VALUE = 1")

    assert any(v.rule_id == "GC-001" for v in violations)


def test_signature_change_is_flagged():
    contracts = module.GuardContracts()
    old = "def verify_token(token):\n    pass\n"
    new = "def verify_token(token, extra):\n    pass\n"

    violations = contracts.check_file("app/auth/service.py", new, old)

    assert any("签名已变更" in v.description for v in violations)


def test_signature_unchanged_passes():
    contracts = module.GuardContracts()
    source = "def verify_token(token):\n    pass\n"

    violations = contracts.check_file("app/auth/service.py", source, source)
    assert all("签名已变更" not in v.description for v in violations)


def test_existence_rule_ignores_without_original():
    contracts = module.GuardContracts()
    violations = contracts.check_file("app/models/user.py", "name = 'x'")
    assert violations == []


def test_existence_rule_flags_removed_field():
    contracts = module.GuardContracts()
    old = "id = 1\ncreated_at = 2\n"
    new = "id = 1\n"

    violations = contracts.check_file("app/models/user.py", new, old)

    assert any("created_at" in v.description for v in violations)


def test_get_rules_for_file_and_to_dict():
    contracts = module.GuardContracts()

    rules = contracts.get_rules_for_file("app/services/auth_service.py")
    assert rules
    payload = contracts.to_dict()
    assert payload["version"] == "1.0"
    assert payload["rules"][0]["id"].startswith("GC-")


def test_global_helpers_use_singleton(monkeypatch):
    module._contracts = None
    first = module.get_guard_contracts()
    second = module.get_guard_contracts()
    assert first is second

    rules = module.get_applicable_rules("app/models/user.py")
    assert any(rule["id"] == "GC-003" for rule in rules)


def test_check_file_against_contracts_helper():
    violations = module.check_file_against_contracts("app/auth/service.py", "VALUE = 1")
    assert violations


def test_signature_rule_continues_after_valid_patterns():
    contracts = module.GuardContracts()
    source = (
        "def verify_token(token):\n    pass\n"
        "def create_token(token):\n    pass\n"
        "def decode_token(token):\n    pass\n"
        "def authenticate_user(user):\n    pass\n"
        "def check_permission(user):\n    pass\n"
        "def require_role(role):\n    pass\n"
        "def verify_password(pw):\n    pass\n"
        "def hash_password(pw):\n    pass\n"
        "def get_current_user():\n    pass\n"
    )

    violations = contracts.check_file("app/auth/service.py", source, source)

    assert violations == []


def test_signature_rule_without_baseline_skips_comparison():
    contracts = module.GuardContracts()
    source = "def verify_token(token):\n    pass\n"

    violations = contracts.check_file("app/auth/service.py", source)

    assert all("签名已变更" not in v.description for v in violations)


def test_unknown_check_type_is_skipped():
    contracts = module.GuardContracts()
    contracts.rules = [
        module.GuardRule(
            id="GC-X",
            severity=module.Severity.NOTICE,
            description="custom",
            file_pattern=r".*",
            protected_patterns=["anything"],
            check_type="type_check",
        )
    ]

    assert contracts.check_file("app/main.py", "anything") == []
