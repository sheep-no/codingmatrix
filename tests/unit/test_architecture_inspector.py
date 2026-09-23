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


class TestTechStackConsistency:
    def test_filename_substring_is_not_backend_layer(self):
        """`backend_utils.py` 不应因文件名含 backend 被当成后端层文件。"""
        inspector = _make_inspector(
            {"tech_stack": {"backend": "FastAPI"}},
            {"backend_utils.py": "x = 1\n"},
        )

        result = inspector.inspect()

        assert result.violations == []

    def test_nested_backend_dir_is_not_top_level_layer(self):
        inspector = _make_inspector(
            {"tech_stack": {"backend": "FastAPI"}},
            {"data/backend/x.py": "x = 1\n"},
        )

        result = inspector.inspect()

        assert result.violations == []

    def test_top_level_backend_without_framework_is_flagged(self):
        inspector = _make_inspector(
            {"tech_stack": {"backend": "FastAPI"}},
            {"backend/app/main.py": "print('x')\n"},
        )

        result = inspector.inspect()

        assert any(v.violation_type == "tech_stack" for v in result.violations)

    def test_comment_mentioning_framework_is_not_usage(self):
        """注释里提到框架名不等于使用了框架。"""
        from app.agent.architecture_inspector import ArchitectureInspector

        inspector = ArchitectureInspector()

        assert inspector._check_framework_inconsistency("# not FastAPI code", "FastAPI") is True

    def test_real_imports_count_as_framework_usage(self):
        from app.agent.architecture_inspector import ArchitectureInspector

        inspector = ArchitectureInspector()

        assert inspector._check_framework_inconsistency(
            "from fastapi import FastAPI\n\napp = FastAPI()\n", "FastAPI"
        ) is False
        assert inspector._check_framework_inconsistency(
            "import { ref } from 'vue'\n", "Vue"
        ) is False


class TestApiStyleConsistency:
    def test_no_decision_does_not_activate_check(self):
        """api_style 未由决策链产出时，接口风格检查不应默认按 REST 激活。"""
        inspector = _make_inspector({}, {"app/api/routes.py": "x = 1\n"})

        result = inspector.inspect()

        assert not any(v.violation_type == "interface_style" for v in result.violations)

    def test_rest_without_any_route_definition_is_flagged(self):
        inspector = _make_inspector(
            {},
            {"app/api/schemas.py": "class Item:\n    pass\n"},
            decisions={"api_style": "REST"},
        )

        result = inspector.inspect()

        assert any(
            v.violation_type == "interface_style" and "REST" in v.description
            for v in result.violations
        )

    def test_rest_with_route_definition_is_clean(self):
        inspector = _make_inspector(
            {},
            {"app/api/routes.py": "@router.get('/items')\ndef items():\n    return []\n"},
            decisions={"api_style": "REST"},
        )

        result = inspector.inspect()

        assert result.violations == []

    def test_rest_file_with_graphql_import_is_flagged(self):
        inspector = _make_inspector(
            {},
            {"app/api/schema.py": "import graphene\n\nclass Query(graphene.ObjectType):\n    pass\n"},
            decisions={"api_style": "REST"},
        )

        result = inspector.inspect()

        assert any(v.violation_type == "interface_style" for v in result.violations)

    def test_graphql_with_rest_route_is_flagged(self):
        inspector = _make_inspector(
            {},
            {"app/api/routes.py": "@app.post('/items')\ndef create():\n    return {}\n"},
            decisions={"api_style": "GraphQL"},
        )

        result = inspector.inspect()

        assert any(v.violation_type == "interface_style" for v in result.violations)
