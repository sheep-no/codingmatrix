"""Branch coverage for app/agent/architecture_inspector.py."""

from types import SimpleNamespace

import pytest

from app.agent import architecture_inspector as ai
from app.agent.architecture_inspector import ArchitectureInspector


def _inspector(
    architecture=None,
    files=None,
    constraints=None,
    decisions=None,
) -> ArchitectureInspector:
    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture=architecture or {},
        generated_files=files or {},
        constraints=constraints,
        decisions=decisions,
    )
    return inspector


# ---------------------------------------------------------------------------
# inspect + LLM review
# ---------------------------------------------------------------------------


def test_inspect_runs_llm_checker_and_merges_violations() -> None:
    def checker(*, architecture, files):
        return {
            "violations": [
                {
                    "file": "backend/app/main.py",
                    "type": "custom",
                    "description": "bad",
                    "severity": "critical",
                    "suggestion": "fix",
                }
            ]
        }

    result = _inspector(files={"main.py": "x = 1\n"}).inspect(llm_checker=checker)

    assert result.passed is False
    assert any(v.violation_type == "custom" for v in result.violations)


def test_inspect_llm_review_defaults_and_ignores_empty() -> None:
    def checker(*, architecture, files):
        return {"violations": [{}]}

    result = _inspector(files={"main.py": "x = 1\n"}).inspect(llm_checker=checker)

    violation = result.violations[0]
    assert violation.file_path == "unknown"
    assert violation.violation_type == "architecture"
    assert violation.severity == "medium"

    assert _inspector().inspect(llm_checker=lambda **_: None).violations == []
    assert _inspector().inspect(llm_checker=lambda **_: {}).violations == []


