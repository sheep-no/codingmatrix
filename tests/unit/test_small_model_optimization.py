"""
单元测试 - 小模型优化策略组件

测试覆盖：
1. SharedContext
2. SpecFirstGenerator
3. RefinementLoop
4. DependencyGraph
5. CrossValidator
"""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.shared_context import SharedContext, FileArtifact, SpecArtifact, GenerationPhase
from app.agent.dependency_graph import DependencyGraph, FileNode
from app.agent.cross_validator import CrossValidator


# ==================== SharedContext Tests ====================

class TestSharedContext:
    """SharedContext 测试"""

    def test_init(self, tmp_path):
        ctx = SharedContext("test requirement", tmp_path)
        assert ctx.requirement == "test requirement"
        assert ctx.output_dir == tmp_path
        assert ctx.session_id is not None
        assert ctx.tech_stack == []
        assert ctx.specs == {}
        assert ctx.files == {}
        assert ctx.errors == []
        assert ctx.warnings == []

    def test_phase_lifecycle(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.start_phase("spec_generation", total_files=5)
        assert ctx.phases["spec_generation"].status == "in_progress"
        assert ctx.phases["spec_generation"].files_total == 5

        ctx.complete_phase("spec_generation")
        assert ctx.phases["spec_generation"].status == "completed"
        assert ctx.phases["spec_generation"].completed_at is not None

    def test_phase_complete_with_errors(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.start_phase("spec_generation")
        ctx.complete_phase("spec_generation", errors=["error1", "error2"])
        assert ctx.phases["spec_generation"].status == "failed"
        assert "error1" in ctx.errors

    def test_phase_complete_empty_errors(self, tmp_path):
        """空列表 errors 应该标记为 failed"""
        ctx = SharedContext("test", tmp_path)
        ctx.start_phase("spec_generation")
        ctx.complete_phase("spec_generation", errors=[])
        assert ctx.phases["spec_generation"].status == "failed"

    def test_save_and_get_spec(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.save_spec("openapi", {"paths": {"/api/users": {}}}, "test-model")
        spec = ctx.get_spec("openapi")
        assert spec is not None
        assert "/api/users" in spec["paths"]
        assert "openapi" in ctx.specs

    def test_save_file_content(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.save_file_content("main.py", "print('hello')", "model-a")
        assert ctx.get_file_content("main.py") == "print('hello')"
        assert ctx.files["main.py"].generated_by == "model-a"

    def test_file_validation_update(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.save_file_content("main.py", "code", "model")
        ctx.update_file_validation("main.py", False, ["syntax error"])
        assert ctx.files["main.py"].validation_passed is False
        assert "syntax error" in ctx.files["main.py"].validation_errors

    def test_increment_fix_attempts(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.save_file_content("main.py", "code", "model")
        ctx.increment_fix_attempts("main.py")
        ctx.increment_fix_attempts("main.py")
        assert ctx.files["main.py"].fix_attempts == 2

    def test_generation_order_simple(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.save_file_content("config.py", "config", "m")
        ctx.dependencies["main.py"] = ["config.py"]
        ctx.save_file_content("main.py", "main", "m")
        order = ctx.get_generation_order()
        assert order.index("config.py") < order.index("main.py")

    def test_add_error_and_warning(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.add_error("critical error")
        ctx.add_warning("minor warning")
        assert "critical error" in ctx.errors
        assert "minor warning" in ctx.warnings

    def test_get_summary(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        ctx.tech_stack = ["Python", "FastAPI"]
        ctx.project_type = "api"
        summary = ctx.get_summary()
        assert summary["project_type"] == "api"
        assert summary["tech_stack"] == ["Python", "FastAPI"]


# ==================== DependencyGraph Tests ====================

class TestDependencyGraph:
    """DependencyGraph 测试"""

    def test_add_file(self):
        g = DependencyGraph()
        g.add_file("config.py", file_type="config", priority=1)
        assert "config.py" in g.nodes
        assert g.nodes["config.py"].file_type == "config"

    def test_add_dependency(self):
        g = DependencyGraph()
        g.add_file("config.py", priority=1)
        g.add_file("main.py", priority=2)
        g.add_dependency("main.py", "config.py")
        assert "config.py" in g.adjacency["main.py"]

    def test_add_dependency_missing_node(self):
        """依赖不存在的节点不会被记录（避免引入外部库作为节点）"""
        g = DependencyGraph()
        g.add_file("main.py", priority=2)
        g.add_dependency("main.py", "nonexistent.py")
        # 依赖不会被记录，因为目标节点不存在
        assert "nonexistent.py" not in g.adjacency.get("main.py", set())

    def test_generation_order_no_deps(self):
        g = DependencyGraph()
        g.add_file("a.py", priority=1)
        g.add_file("b.py", priority=2)
        g.add_file("c.py", priority=3)
        order = g.get_generation_order()
        assert set(order) == {"a.py", "b.py", "c.py"}

    def test_generation_order_with_deps(self):
        g = DependencyGraph()
        g.add_file("config.py", file_type="config", priority=1)
        g.add_file("models.py", file_type="model", priority=2)
        g.add_file("services.py", file_type="service", priority=3)
        g.add_file("api.py", file_type="api", priority=4)
        order = g.get_generation_order()
        assert order.index("config.py") < order.index("models.py")
        assert order.index("models.py") < order.index("services.py")
        assert order.index("services.py") < order.index("api.py")

    def test_cycle_breaking(self):
        """循环依赖应该被打破"""
        g = DependencyGraph()
        g.add_file("a.py", priority=1)
        g.add_file("b.py", priority=2)
        g.add_file("c.py", priority=3)
        g.add_dependency("a.py", "b.py")
        g.add_dependency("b.py", "c.py")
        g.add_dependency("c.py", "a.py")  # 循环
        order = g.get_generation_order()
        assert len(order) == 3
        assert set(order) == {"a.py", "b.py", "c.py"}

    def test_get_generation_layers(self):
        """分层应该正确"""
        g = DependencyGraph()
        g.add_file("config.py", priority=1)
        g.add_file(".env", priority=1)
        g.add_file("models.py", priority=2)
        g.add_file("services.py", priority=3)
        g.add_dependency("models.py", "config.py")
        g.add_dependency("services.py", "models.py")

        layers = g.get_generation_layers()
        assert len(layers) >= 2
        # config.py 和 .env 应该在第一层
        assert {"config.py", ".env"}.issubset(set(layers[0]))

    def test_get_context_for_file(self):
        g = DependencyGraph()
        g.add_file("config.py", priority=1)
        g.add_file("main.py", priority=2)
        g.add_dependency("main.py", "config.py")

        generated = {"config.py": "DATABASE_URL = 'sqlite:///db.sqlite3'"}
        context = g.get_context_for_file("main.py", generated)
        assert "config.py" in context
        assert "DATABASE_URL" in context

    def test_to_dict(self):
        g = DependencyGraph()
        g.add_file("config.py", priority=1)
        g.add_file("main.py", priority=2)
        result = g.to_dict()
        assert "nodes" in result
        assert "dependencies" in result
        assert "generation_order" in result


# ==================== CrossValidator Tests ====================

class TestCrossValidator:
    """CrossValidator 测试"""

    def test_is_critical_file_auth(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)
        # priority<=2 且命中模式
        assert cv.is_critical_file("app/auth/login.py", "api", priority=1) is True
        assert cv.is_critical_file("app/middleware/auth_middleware.py", "service", priority=2) is True
        # priority>2 即使命中模式也不触发
        assert cv.is_critical_file("app/auth/login.py", "api", priority=3) is False

    def test_is_critical_file_payment(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)
        assert cv.is_critical_file("app/services/payment.py", "service", priority=1) is True
        assert cv.is_critical_file("app/models/order.py", "model", priority=2) is True

    def test_is_not_critical_file(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)
        assert cv.is_critical_file("app/utils/helpers.py", "util") is False
        assert cv.is_critical_file("config.py", "config") is False
        assert cv.is_critical_file("README.md", "docs") is False

    def test_extract_json_from_code_block(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)
        text = '''Some text
```json
{"winner": "A", "reason": "better code"}
```
More text'''
        result = cv._extract_json(text)
        assert result is not None
        assert result["winner"] == "A"

    def test_extract_json_direct(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)
        text = '{"winner": "B", "reason": "cleaner"}'
        result = cv._extract_json(text)
        assert result is not None
        assert result["winner"] == "B"

    def test_extract_json_with_braces_in_text(self, tmp_path):
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)
        text = 'Some text {"winner": "merged"} more text'
        result = cv._extract_json(text)
        assert result is not None
        assert result["winner"] == "merged"

    @pytest.mark.asyncio
    async def test_validate_and_select_fallback(self, tmp_path):
        """当 LLM 返回空内容时，默认使用版本 A"""
        ctx = SharedContext("test", tmp_path)
        cv = CrossValidator(ctx)

        with patch("app.agent.cross_validator.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"choices": [{"message": {"content": ""}}]}
            result_code, winner = await cv.validate_and_select(
                file_path="auth.py",
                file_type="api",
                description="Auth API",
                version_a="code A",
                model_a="model-A",
                version_b="code B",
                model_b="model-B",
                judge_model="judge"
            )
            assert result_code == "code A"
            assert winner == "model-A"


# ==================== SpecFirstGenerator Tests ====================

class TestSpecFirstGenerator:
    """SpecFirstGenerator 测试"""

    def test_extract_json(self, tmp_path):
        from app.agent.spec_first_generator import SpecFirstGenerator
        ctx = SharedContext("test", tmp_path)
        gen = SpecFirstGenerator(ctx)

        text = '```json\n{"openapi": "3.0.0"}\n```'
        result = gen._extract_json(text)
        assert result is not None
        assert result["openapi"] == "3.0.0"

    def test_clean_code_block(self, tmp_path):
        from app.agent.spec_first_generator import SpecFirstGenerator
        ctx = SharedContext("test", tmp_path)
        gen = SpecFirstGenerator(ctx)

        text = '```python\nprint("hello")\n```'
        result = gen._clean_code_block(text)
        assert result == 'print("hello")'

    def test_clean_code_block_no_marker(self, tmp_path):
        from app.agent.spec_first_generator import SpecFirstGenerator
        ctx = SharedContext("test", tmp_path)
        gen = SpecFirstGenerator(ctx)

        text = 'print("hello")'
        result = gen._clean_code_block(text)
        assert result == 'print("hello")'

    def test_get_spec_context_for_api(self, tmp_path):
        from app.agent.spec_first_generator import SpecFirstGenerator
        ctx = SharedContext("test", tmp_path)
        ctx.save_spec("openapi", {"paths": {"/api/users": {"get": {}}}}, "model")
        gen = SpecFirstGenerator(ctx)

        context = gen.get_spec_context_for_file("app/api/users.py", "api")
        assert "openapi" in context.lower() or "OpenAPI" in context
        assert "/api/users" in context


# ==================== RefinementLoop Tests ====================

class TestRefinementLoop:
    """RefinementLoop 测试"""

    def test_validate_python_syntax_valid(self, tmp_path):
        from app.agent.refinement_loop import RefinementLoop
        ctx = SharedContext("test", tmp_path)
        rl = RefinementLoop(ctx)

        issues = rl._validate_python_syntax("def hello():\n    return 'world'", "test.py")
        assert len(issues) == 0

    def test_validate_python_syntax_invalid(self, tmp_path):
        from app.agent.refinement_loop import RefinementLoop
        ctx = SharedContext("test", tmp_path)
        rl = RefinementLoop(ctx)

        issues = rl._validate_python_syntax("def hello(\n    return 'world'", "test.py")
        assert len(issues) > 0
        assert issues[0].type == "syntax"

    def test_validate_json_valid(self, tmp_path):
        from app.agent.refinement_loop import RefinementLoop
        ctx = SharedContext("test", tmp_path)
        rl = RefinementLoop(ctx)

        issues = rl._validate_json_syntax('{"key": "value"}')
        assert len(issues) == 0

    def test_validate_json_invalid(self, tmp_path):
        from app.agent.refinement_loop import RefinementLoop
        ctx = SharedContext("test", tmp_path)
        rl = RefinementLoop(ctx)

        issues = rl._validate_json_syntax('{"key": "value"')
        assert len(issues) > 0
        assert issues[0].type == "syntax"

    def test_validate_js_bracket_mismatch(self, tmp_path):
        from app.agent.refinement_loop import RefinementLoop
        ctx = SharedContext("test", tmp_path)
        rl = RefinementLoop(ctx)

        issues = rl._validate_js_basic("function test() { return true")
        assert any(i.type == "syntax" for i in issues)

    def test_build_error_summary(self, tmp_path):
        from app.agent.refinement_loop import RefinementLoop, ValidationIssue
        ctx = SharedContext("test", tmp_path)
        rl = RefinementLoop(ctx)

        issues = [
            ValidationIssue(type="syntax", severity="error", message="Missing colon", line=5, suggestion="Add :"),
            ValidationIssue(type="import", severity="warning", message="Missing import"),
        ]
        summary = rl._build_error_summary(issues)
        assert "[ERROR]" in summary
        assert "[WARNING]" in summary
        assert "Missing colon" in summary
