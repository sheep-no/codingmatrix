import pytest
import asyncio
import tempfile
from pathlib import Path

class TestCrossValidator:
    @pytest.fixture
    def validator(self):
        from app.agent.cross_validator import CrossValidator
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            yield CrossValidator(ctx)
    
    def test_is_critical_file(self, validator):
        # priority=1 自动触发
        assert validator.is_critical_file("auth.py", "backend", priority=1) is True
        # priority<=2 且命中模式
        assert validator.is_critical_file("permission.py", "backend", priority=2) is True
        assert validator.is_critical_file("payment.py", "backend", priority=2) is True
        # priority>2 即使命中模式也不触发
        assert validator.is_critical_file("auth.py", "backend", priority=3) is False
        # 不命中模式
        assert validator.is_critical_file("utils.py", "backend") is False
        assert validator.is_critical_file("README.md", "docs") is False

    def test_is_critical_file_disabled_when_review_off(self):
        from app.agent.cross_validator import CrossValidator
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            validator = CrossValidator(ctx, review_enabled=False)
            assert validator.is_critical_file("auth.py", "backend", priority=1) is False
            assert validator.is_critical_file("payment.py", "backend", priority=2) is False

    def test_positional_args_satisfy_required_params(self, validator):
        # `def greet(name)` 本身会被扫描为一次调用，位置参数应满足 name
        files = {
            "greet.py": 'def greet(name):\n    return f"Hello, {name}"',
            "main.py": 'from greet import greet\n\nprint(greet("world"))',
        }
        issues = asyncio.run(
            validator.validate_cross_file_consistency(files, {"language": "python"})
        )
        assert [issue for issue in issues if issue["type"] == "missing_argument"] == []

    def test_missing_positional_arg_still_reported(self, validator):
        files = {"a.py": "def add(a, b):\n    return a + b\n\nresult = add(1)\n"}
        issues = asyncio.run(
            validator.validate_cross_file_consistency(files, {"language": "python"})
        )
        missing = [issue for issue in issues if issue["type"] == "missing_argument"]
        assert len(missing) == 1
        assert "b" in missing[0]["message"]

    def test_keyword_and_default_args_satisfy_required_params(self, validator):
        files = {
            "kw.py": "def add(a, b):\n    return a + b\n\nresult = add(a=1, b=2)\n",
            "default.py": "def sub(a, b=2):\n    return a - b\n\nresult = sub(1)\n",
        }
        issues = asyncio.run(
            validator.validate_cross_file_consistency(files, {"language": "python"})
        )
        assert [issue for issue in issues if issue["type"] == "missing_argument"] == []
    
    def test_validate_and_select(self, validator):
        version_a = "def hello():\n    return 'A'"
        version_b = "def hello():\n    return 'B'"
        
        async def fake_llm(**_kwargs):
            return {"choices": [{"message": {"content": '{"winner": "A", "reason": "ok"}'}}]}

        from unittest.mock import patch
        with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
            result, winner = asyncio.run(validator.validate_and_select(
                file_path="test.py",
                file_type="backend",
                description="test function",
                version_a=version_a,
                model_a="model-a",
                version_b=version_b,
                model_b="model-b",
                judge_model="judge-model"
            ))

        assert result == version_a
        assert winner == "model-a"


def test_validate_and_select_empty_judge_raises(tmp_path):
    from unittest.mock import patch
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", tmp_path))

    async def fake_llm(**_kwargs):
        return {"choices": [{"message": {"content": ""}}]}

    with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
        with pytest.raises(ValueError, match="cross validator judge was empty"):
            asyncio.run(validator.validate_and_select(
                file_path="test.py",
                file_type="backend",
                description="test function",
                version_a="A",
                model_a="model-a",
                version_b="B",
                model_b="model-b",
                judge_model="judge-model",
            ))


