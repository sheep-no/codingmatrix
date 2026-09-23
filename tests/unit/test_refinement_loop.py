import pytest
import asyncio
import tempfile
from pathlib import Path

class TestRefinementLoop:
    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)
    
    def test_refine_success(self, loop):
        initial_content = "def hello(): pass"
        
        result = asyncio.run(loop.refine(
            file_path="test.py",
            file_type="backend",
            description="test",
            initial_content=initial_content,
            model_name="test-model",
            project_context={}
        ))
        
        assert result is not None
        assert hasattr(result, 'final_content')
        assert hasattr(result, 'success')
        assert hasattr(result, 'attempts')


def test_refinement_loop_requires_model_assignment(tmp_path):
    from app.agent.refinement_loop import RefinementLoop
    from app.agent.shared_context import SharedContext

    ctx = SharedContext("test requirement", tmp_path)
    with pytest.raises(RuntimeError, match="model assignment is required for refinement"):
        RefinementLoop(ctx)


class TestJsFamilyValidation:
    """`_validate_code` 必须覆盖 JS/TS 家族全部扩展名，且不误报 SFC/JSX。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    @pytest.mark.asyncio
    async def test_vue_single_file_component_is_not_a_syntax_error(self, loop):
        content = (
            "<template><div>hi</div></template>\n"
            "<script>export default { name: 'A' }</script>\n"
        )

        issues = await loop._validate_code("src/App.vue", content, "frontend")

        assert issues == []

    @pytest.mark.asyncio
    async def test_jsx_and_tsx_jsx_syntax_is_not_a_syntax_error(self, loop):
        assert await loop._validate_code(
            "src/App.jsx", "export default function App() { return <div>hi</div> }\n", "frontend"
        ) == []
        assert await loop._validate_code(
            "src/App.tsx", "export const A = (): JSX.Element => <div>hi</div>\n", "frontend"
        ) == []

    @pytest.mark.asyncio
    async def test_js_family_extensions_reject_python_code(self, loop):
        python_source = "def main():\n    return 1\n"

        for path in ("src/a.mjs", "src/a.cjs", "src/App.jsx", "src/App.tsx"):
            issues = await loop._validate_code(path, python_source, "frontend")
            assert issues, path

    @pytest.mark.asyncio
    async def test_mjs_and_cjs_real_syntax_errors_are_flagged(self, loop):
        for path in ("src/a.mjs", "src/a.cjs"):
            issues = await loop._validate_code(path, "const x = ;\n", "frontend")
            assert issues, path

    @pytest.mark.asyncio
    async def test_vue_script_block_syntax_error_is_flagged(self, loop):
        content = "<script>const x = ;</script>\n"

        issues = await loop._validate_code("src/App.vue", content, "frontend")

        assert issues
        assert issues[0].type == "syntax"


class TestWarningDoesNotBlockRefinement:
    """warning 是诊断信息：不应触发修复轮次，也不应把文件判为失败。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    @pytest.mark.asyncio
    async def test_warning_only_issues_pass_without_extra_llm_calls(self, loop, monkeypatch):
        from app.agent.refinement_loop import ValidationIssue

        async def warning_only(self, file_path, content, file_type):
            return [ValidationIssue(
                type="spec_mismatch",
                severity="warning",
                message="类型定义文件应使用 Pydantic BaseModel",
            )]

        calls = []

        async def fail_if_called(**kwargs):
            calls.append(kwargs)
            raise AssertionError("warning 不应触发修复调用")

        monkeypatch.setattr("app.agent.refinement_loop.RefinementLoop._validate_code", warning_only)
        monkeypatch.setattr("app.agent.refinement_loop.call_llm", fail_if_called)

        result = await loop.refine(
            file_path="app/models.py",
            file_type="model",
            description="模型",
            initial_content="class User:\n    pass\n",
            model_name="test-model",
        )

        assert result.success is True
        assert result.attempts == 1
        assert calls == []
        assert [issue.severity for issue in result.remaining_issues] == ["warning"]

    @pytest.mark.asyncio
    async def test_environment_import_absence_is_not_reported(self, loop):
        content = "import torch\n\n\ndef run():\n    return torch.tensor(1)\n"

        issues = await loop._validate_code("app/model.py", content, "model")

        assert issues == []


