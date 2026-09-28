"""GlobalConstraintParser 全量注入语义测试（GC2）。

spec_first 链只调用 generate_prompt_fragment("all", "all")，此前
compatibility(applies_to=["frontend"])、security(["backend", "api"])
会被 applies_to/_file_matches_category 过滤掉——安全约束提取成功却
从未进入生成 prompt。全量注入必须返回全部约束，文件级调用保持按
作用域过滤。
"""

from app.agent.global_constraint import ConstraintCategory, GlobalConstraintParser

REQUIREMENT = (
    "所有代码必须兼容 IE11。所有接口必须有权限校验。必须使用 FastAPI。"
)


def _parse():
    parser = GlobalConstraintParser()
    parser.parse_requirement(REQUIREMENT)
    return parser


class TestAllInjection:
    def test_all_injection_keeps_scoped_constraints(self):
        parser = _parse()

        categories = {constraint.category for constraint in parser.constraints}
        # 三类约束都已提取，作为前置条件
        assert ConstraintCategory.COMPATIBILITY in categories
        assert ConstraintCategory.SECURITY in categories

        fragment = parser.generate_prompt_fragment("all", "all")
        assert "兼容性约束: IE11" in fragment
        assert "权限校验" in fragment
        assert "技术栈约束: FastAPI" in fragment

    def test_empty_parser_produces_empty_fragment(self):
        parser = GlobalConstraintParser()

        assert parser.generate_prompt_fragment("all", "all") == ""


class TestScopedInjectionUnchanged:
    def test_api_file_keeps_security_but_not_compatibility(self):
        parser = _parse()

        fragment = parser.generate_prompt_fragment("app/api/users.py", "api")
        assert "权限校验" in fragment
        assert "兼容性约束: IE11" not in fragment

    def test_frontend_file_keeps_compatibility(self):
        parser = _parse()

        fragment = parser.generate_prompt_fragment("src/views/App.vue", "frontend")
        assert "兼容性约束: IE11" in fragment
        assert "权限校验" not in fragment
