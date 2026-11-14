"""global_constraint 解析、分类、注入与合并补测。"""

import pytest

from app.agent.global_constraint import (
    ConstraintCategory,
    GlobalConstraint,
    GlobalConstraintParser,
)


def _parse(text):
    parser = GlobalConstraintParser()
    return parser, parser.parse_requirement(text)


@pytest.mark.parametrize("text,category,description", [
    ("必须使用 FastAPI", ConstraintCategory.TECH_STACK, "技术栈约束: FastAPI"),
    ("必须采用 Vue 框架", ConstraintCategory.TECH_STACK, "技术栈约束: Vue"),
    ("技术栈为 Django，全局统一", ConstraintCategory.TECH_STACK, "技术栈约束: Django"),
    ("兼容 IE11", ConstraintCategory.COMPATIBILITY, "兼容性约束: IE11"),
    ("支持 Chrome 浏览器", ConstraintCategory.COMPATIBILITY, "兼容性约束: Chrome"),
    ("所有接口响应时间不超过 200ms", ConstraintCategory.PERFORMANCE, "性能约束: 200"),
    ("全局加载时间不超过 3", ConstraintCategory.PERFORMANCE, "性能约束: 3"),
    ("统一使用 pnpm", ConstraintCategory.ARCHITECTURE, "架构约束: pnpm"),
    ("统一架构采用 MVC", ConstraintCategory.ARCHITECTURE, "架构约束: MVC"),
    ("必须遵循 PEP8 规范", ConstraintCategory.STYLE, "代码风格约束: PEP8"),
    ("必须遵循 Google 规范", ConstraintCategory.STYLE, "代码风格约束: Google"),
    ("所有测试覆盖率不低于 80", ConstraintCategory.TESTING, "测试约束: 80"),
])
def test_classification_patterns(text, category, description):
    _, constraints = _parse(text)
    assert len(constraints) == 1
    assert constraints[0].category is category
    assert constraints[0].description == description
    assert constraints[0].priority == "high"


@pytest.mark.parametrize("text", [
    "所有接口必须有权限校验",
    "任何操作必须认证",
    "禁止未授权访问",
    "必须有权限校验",
    "密码必须加密存储",
])
def test_security_patterns(text):
    _, constraints = _parse(text)
    assert constraints[0].category is ConstraintCategory.SECURITY
    assert constraints[0].applies_to == ["backend", "api"]


@pytest.mark.parametrize("text", [
    "统一命名规范",
    "必须命名规则为 camelCase",
    "所有文件命名规范",
    "全局命名规则为 camelCase",
])
def test_naming_patterns(text):
    _, constraints = _parse(text)
    assert constraints[0].category is ConstraintCategory.NAMING


def test_security_pattern_returns_statement_without_group():
    _, constraints = _parse("所有接口必须有权限校验")
    assert constraints[0].description == "所有接口必须有权限校验"


def test_unmatched_global_statement_becomes_general():
    _, constraints = _parse("所有模块必须保持整洁。")
    assert constraints[0].id == "general_0"
    assert constraints[0].category is ConstraintCategory.ARCHITECTURE
    assert constraints[0].priority == "medium"


def test_non_global_sentences_ignored():
    parser, constraints = _parse("这是一个普通需求。")
    assert constraints == []
    assert parser.raw_text == "这是一个普通需求。"


def test_multiple_sentences_and_newlines():
    text = "必须使用 FastAPI。\n兼容 IE11;禁止未授权访问"
    _, constraints = _parse(text)
    assert [c.category for c in constraints] == [
        ConstraintCategory.TECH_STACK,
        ConstraintCategory.COMPATIBILITY,
        ConstraintCategory.SECURITY,
    ]
    assert [c.id for c in constraints] == [
        "tech_stack_0", "compatibility_1", "security_2",
    ]


def test_keyword_appears_but_no_pattern_requires_global_keyword():
    _, constraints = _parse("请用 FastAPI 实现登录")
    assert constraints == []


def test_parse_clears_previous_constraints():
    parser, _ = _parse("必须使用 FastAPI")
    parser.parse_requirement("兼容 IE11")
    assert len(parser.constraints) == 1
    assert parser.constraints[0].category is ConstraintCategory.COMPATIBILITY


def test_get_constraints_for_file_all_returns_all():
    parser, constraints = _parse("必须使用 FastAPI。兼容 IE11")
    assert parser.get_constraints_for_file("all", "all") == constraints
    assert parser.get_constraints_for_file("src/app.tsx", "all") == constraints