def test_inspect_llm_review_swallows_exception(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(ai.logger, "error", logged.append)

    def checker(**kwargs):
        raise RuntimeError("checker down")

    result = _inspector(files={"main.py": "x = 1\n"}).inspect(llm_checker=checker)

    assert result.violations == []
    assert any("checker down" in entry for entry in logged)


def test_inspect_skips_llm_review_when_no_checker() -> None:
    result = _inspector(files={"main.py": "x = 1\n"}).inspect()

    assert result.passed is True


# ---------------------------------------------------------------------------
# Layer boundaries
# ---------------------------------------------------------------------------


def test_layer_boundaries_flag_rule_match() -> None:
    inspector = _inspector(
        architecture={
            "layers": {
                "repository": {
                    "paths": ["repositories"],
                    "boundaries": ["no_business_logic"],
                }
            }
        },
        files={"app/repositories/user.py": "def calculate():\n    return 1\n"},
    )

    result = inspector.inspect()

    assert any(v.violation_type == "layer_boundary" for v in result.violations)


def test_layer_boundaries_skip_unassigned_file() -> None:
    inspector = _inspector(
        architecture={
            "layers": {"repository": {"paths": ["repositories"], "boundaries": []}}
        },
        files={"app/services/user.py": "import sqlite3\n"},
    )

    assert inspector._check_layer_boundaries() == []


def test_assigned_layer_missing_boundaries_defaults_to_empty() -> None:
    inspector = _inspector(
        architecture={"layers": {"repository": {"paths": ["repositories"]}}},
        files={"app/repositories/user.py": "x = 1\n"},
    )

    assert inspector._check_layer_boundaries() == []


def test_violates_boundary_unknown_rule_is_false() -> None:
    assert ArchitectureInspector()._violates_boundary("anything", "not_a_rule") is False


# ---------------------------------------------------------------------------
# Interface style
# ---------------------------------------------------------------------------


def test_interface_style_graphql_declared_but_missing() -> None:
    inspector = _inspector(
        files={"app/api/schema.py": "class Query:\n    pass\n"},
        decisions={"api_style": "GraphQL"},
    )

    violations = inspector._check_interface_style()

    assert any("GraphQL" in v.description for v in violations)


def test_interface_style_graphql_declared_with_schema_is_clean() -> None:
    inspector = _inspector(
        files={"app/api/schema.py": "type Query {\n  todos: [Todo]\n}\n"},
        decisions={"api_style": "GraphQL"},
    )

    assert inspector._check_interface_style() == []


def test_interface_style_no_api_files_returns_empty() -> None:
    inspector = _inspector(
        files={"app/models/user.py": "x = 1\n"},
        decisions={"api_style": "REST"},
    )

    assert inspector._check_interface_style() == []


def test_api_style_rest_file_without_graphql_is_clean() -> None:
    inspector = ArchitectureInspector()

    assert inspector._check_api_style("@router.get('/x')", "REST") is None
    assert inspector._check_api_style("type Query { x: Int }", "GraphQL") is None
    assert inspector._check_api_style("plain", "Unknown") is None


def test_graphql_schema_detected_from_js_import() -> None:
    inspector = ArchitectureInspector()

    assert inspector._has_graphql_schema(
        "import { gql } from 'graphql';\n"
    ) is True
    assert inspector._has_graphql_schema("const x = 1;\n") is False


def test_graphql_schema_detected_from_schema_keyword() -> None:
    inspector = ArchitectureInspector()

    assert inspector._has_graphql_schema("type Mutation {\n  add: Boolean\n}\n") is True


# ---------------------------------------------------------------------------
# _file_imports_packages
# ---------------------------------------------------------------------------


def test_file_imports_packages_handles_invalid_python_falling_to_js() -> None:
    source = "import { gql } from '@apollo/graphql';\nconst x = {;\n"

    assert ArchitectureInspector._file_imports_packages(source, ("@apollo/graphql",)) is True


def test_file_imports_packages_invalid_and_no_js_match() -> None:
    assert ArchitectureInspector._file_imports_packages(
        "const x = {;\n", ("graphene",)
    ) is False


def test_file_imports_packages_ignores_non_import_nodes() -> None:
    source = "x = 1\ny = x + 2\n"

    assert ArchitectureInspector._file_imports_packages(source, ("fastapi",)) is False


def test_file_imports_packages_importfrom_without_module() -> None:
    source = "from . import local\n"

    assert ArchitectureInspector._file_imports_packages(source, ("local",)) is False


def test_file_imports_packages_submodule_prefix_matches() -> None:
    source = "from fastapi.routing import APIRouter\n"

    assert ArchitectureInspector._file_imports_packages(source, ("fastapi",)) is True


# ---------------------------------------------------------------------------
# Naming conventions
# ---------------------------------------------------------------------------


def test_naming_kebab_case_detects_underscore() -> None:
    inspector = _inspector(
        architecture={"naming_conventions": {"vue": "kebab-case"}},
        files={"frontend/components/User_Profile.vue": "<template/>"},
    )

    violations = inspector._check_naming_conventions()

    assert violations and violations[0].violation_type == "naming_convention"


def test_naming_default_pattern_and_extensionless_file() -> None:
    inspector = _inspector(
        architecture={"naming_conventions": {"default": "snake_case"}},
        files={"Make File": "target: all\n"},
    )

    violations = inspector._check_naming_conventions()

    assert violations


def test_naming_unknown_pattern_is_clean() -> None:
    inspector = _inspector(
        architecture={"naming_conventions": {"py": "camelCase"}},
        files={"app/MyThing.py": "x = 1\n"},
    )

    assert inspector._check_naming_conventions() == []


def test_naming_patterns_accept_compliant_names() -> None:
    inspector = _inspector(
        architecture={"naming_conventions": {"py": "snake_case", "vue": "kebab-case"}},
        files={"app/good_name.py": "x = 1\n", "frontend/user-profile.vue": "<template/>"},
    )

    assert inspector._check_naming_conventions() == []


# ---------------------------------------------------------------------------
# Global constraints
# ---------------------------------------------------------------------------


def test_constraint_without_applies_to_defaults_to_all() -> None:
    constraint = SimpleNamespace(description="必须有权限校验")
    inspector = _inspector(
        files={"app/api/routes.py": "def read():\n    return []\n"},
        constraints=[constraint],
    )

    violations = inspector._check_global_constraints()

    assert violations and violations[0].severity == "high"


def test_constraint_skips_empty_content() -> None:
    constraint = SimpleNamespace(description="权限校验", applies_to=["all"])
    inspector = _inspector(
        files={"app/api/routes.py": ""},
        constraints=[constraint],
    )

    assert inspector._check_global_constraints() == []


def test_constraint_non_security_description_is_ignored() -> None:
    constraint = SimpleNamespace(description="代码需要注释", applies_to=["all"])
    inspector = _inspector(
        files={"app/api/routes.py": "x = 1\n"},
        constraints=[constraint],
    )

    assert inspector._check_global_constraints() == []


def test_constraint_applies_to_api_token() -> None:
    assert ArchitectureInspector._constraint_applies_to_file(
        ["api"], "frontend/controller/view.ts"
    ) is True
    assert ArchitectureInspector._constraint_applies_to_file(
        ["backend"], "frontend/index.ts"
    ) is False
    assert ArchitectureInspector._constraint_applies_to_file(
        ["backend"], "backend/app/main.py"
    ) is True


# ---------------------------------------------------------------------------
# Tech stack
# ---------------------------------------------------------------------------


def test_tech_stack_list_of_dict_and_string_entries() -> None:
    inspector = _inspector(
        architecture={
            "tech_stack": [
                "python service",
                "react frontend",
                "unrelated",
                {"backend": "FastAPI"},
                {"frontend": "Vue"},
            ]
        },
        files={
            "backend/app/main.py": "print('x')\n",
            "frontend/src/App.js": "console.log('x')\n",
        },
    )

    violations = inspector._check_tech_stack_consistency()

    types = {v.description.split("文件")[0] for v in violations}
    assert violations
    assert any("后端" in v.description for v in violations)
    assert any("前端" in v.description for v in violations)
    assert types


def test_tech_stack_falls_back_to_user_decisions() -> None:
    inspector = _inspector(
        architecture={"tech_stack": {}},
        files={"backend/app/main.py": "print('x')\n"},
        decisions={"backend_framework": "FastAPI"},
    )
    inspector.architecture_design = {"tech_stack": {"frontend": "Vue"}}
    inspector.user_decisions = {"backend_framework": "FastAPI"}

    # tech_stack truthy but empty backend dict would early-return; replace with
    # an unrelated key to exercise the fallback branch.
    inspector.architecture_design = {"tech_stack": {"mobile": "Flutter"}}
    inspector.user_decisions = {"backend_framework": "FastAPI", "frontend_framework": "Vue"}
    inspector.generated_files = {"backend/app/main.py": "print('x')\n"}

    violations = inspector._check_tech_stack_consistency()

    assert any("后端" in v.description for v in violations)


def test_tech_stack_frontend_missing_framework_is_flagged() -> None:
    inspector = _inspector(
        architecture={"tech_stack": {"frontend": "Vue"}},
        files={"frontend/src/App.js": "console.log('x')\n"},
    )

    violations = inspector._check_tech_stack_consistency()

    assert any("前端" in v.description for v in violations)


def test_tech_stack_frontend_with_marker_is_clean() -> None:
    inspector = _inspector(
        architecture={"tech_stack": {"frontend": "Vue"}},
        files={"frontend/src/App.js": "import { createApp } from 'vue'\n"},
    )

    assert inspector._check_tech_stack_consistency() == []


def test_file_layer_top_level_rules() -> None:
    assert ArchitectureInspector._file_layer("main.py") is None
    assert ArchitectureInspector._file_layer("backend/app/main.py") == "backend"
    assert ArchitectureInspector._file_layer("frontend/src/app.ts") == "frontend"
    assert ArchitectureInspector._file_layer("lib/backend/main.py") is None


def test_framework_inconsistency_unknown_framework_is_clean() -> None:
    assert ArchitectureInspector()._check_framework_inconsistency(
        "anything", "Unknown"
    ) is False


def test_framework_inconsistency_marker_usage_is_clean() -> None:
    assert ArchitectureInspector()._check_framework_inconsistency(
        "@app.get('/x')", "FastAPI"
    ) is False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_alignment_score_clamps_at_zero_for_many_violations() -> None:
    from app.agent.architecture_inspector import ArchitectureViolation

    violations = [
        ArchitectureViolation("f.py", "t", "d", "critical", "s") for _ in range(5)
    ]

    assert ArchitectureInspector()._calculate_alignment_score(violations) == 0.0


def test_alignment_score_uses_default_weight_for_unknown_severity() -> None:
    from app.agent.architecture_inspector import ArchitectureViolation

    score = ArchitectureInspector()._calculate_alignment_score(
        [ArchitectureViolation("f.py", "t", "d", "weird", "s")]
    )

    assert score == pytest.approx(0.9)


def test_suggestions_render_severity_and_path() -> None:
    from app.agent.architecture_inspector import ArchitectureViolation

    suggestions = ArchitectureInspector()._generate_fix_suggestions(
        [ArchitectureViolation("f.py", "t", "d", "high", "fix it")]
    )

    assert suggestions == ["[high] f.py: fix it"]
