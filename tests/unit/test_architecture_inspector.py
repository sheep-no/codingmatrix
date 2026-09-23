"""ArchitectureInspector 单元测试。"""

from types import SimpleNamespace


def _make_inspector(architecture, files, constraints=None, decisions=None):
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture=architecture,
        generated_files=files,
        constraints=constraints or [],
        decisions=decisions or {},
    )
    return inspector


def _constraint(description, applies_to):
    return SimpleNamespace(description=description, applies_to=applies_to)


class TestPassedGate:
    def test_high_violation_blocks_gate(self):
        """内建检查最高只产出 high，门禁必须认可 high 级违规。"""
        inspector = _make_inspector(
            {"tech_stack": {"backend": "FastAPI"}},
            {"backend/app/main.py": "print('hello')\n"},
        )

        result = inspector.inspect()

        assert result.passed is False
        assert any(v.severity == "high" for v in result.violations)

    def test_low_and_medium_violations_still_pass(self):
        inspector = _make_inspector(
            {"naming_conventions": {"py": "snake_case"}},
            {"app/My-File.py": "x = 1\n"},
        )

        result = inspector.inspect()

        assert result.violations
        assert all(v.severity in ("low", "medium") for v in result.violations)
        assert result.passed is True

    def test_no_violations_passes_with_full_score(self):
        inspector = _make_inspector({}, {"main.py": "x = 1\n"})

        result = inspector.inspect()

        assert result.passed is True
        assert result.architecture_alignment_score == 1.0


class TestGlobalConstraints:
    def test_security_constraint_flags_api_file_without_auth(self):
        """applies_to 的层名/关键词要匹配真实文件路径，且 'all' 不再被跳过。"""
        constraint = _constraint("所有接口必须有权限校验", ["backend", "api"])
        inspector = _make_inspector(
            {},
            {"app/routers/users.py": "def list_users():\n    return []\n"},
            constraints=[constraint],
        )

        result = inspector.inspect()

        assert result.passed is False
        assert any(v.violation_type == "global_constraint" for v in result.violations)

    def test_security_constraint_accepts_dependency_injected_auth(self):
        constraint = _constraint("所有接口必须有权限校验", ["backend", "api"])
        inspector = _make_inspector(
            {},
            {
                "app/routers/users.py": (
                    "def list_users(user=Depends(get_current_user)):\n    return []\n"
                )
            },
            constraints=[constraint],
        )

        result = inspector.inspect()

        assert result.passed is True

    def test_all_marker_matches_every_file(self):
        constraint = _constraint("必须保证权限校验", ["all"])
        inspector = _make_inspector(
            {},
            {"app/routers/items.py": "def items():\n    return []\n"},
            constraints=[constraint],
        )

        result = inspector.inspect()

        assert any(v.violation_type == "global_constraint" for v in result.violations)

    def test_constraint_skips_unrelated_layer(self):
        constraint = _constraint("所有接口必须有权限校验", ["backend", "api"])
        inspector = _make_inspector(
            {},
            {"frontend/index.html": "<div></div>\n"},
            constraints=[constraint],
        )

        result = inspector.inspect()

        assert result.violations == []


class TestDependencyDirection:
    def test_whitelist_allows_listed_target(self):
        inspector = _make_inspector(
            {
                "dependency_rules": {
                    "services_only_use_models": {
                        "source": "services",
                        "allowed_targets": ["app.models", "app.utils"],
                    }
                }
            },
            {"app/services/user.py": "from app.models import User\n"},
        )

        result = inspector.inspect()

        assert result.violations == []

    def test_whitelist_flags_target_outside_set(self):
        inspector = _make_inspector(
            {
                "dependency_rules": {
                    "services_only_use_models": {
                        "source": "services",
                        "allowed_targets": ["app.models", "app.utils"],
                    }
                }
            },
            {"app/services/user.py": "from app.api.routes import router\n"},
        )

        result = inspector.inspect()

        assert any(v.violation_type == "dependency_direction" for v in result.violations)


class TestBoundaryRules:
    def test_regex_style_pattern_is_applied_as_regex(self):
        """`import.*sql` 是正则写法，不能按字面子串匹配（否则永不命中）。"""
        from app.agent.architecture_inspector import ArchitectureInspector

        inspector = ArchitectureInspector()

        assert inspector._violates_boundary("import sqlalchemy\n", "no_database_access") is True

    def test_plain_word_uses_word_boundary(self):
        from app.agent.architecture_inspector import ArchitectureInspector

        inspector = ArchitectureInspector()

        assert inspector._violates_boundary("SELECT * FROM users", "no_database_access") is True
        assert inspector._violates_boundary("SELECTED = 1", "no_database_access") is False