def test_validate_and_select_invalid_json_raises(tmp_path):
    from unittest.mock import patch
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", tmp_path))

    async def fake_llm(**_kwargs):
        return {"choices": [{"message": {"content": "not json at all"}}]}

    with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
        with pytest.raises(ValueError, match="cross validator judge was not JSON"):
            asyncio.run(validator.validate_and_select(
                file_path="test.py",
                file_type="backend",
                description="test function",
                version_a="A",
                model_a="model-a",
                version_b="B",
                model_b="model-b",
                judge_model="judge-model",
            ))


def test_validate_and_select_timeout_reraises(tmp_path):
    from unittest.mock import patch
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", tmp_path))

    async def fake_llm(**_kwargs):
        raise TimeoutError("LLM 调用超时 (300s)")

    with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
        with pytest.raises(TimeoutError):
            asyncio.run(validator.validate_and_select(
                file_path="test.py",
                file_type="backend",
                description="test function",
                version_a="A",
                model_a="model-a",
                version_b="B",
                model_b="model-b",
                judge_model="judge-model",
            ))


def test_select_llm_fix_issues_caps_and_prioritizes_imports():
    from app.agent.cross_validator import select_llm_fix_issues

    issues = [
        {"type": "symbol_not_found", "file": f"f{i}.py", "message": f"missing {i}"}
        for i in range(40)
    ]
    issues.insert(0, {"type": "import_error", "file": "main.py", "message": "no app.main"})
    issues.insert(1, {"type": "import_error", "file": "main.py", "message": "no app.main"})

    selected = select_llm_fix_issues(issues, max_issues=20, max_files=6)

    assert len(selected) <= 20
    assert len({item["file"] for item in selected}) <= 6
    assert selected[0]["type"] == "import_error"
    assert selected[0]["file"] == "main.py"
    assert sum(1 for item in selected if item["message"] == "no app.main") == 1


def test_is_review_timeout_detects_timeout_errors():
    from app.agent.cross_validator import is_review_timeout
    from app.agent.llm_client import LLMClientError

    assert is_review_timeout(TimeoutError("timed out"))
    assert is_review_timeout(LLMClientError("LLM 流式调用超时 (300s): glm"))
    assert is_review_timeout(RuntimeError("httpx.TimeoutException"))
    assert not is_review_timeout(ValueError("bad json"))


def test_validate_and_fix_skips_llm_on_timeout():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    ctx = SharedContext("test", Path("."))
    validator = CrossValidator(ctx)
    files = {"main.py": "def app():\n    return 1\n"}

    async def boom(*_args, **_kwargs):
        raise TimeoutError("LLM 调用超时 (300s)")

    validator._fix_with_llm = boom
    async def fake_consistency(*_args, **_kwargs):
        return [{"type": "api_contract", "file": "main.py", "message": "route mismatch"}]

    validator.validate_cross_file_consistency = fake_consistency
    with pytest.raises(TimeoutError, match="LLM 调用超时"):
        asyncio.run(validator.validate_and_fix(files, {}, fix_model="glm"))


def test_clean_code_block_strips_unclosed_think():
    from app.agent.utils import clean_code_block

    dumped = "<think>\n好的，我现在需要帮用户修复他们的Python文件\n"
    assert clean_code_block(dumped) == ""

    wrapped = "<think>plan</think>\n```python\ndef greet(name):\n    return name\n```"
    assert "def greet" in clean_code_block(wrapped)


def test_accept_llm_fix_rejects_thinking_dump():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", Path(".")))
    original = "def greet(name):\n    return f'Hello, {name}'\n"
    dumped = "<think>\n好的，我现在需要帮用户修复他们的Python文件中的问题。\n"
    assert validator._accept_llm_fix("src/greet.py", dumped, original) is None

    parsed = validator._parse_batch_fix_result(dumped, ["src/greet.py"])
    assert validator._accept_llm_fix("src/greet.py", parsed.get("src/greet.py", ""), original) is None