def test_get_constraints_for_file_filtered_by_type():
    parser, _ = _parse("必须使用 FastAPI。兼容 IE11")
    backend = parser.get_constraints_for_file("src/server.py", "backend")
    assert [c.category for c in backend] == [ConstraintCategory.TECH_STACK]

    frontend = parser.get_constraints_for_file("src/app.vue", "frontend")
    assert [c.category for c in frontend] == [
        ConstraintCategory.TECH_STACK,
        ConstraintCategory.COMPATIBILITY,
    ]


def test_file_matches_category_paths():
    parser, _ = _parse("兼容 IE11。禁止未授权。必须测试覆盖率不低于 80。")
    constraint_by_cat = {c.category: c for c in parser.constraints}

    assert parser._file_matches_category(
        "src/frontend/components/Header.vue", ConstraintCategory.COMPATIBILITY
    ) is True
    assert parser._file_matches_category(
        "src/views/Home.vue", ConstraintCategory.COMPATIBILITY
    ) is True
    assert parser._file_matches_category(
        "src/services/auth.py", ConstraintCategory.COMPATIBILITY
    ) is False

    assert parser._file_matches_category(
        "app/api/routes.py", ConstraintCategory.SECURITY
    ) is True
    assert parser._file_matches_category(
        "app/controllers/user.py", ConstraintCategory.SECURITY
    ) is True
    assert parser._file_matches_category(
        "app/models/user.py", ConstraintCategory.SECURITY
    ) is False

    assert parser._file_matches_category(
        "tests/test_x.py", ConstraintCategory.TESTING
    ) is True
    assert parser._file_matches_category(
        "app/x.py", ConstraintCategory.TESTING
    ) is False


def test_file_matches_category_default_true():
    parser = GlobalConstraintParser()
    sentinel = object()
    assert parser._file_matches_category("x.py", sentinel) is True


def test_generate_prompt_fragment_empty():
    parser = GlobalConstraintParser()
    assert parser.generate_prompt_fragment("app/main.py", "backend") == ""


def test_generate_prompt_fragment_lists_constraints():
    parser, _ = _parse("必须使用 FastAPI。兼容 IE11")
    fragment = parser.generate_prompt_fragment("all", "all")
    assert fragment.splitlines() == [
        "全局约束要求:",
        "- 技术栈约束: FastAPI",
        "- 兼容性约束: IE11",
    ]


def test_get_all_constraints_returns_copy():
    parser, _ = _parse("必须使用 FastAPI")
    copy = parser.get_all_constraints()
    copy.clear()
    assert len(parser.constraints) == 1


def test_constraints_summary():
    parser, _ = _parse("必须使用 FastAPI。所有模块必须保持整洁。兼容 IE11")
    summary = parser.get_constraints_summary()
    assert summary["total"] == 3
    assert summary["by_category"]["tech_stack"] == 1
    assert summary["by_category"]["architecture"] == 1
    assert summary["by_category"]["compatibility"] == 1
    assert summary["high_priority"] == [
        "技术栈约束: FastAPI",
        "兼容性约束: IE11",
    ]
    assert summary["original_texts"] == [
        "必须使用 FastAPI", "所有模块必须保持整洁", "兼容 IE11",
    ]


def test_merge_with_decisions_empty():
    parser = GlobalConstraintParser()
    assert parser.merge_with_decisions({}) == ""


def test_merge_with_decisions_both():
    parser, _ = _parse("必须使用 FastAPI")
    merged = parser.merge_with_decisions({"db": "PostgreSQL"})
    assert merged == "全局约束要求:\n- 技术栈约束: FastAPI\n\n用户架构决策:\n- db: PostgreSQL"


def test_merge_with_decisions_only_decisions():
    parser = GlobalConstraintParser()
    assert parser.merge_with_decisions({"db": "SQLite"}) == "用户架构决策:\n- db: SQLite"


def test_generate_description_unknown_category_fallback():
    match = __import__("re").search(r"(\w+)", "Foo")
    assert GlobalConstraintParser()._generate_description("weird", match, "s") == "约束: Foo"


def test_global_constraint_dataclass_fields():
    constraint = GlobalConstraint(
        id="x", category=ConstraintCategory.STYLE, description="d",
        original_text="o", applies_to=["all"], priority="high",
    )
    assert constraint.id == "x"


def test_constraints_summary_accumulates_duplicate_categories():
    parser, constraints = _parse("必须使用 FastAPI。必须使用 Django")
    summary = parser.get_constraints_summary()
    assert summary["by_category"]["tech_stack"] == 2
    assert summary["high_priority"] == [
        "技术栈约束: FastAPI", "技术栈约束: Django",
    ]
    assert len(constraints) == 2
