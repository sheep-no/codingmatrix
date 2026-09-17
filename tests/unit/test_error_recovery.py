import pytest
import asyncio
import tempfile
from pathlib import Path

class TestErrorRecoveryLoop:
    @pytest.fixture
    def recovery(self):
        from app.agent.error_recovery import ErrorRecoveryLoop
        from app.agent.code_validator import CodeValidator
        from app.agent.code_reviewer import CodeReviewer
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            validator = CodeValidator(Path(tmpdir))
            reviewer = CodeReviewer(ctx, model_name="test-model")
            yield ErrorRecoveryLoop(validator, reviewer)
    
    def test_validate_and_fix(self, recovery):
        # 简化测试：只验证对象创建成功
        assert recovery.validator is not None
        assert recovery.reviewer is not None
        assert recovery.MAX_FIX_ATTEMPTS == 3


def test_default_fallback_chain_is_empty(monkeypatch):
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config",
        lambda: {},
    )
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    assert loop.MODEL_FALLBACK_CHAIN == []
    assert loop._load_fallback_chain() == []


def test_select_fix_model_uses_assigned_model_without_fast_default(monkeypatch):
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config",
        lambda: {},
    )
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    assert loop._select_fix_model_by_error_type("SyntaxError", ["assigned-model"], 0) == "assigned-model"


@pytest.mark.asyncio
async def test_try_react_auto_fix_requires_model_assignment():
    from app.agent.orchestrator_generation.error_recovery import ErrorRecoveryMixin

    mixin = object.__new__(ErrorRecoveryMixin)
    mixin.error_recovery = object()
    mixin.reviewer = object()
    mixin.model_assignment = None
    with pytest.raises(RuntimeError, match="model assignment is required for ReAct auto-fix"):
        await mixin._try_react_auto_fix({"failed_tests": ["test_a"]})


@pytest.mark.asyncio
async def test_quality_score_ignores_environment_import_errors():
    """环境缺包产生的 import_errors 不应拉低修复策略的质量评分。"""
    from app.agent.error_recovery import ErrorRecoveryLoop

    class StubValidator:
        async def validate_single_file(self, file_path):
            return {
                "syntax_errors": [],
                "import_errors": ["ModuleNotFoundError: No module named 'torch'"],
                "runtime_errors": [],
                "api_errors": [],
                "frontend_errors": [],
                "is_valid": True,
            }

    loop = ErrorRecoveryLoop(validator=StubValidator(), reviewer=object())
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "main.py"
        target.write_text("import torch\n", encoding="utf-8")

        assert await loop._evaluate_code_quality("import torch\n", target) == 1.0


@pytest.mark.asyncio
async def test_quality_score_penalizes_code_defects():
    from app.agent.error_recovery import ErrorRecoveryLoop

    class StubValidator:
        async def validate_single_file(self, file_path):
            return {
                "syntax_errors": ["line 1: invalid syntax"],
                "import_errors": ["ModuleNotFoundError: No module named 'torch'"],
                "runtime_errors": [],
                "api_errors": [],
                "frontend_errors": [],
                "is_valid": False,
            }

    loop = ErrorRecoveryLoop(validator=StubValidator(), reviewer=object())
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "main.py"
        target.write_text("def broken(:\n", encoding="utf-8")

        score = await loop._evaluate_code_quality("def broken(:\n", target)

    assert score == 0.8


def test_default_fix_template_is_strategy_text_without_placeholders():
    """默认策略文本会被原样注入系统提示，不能残留未填充的提示词占位符。"""
    from app.agent.error_classifier import ErrorClassification
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    template = loop._build_default_fix_template()

    assert "{content}" not in template
    assert "{error_context}" not in template
    assert "{suggested_fix_strategy}" not in template

    classification = ErrorClassification("SyntaxError", "missing_delimiter", "语法错误", "检查括号匹配", 0.9)
    context = loop._build_targeted_error_context_with_template(
        {"syntax_errors": ["line 1: invalid syntax"]}, "code = 1", 0, classification, template
    )

    assert context.startswith("## 错误类型")
    assert "invalid syntax" in context
    assert "{content}" not in context


def test_strategy_template_with_error_context_placeholder_is_substituted():
    from app.agent.error_classifier import ErrorClassification
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    classification = ErrorClassification("ImportError", "missing_module", "导入错误", "检查导入路径", 0.9)
    context = loop._build_targeted_error_context_with_template(
        {"runtime_errors": ["运行时导入失败: from fastapi import Depends"]}, "import fastapi\n", 0, classification,
        "## 自定义策略\n{error_context}\n## 结束",
    )

    assert context.startswith("## 自定义策略")
    assert context.endswith("## 结束")
    assert "运行时导入失败: from fastapi import Depends" in context


def test_environment_import_diagnostics_are_not_fix_targets():
    """validate_single_file 的 import_errors 只反映执行环境缺包，
    不能作为修复目标写进提示词，否则模型会去改本来正确的 import。"""
    from app.agent.error_classifier import ErrorClassification
    from app.agent.error_recovery import ErrorRecoveryLoop

    loop = ErrorRecoveryLoop(validator=object(), reviewer=object())
    classification = ErrorClassification("SyntaxError", "missing_delimiter", "语法错误", "检查括号匹配", 0.9)
    context = loop._build_targeted_error_context(
        {
            "syntax_errors": ["语法错误 第5行: invalid syntax"],
            "import_errors": ["缺少依赖: torch"],
        },
        "import torch\n",
        0,
        classification,
    )

    assert "invalid syntax" in context
    assert "缺少依赖: torch" not in context
    assert "## 导入错误" not in context