def test_accept_llm_fix_keeps_valid_python():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", Path(".")))
    original = "def greet(name):\n    return name\n"
    fixed = "def greet(name):\n    return f'Hello, {name}'\n"
    assert validator._accept_llm_fix("src/greet.py", fixed, original) == fixed.strip()


def test_fix_with_llm_keeps_original_on_thinking_dump():
    from unittest.mock import patch
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    original = "def greet(name):\n    return f'Hello, {name}'\n"
    files = {"src/greet.py": original}
    issues = [{"type": "missing_argument", "file": "src/greet.py", "message": "x"}]
    validator = CrossValidator(SharedContext("test", Path(".")))

    async def fake_llm(**_kwargs):
        return {
            "choices": [
                {"message": {"content": "<think>\n好的，我现在需要帮用户修复他们的Python文件\n"}}
            ]
        }

    with patch("app.agent.cross_validator.call_llm", side_effect=fake_llm):
        fixed = asyncio.run(validator._fix_with_llm(files, issues, "glm"))
    assert fixed["src/greet.py"] == original


def test_generate_missing_modules_raises_when_file_absent():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", Path(".")))
    with pytest.raises(RuntimeError, match="missing modules were not generated"):
        asyncio.run(validator._generate_missing_modules(
            {"main.py": "import helper"},
            ["helper"],
            {},
            model="glm",
        ))


def test_package_entry_content_rejects_plain_modules():
    from app.agent.orchestrator_generation.spec_first_generate import _package_entry_content

    class Adapter:
        package_init_filename = "__init__.py"

    assert _package_entry_content("app/utils.py", None, Adapter(), {}) is None


def _python_validator():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext
    from app.agent.adapters.python import PythonLanguageAdapter

    return CrossValidator(SharedContext("test", Path(".")), language_adapter=PythonLanguageAdapter())


def _symbol_issues(files):
    validator = _python_validator()
    issues = asyncio.run(
        validator.validate_cross_file_consistency(files, {"language": "python"})
    )
    return [issue for issue in issues if issue["type"].startswith("symbol_")]


def test_symbol_check_ignores_instance_and_class_attributes():
    files = {
        "calc.py": (
            "class Calculator:\n"
            "    KIND = \"calc\"\n"
            "\n"
            "    def __init__(self):\n"
            "        self.total = 0\n"
            "\n"
            "    def add(self, value):\n"
            "        self.total += value\n"
            "        return self.total\n"
        ),
        "main.py": (
            "from calc import Calculator\n"
            "\n"
            "calc = Calculator()\n"
            "print(Calculator.KIND, calc.add(5))\n"
        ),
    }
    assert _symbol_issues(files) == []


def test_symbol_check_ignores_dotted_and_external_calls():
    files = {
        "app.py": (
            "import json\n"
            "from flask import Flask\n"
            "\n"
            "app = Flask(__name__)\n"
            "\n"
            "@app.route(\"/\")\n"
            "def index():\n"
            "    return json.dumps({\"ok\": True})\n"
        ),
    }
    assert _symbol_issues(files) == []


def test_symbol_check_still_flags_undefined_function():
    files = {"main.py": "def run():\n    return missing_helper()\n"}
    messages = [issue["message"] for issue in _symbol_issues(files)]
    assert any("missing_helper" in message for message in messages)


def test_generate_missing_modules_raises_when_file_absent():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    validator = CrossValidator(SharedContext("test", Path(".")))
    with pytest.raises(RuntimeError, match="missing modules were not generated"):
        asyncio.run(validator._generate_missing_modules(
            {"main.py": "import helper"},
            ["helper"],
            {},
            model="glm",
        ))


def test_package_entry_content_rejects_plain_modules():
    from app.agent.orchestrator_generation.spec_first_generate import _package_entry_content

    class Adapter:
        package_init_filename = "__init__.py"

    assert _package_entry_content("app/utils.py", None, Adapter(), {}) is None