class TestMarkupValidationReusesSharedSyntax:
    """HTML/CSS 结构校验必须忽略注释、字符串和原始文本元素里的定界符。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    @pytest.mark.asyncio
    async def test_markup_inside_script_string_is_not_a_structure_error(self, loop):
        # 片段：不带文档级闭合，纯计数会把字符串里的 <body> 当成未闭合标签
        content = '<script>\nconst t = "<body>";\nconsole.log("</html>");\n</script>\n'

        assert await loop._validate_code("index.html", content, "frontend") == []

    @pytest.mark.asyncio
    async def test_markup_inside_comment_is_not_a_structure_error(self, loop):
        content = "<!-- <body> </head> -->\n<div>hi</div>\n"

        assert await loop._validate_code("index.html", content, "frontend") == []

    @pytest.mark.asyncio
    async def test_unclosed_body_without_document_end_is_flagged(self, loop):
        content = "<html><head></head><body>\n<p>hi</p>\n"

        issues = await loop._validate_code("index.html", content, "frontend")

        assert issues
        assert any("</body>" in issue.message for issue in issues)

    @pytest.mark.asyncio
    async def test_css_delimiters_inside_strings_and_comments_are_ignored(self, loop):
        content = '/* } */\nbody::after {\n  content: "}";\n  background: url("a(b");\n}\n'

        assert await loop._validate_code("styles.css", content, "frontend") == []

    @pytest.mark.asyncio
    async def test_css_unbalanced_braces_are_still_flagged(self, loop):
        issues = await loop._validate_code("styles.css", "body {\n  margin: 0;\n", "frontend")

        assert issues
        assert any("大括号不匹配" in issue.message for issue in issues)


class TestSpecConsistencyFixes:
    """RL1（openapi 空操作）与 RL7（字符串包含检查）。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    @pytest.mark.asyncio
    async def test_unreferenced_openapi_routes_produce_warnings(self, loop):
        """RL1: 原实现只 pass，api 文件对未实现的路由零 issue。"""
        loop.context.save_spec(
            "openapi", {"paths": {"/api/users": {}, "/api/orders": {}}}, "m"
        )

        issues = await loop._validate_code(
            "routes.py", "router = APIRouter()\n", "api"
        )

        messages = [i.message for i in issues]
        assert any("/api/users" in m for m in messages)
        assert any("/api/orders" in m for m in messages)
        assert all(i.severity == "warning" for i in issues)

    @pytest.mark.asyncio
    async def test_referenced_openapi_route_is_not_flagged(self, loop):
        loop.context.save_spec("openapi", {"paths": {"/api/users": {}}}, "m")

        issues = await loop._validate_code(
            "routes.py", 'router.get("/api/users")\n', "api"
        )

        assert issues == []

    @pytest.mark.asyncio
    async def test_pydantic_mention_in_comment_still_warns(self, loop):
        """RL7: 注释里出现 BaseModel 不应让检查通过。"""
        loop.context.save_spec("types", {"code": "class User(BaseModel): ..."}, "m")
        content = "# 注意：这里应使用 BaseModel 定义\n\n\ndef helper():\n    return 1\n"

        issues = await loop._validate_code("models.py", content, "model")

        assert any("Pydantic" in i.message for i in issues)

    @pytest.mark.asyncio
    async def test_real_pydantic_import_passes(self, loop):
        loop.context.save_spec("types", {"code": "class User(BaseModel): ..."}, "m")
        content = "from pydantic import BaseModel\n\n\nclass User(BaseModel):\n    pass\n"

        assert await loop._validate_code("models.py", content, "model") == []


class TestSpecContextReuse:
    """RL6: SpecFirstGenerator 复用 + 异常可见。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    def _install_generator(self, monkeypatch, generator_cls):
        import sys
        import types

        module = types.ModuleType("app.agent.spec_first_generator")
        module.SpecFirstGenerator = generator_cls
        monkeypatch.setitem(sys.modules, "app.agent.spec_first_generator", module)

    def test_generator_is_instantiated_once(self, loop, monkeypatch):
        calls = {"count": 0}

        class FakeGenerator:
            def __init__(self, context):
                calls["count"] += 1

            def get_spec_context_for_file(self, file_path, file_type):
                return f"SPEC:{file_path}"

        self._install_generator(monkeypatch, FakeGenerator)

        first = loop._build_fix_prompt("a.py", "api", "d", "code", "err", None, 1)
        second = loop._build_fix_prompt("b.py", "api", "d", "code", "err", None, 2)

        assert calls["count"] == 1
        assert "SPEC:a.py" in first
        assert "SPEC:b.py" in second

    def test_generator_failure_is_logged_and_degrades_gracefully(
        self, loop, monkeypatch
    ):
        from app.agent import refinement_loop as module

        warnings = []

        class BoomGenerator:
            def __init__(self, context):
                pass

            def get_spec_context_for_file(self, file_path, file_type):
                raise RuntimeError("boom")

        self._install_generator(monkeypatch, BoomGenerator)
        monkeypatch.setattr(
            module.logger, "warning", lambda *a, **k: warnings.append(a)
        )
        loop._spec_generator = None

        prompt = loop._build_fix_prompt("a.py", "api", "d", "code", "err", None, 1)

        assert any("无规范方式修复" in str(w) for w in warnings)
        assert "（无相关规范）" in prompt


class TestRefineFailurePaths:
    """RL4/RL8: LLM 空返回与多轮修复的兜底语义。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx, complexity="simple")

    @pytest.mark.asyncio
    async def test_empty_llm_response_keeps_remaining_issues(self, loop, monkeypatch):
        from app.agent import refinement_loop as module

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": ""}}]}

        monkeypatch.setattr(module, "call_llm", fake_call_llm)

        result = await loop.refine(
            "bad.py", "backend", "d", "def f(:\n", model_name="test-model"
        )

        assert result.success is False
        assert result.attempts == loop.MAX_ATTEMPTS
        # RL4: 兜底/末轮都必须携带真实剩余问题，而非空列表
        assert result.remaining_issues

    @pytest.mark.asyncio
    async def test_recovers_after_one_fix(self, loop, monkeypatch):
        from app.agent import refinement_loop as module

        fixed = "def f():\n    return 1\n"

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": fixed}}]}

        monkeypatch.setattr(module, "call_llm", fake_call_llm)

        result = await loop.refine(
            "bad.py", "backend", "d", "def f(:\n", model_name="test-model"
        )

        assert result.success is True
        assert result.attempts == 2
        assert result.final_content.strip() == fixed.strip()
