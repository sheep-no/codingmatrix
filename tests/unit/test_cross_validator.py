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


def _model_issues(files):
    validator = _python_validator()
    issues = asyncio.run(
        validator.validate_cross_file_consistency(files, {"language": "python"})
    )
    return [issue for issue in issues if issue["type"] == "model_mismatch"]


def test_pydantic_model_fields_are_kept_for_sqlalchemy_scan():
    # `(BaseModel)` 曾命中 SQLAlchemy 的 Base 正则并用空字段覆盖 pydantic 模型
    files = {
        "schemas.py": (
            "from pydantic import BaseModel\n"
            "\n"
            "class UserOut(BaseModel):\n"
            "    id: int\n"
            "    name: str\n"
        ),
        "crud.py": (
            "from schemas import UserOut\n"
            "\n"
            "def make(user_id: int, name: str) -> UserOut:\n"
            "    return UserOut(id=user_id, name=name)\n"
        ),
    }
    assert _model_issues(files) == []


def test_model_mismatch_ignores_comments_and_docstrings():
    files = {
        "schemas.py": (
            "from pydantic import BaseModel\n"
            "\n"
            "class Ping(BaseModel):\n"
            "    ok: bool\n"
        ),
        "main.py": (
            "from schemas import Ping\n"
            "\n"
            "def build():\n"
            '    """用法示例: Ping(extra=1)"""\n'
            "    # Ping(retired=True) 是旧写法\n"
            "    return Ping(ok=True)\n"
        ),
    }
    assert _model_issues(files) == []


def test_model_mismatch_still_flags_unknown_field():
    files = {
        "schemas.py": (
            "from pydantic import BaseModel\n"
            "\n"
            "class Ping(BaseModel):\n"
            "    ok: bool\n"
        ),
        "main.py": 'from schemas import Ping\n\nping = Ping(ok=True, missing=True)\n',
    }
    messages = [issue["message"] for issue in _model_issues(files)]
    assert any("missing" in message for message in messages)


def test_model_check_matches_complete_identifier():
    files = {
        "models.py": (
            "from pydantic import BaseModel\n"
            "class Item(BaseModel):\n"
            "    id: int\n"
            "class LineItem(BaseModel):\n"
            "    sku: str\n"
            "    qty: int\n"
        ),
        "service.py": (
            "from models import Item, LineItem\n"
            "line = LineItem(sku='x', qty=2)\n"
            "item = Item(id=1)\n"
        ),
    }
    assert _model_issues(files) == []
    files["service.py"] += "invalid = Item(id=1, sku='x')\n"
    issues = _model_issues(files)
    assert len(issues) == 1
    assert "sku" in issues[0]["message"]


def test_model_check_ignores_nested_call_arguments():
    # 字段值里的嵌套调用参数（parse(raw=1)）不是模型字段
    files = {
        "models.py": (
            "from pydantic import BaseModel\n"
            "class Item(BaseModel):\n"
            "    id: int\n"
            "    name: str\n"
        ),
        "service.py": "item = Item(id=parse(raw=1, strict=True), name='x')\n",
    }
    assert _model_issues(files) == []


def _api_contract_issues(files):
    validator = _python_validator()
    issues = asyncio.run(
        validator.validate_cross_file_consistency(files, {"language": "python"})
    )
    return [issue for issue in issues if issue["type"] == "api_mismatch"]


def _fastapi_items_backend(fields=("id", "name")):
    annotations = "".join(f"    {name}: int\n" for name in fields)
    return (
        "from fastapi import FastAPI\n"
        "from pydantic import BaseModel\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "class ItemOut(BaseModel):\n"
        f"{annotations}"
        "\n"
        '@app.get("/api/items", response_model=ItemOut)\n'
        "def list_items():\n"
        "    return ItemOut(id=1, name='pen')\n"
    )


def test_symbol_check_ignores_js_runtime_globals():
    # fetch/setTimeout/Promise 等浏览器全局由运行时提供，不是项目定义
    files = {
        "src/runtime.js": (
            "export function boot() {\n"
            "  const parsed = parseInt('42', 10)\n"
            "  setTimeout(() => console.log(parsed), 10)\n"
            "  fetch('/api/items').then((res) => res.json())\n"
            "  return Promise.resolve(new Date())\n"
            "}\n"
        ),
    }
    assert _symbol_issues(files) == []


def test_api_contract_ignores_array_and_response_members():
    files = {
        "main.py": _fastapi_items_backend(),
        "src/api.js": (
            "export async function loadAll() {\n"
            "  const res = await fetch('/api/items')\n"
            "  const items = await res.json()\n"
            "  const total = items.length,\n"
            "    first = items[0]\n"
            "  return items.map((it) => it.name), total, first, res.status\n"
            "}\n"
        ),
    }
    assert _api_contract_issues(files) == []


def test_api_contract_prefers_exact_route_over_path_param_route():
    # GET /api/items 应命中同名路由，而不是被 /api/items/{item_id} 前缀抢先匹配
    files = {
        "main.py": (
            "from fastapi import FastAPI\n"
            "from pydantic import BaseModel\n"
            "\n"
            "app = FastAPI()\n"
            "\n"
            "class ItemDetail(BaseModel):\n"
            "    id: int\n"
            "    name: str\n"
            "\n"
            "class ItemSummary(BaseModel):\n"
            "    total: int\n"
            "\n"
            '@app.get("/api/items/{item_id}", response_model=ItemDetail)\n'
            "def get_item(item_id: int):\n"
            "    return ItemDetail(id=item_id, name='pen')\n"
            "\n"
            '@app.get("/api/items", response_model=ItemSummary)\n'
            "def list_items():\n"
            "    return ItemSummary(total=1)\n"
        ),
        "src/api.js": (
            "export async function load() {\n"
            "  const res = await fetch('/api/items')\n"
            "  const body = await res.json()\n"
            "  return body.total\n"
            "}\n"
        ),
    }
    assert _api_contract_issues(files) == []


def test_api_contract_still_flags_unknown_response_field():
    files = {
        "main.py": _fastapi_items_backend(),
        "src/api.js": (
            "export async function load() {\n"
            "  const res = await fetch('/api/items')\n"
            "  const data = await res.json()\n"
            "  return { sku: data.sku }\n"
            "}\n"
        ),
    }
    messages = [issue["message"] for issue in _api_contract_issues(files)]
    assert any("sku" in message for message in messages)


def test_api_contract_ignores_unrelated_object_properties():
    # fetch 之后无关对象的属性不是响应字段
    files = {
        "main.py": _fastapi_items_backend(),
        "src/api.js": (
            "export async function load() {\n"
            "  const res = await fetch('/api/items')\n"
            "  const data = await res.json()\n"
            "  track(event.name, { page: config.pageTitle, ua: navigator.userAgent })\n"
            "  return data.id\n"
            "}\n"
        ),
    }
    assert _api_contract_issues(files) == []


def test_api_contract_still_flags_body_field_missing():
    # data.items 是对响应体的真实字段访问，后端未返回时应报出
    files = {
        "main.py": _fastapi_items_backend(),
        "src/api.js": (
            "export async function load() {\n"
            "  const res = await fetch('/api/items')\n"
            "  const data = await res.json()\n"
            "  return data.items\n"
            "}\n"
        ),
    }
    messages = [issue["message"] for issue in _api_contract_issues(files)]
    assert any("items" in message for message in messages)


def test_api_contract_reads_axios_response_data():
    # axios 的响应字段在 res.data 上，不应误报
    files = {
        "main.py": _fastapi_items_backend(),
        "src/api.js": (
            "export async function load() {\n"
            "  const res = await axios.get('/api/items')\n"
            "  const total = res.data.id\n"
            "  return total\n"
            "}\n"
        ),
    }
    assert _api_contract_issues(files) == []


def test_validate_imports_flags_missing_project_module_only():
    files = {
        "app/__init__.py": "",
        "app/main.py": (
            "import os\n"
            "from typing import List\n"
            "from fastapi import FastAPI\n"
            "from .models import User\n"
            "from app.services import load\n"
        ),
        "app/models.py": "class User:\n    pass\n",
    }
    validator = _python_validator()
    issues = validator._validate_imports(files)
    assert [issue["message"] for issue in issues] == ["导入的模块不存在: app.services"]


def test_validate_imports_accepts_namespace_package_without_init():
    # Python 3 命名空间包允许目录没有 __init__.py，
    # `from app import models` 在 app/models.py 存在时是合法导入
    files = {
        "app/models.py": "class User:\n    pass\n",
        "app/main.py": "from app import models\n",
    }
    validator = _python_validator()
    assert validator._validate_imports(files) == []


def test_validate_imports_accepts_aliased_and_star_imports():
    files = {
        "app/models.py": "class User:\n    pass\n",
        "app/main.py": (
            "from app import models as m\n"
            "from app.models import *\n"
        ),
    }
    validator = _python_validator()
    assert validator._validate_imports(files) == []


def test_validate_imports_flags_package_dir_without_target_file():
    # 同目录下存在其它文件，不代表任意子模块都存在
    files = {
        "app/other.py": "x = 1\n",
        "app/main.py": "from app.missing import load\n",
    }
    validator = _python_validator()
    assert [issue["message"] for issue in validator._validate_imports(files)] == [
        "导入的模块不存在: app.missing"
    ]


def test_validate_imports_flags_missing_top_level_package_without_adapter():
    # 通用（无适配器）路径同样不能用目录前缀掩盖缺失的顶层包
    files = {
        "app/other.py": "x = 1\n",
        "app/main.py": "from something_else import load\n",
    }
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext

    generic = CrossValidator(SharedContext("test", Path(".")), language_adapter=None)
    assert [issue["message"] for issue in generic._validate_imports(files)] == [
        "导入的模块不存在: something_else"
    ]


@pytest.mark.parametrize(
    "specifier, target",
    [
        ("@/components/Button.vue", "src/components/Button.vue"),
        ("@/data/items.json", "src/data/items.json"),
        ("@/styles/main.css", "src/styles/main.css"),
        ("@/assets/logo.svg", "src/assets/logo.svg"),
    ],
)
def test_validate_imports_resolves_alias_with_explicit_extension(specifier, target):
    # 扩展名补全曾把 `@/x.vue` 拼成 `x.vue.js`，让带显式扩展名的别名导入永远匹配不上
    files = {
        target: "export default 1\n",
        "src/App.jsx": f"import value from '{specifier}'\n",
    }
    assert _js_validator()._validate_imports(files) == []


def test_validate_imports_still_flags_missing_alias_with_explicit_extension():
    files = {
        "src/App.jsx": "import Missing from '@/components/Missing.vue'\n",
    }
    assert [issue["message"] for issue in _js_validator()._validate_imports(files)] == [
        "导入的模块不存在: @/components/Missing.vue"
    ]


@pytest.mark.parametrize(
    "specifier, target",
    [
        ("@/components/HelloWorld", "src/components/HelloWorld.vue"),
        ("@/components/Card", "src/components/Card/index.vue"),
        ("src/components/HelloWorld", "src/components/HelloWorld.vue"),
    ],
)
def test_validate_imports_resolves_alias_to_vue_component(specifier, target):
    # 别名候选不含 .vue 时，指向单文件组件的省略扩展名导入会被误报
    files = {
        target: "<template><div/></template>\n",
        "src/App.vue": f"<script setup>\nimport value from '{specifier}'\n</script>\n",
    }
    assert _js_validator()._validate_imports(files) == []


def test_validate_imports_still_flags_missing_vue_component():
    files = {
        "src/components/Other.vue": "<template/>\n",
        "src/App.vue": "<script setup>\nimport Nope from '@/components/Nope'\n</script>\n",
    }
    assert [issue["message"] for issue in _js_validator()._validate_imports(files)] == [
        "导入的模块不存在: @/components/Nope"
    ]


def test_validate_imports_prefers_existing_js_over_vue():
    files = {
        "src/utils/a.js": "export const x = 1\n",
        "src/utils/a.vue": "<template/>\n",
        "src/App.jsx": "import { x } from '@/utils/a'\n",
    }
    assert _js_validator()._validate_imports(files) == []


def _missing_argument_issues(files):
    validator = _python_validator()
    issues = validator._validate_function_signatures(files)
    return [issue["message"] for issue in issues]


def test_signature_check_ignores_comments_docstrings_and_strings():
    # 注释、docstring、字符串字面量里的示例调用不是真实调用
    files = {
        "a.py": (
            "def build(a, b):\n"
            "    return a + b\n"
            "\n"
            "def deploy(target, mode):\n"
            "    return target\n"
        ),
        "b.py": (
            "# legacy build(1) signature\n"
            'MSG = "run deploy(prod) to ship"\n'
            "\n"
            "def helper():\n"
            '    """Use build(1) for quick work."""\n'
            "    return 1\n"
        ),
    }
    assert _missing_argument_issues(files) == []


def test_signature_check_counts_nested_call_arguments():
    # f(g(1), 2) 提供了两个实参，不能被第一个 ) 提前截断而误报缺参
    files = {
        "a.py": "def build(name, opts):\n    return name\n",
        "b.py": (
            "def norm(value):\n"
            "    return value\n"
            "\n"
            "result = build(norm('a'), {'k': 1})\n"
        ),
    }
    assert _missing_argument_issues(files) == []


def test_signature_check_skips_ambiguous_same_name_definitions():
    # 同名函数在多个文件定义且签名不同，无法判定调用点用哪一份，跳过而不是误报
    files = {
        "b.py": "def handle():\n    return 1\n",
        "a.py": "def handle(event, ctx):\n    return event\n",
        "c.py": "handle()\n",
    }
    assert _missing_argument_issues(files) == []


def test_signature_check_skips_method_calls():
    files = {
        "a.py": "def save(path, data):\n    return path\n",
        "store.py": (
            "class Store:\n"
            "    def save(self):\n"
            "        return 1\n"
            "\n"
            "store = Store()\n"
            "store.save()\n"
        ),
    }
    assert _missing_argument_issues(files) == []


def test_signature_check_still_reports_missing_cross_file_argument():
    files = {
        "calc.py": "def connect(host, port):\n    return host\n",
        "main.py": "from calc import connect\n\nconnect('localhost')\n",
    }
    messages = _missing_argument_issues(files)
    assert len(messages) == 1
    assert "port" in messages[0]


def test_signature_check_skips_star_args_unpacking():
    # 调用点用 *args / **kwargs 展开，实参个数静态未知，不应报缺参
    files = {
        "calc.py": "def connect(host, port):\n    return host\n",
        "main.py": (
            "from calc import connect\n"
            "args = ('localhost', 80)\n"
            "kw = {'host': 'x', 'port': 80}\n"
            "connect(*args)\n"
            "connect(**kw)\n"
            "connect(*(1, 2))\n"
        ),
    }
    assert _missing_argument_issues(files) == []


def test_signature_check_still_reports_missing_after_partial_positional():
    # 部分位置参数满足首个必需参数后，仍缺后续必需参数
    files = {
        "calc.py": "def build(name, opts, timeout):\n    return name\n",
        "main.py": "from calc import build\n\nbuild('n')\n",
    }
    messages = _missing_argument_issues(files)
    assert len(messages) == 2
    assert any("opts" in message for message in messages)
    assert any("timeout" in message for message in messages)


def _js_validator():
    from app.agent.cross_validator import CrossValidator
    from app.agent.shared_context import SharedContext
    from app.agent.adapters.javascript import JavaScriptLanguageAdapter

    return CrossValidator(
        SharedContext("test", Path(".")),
        language_adapter=JavaScriptLanguageAdapter(),
    )


def _js_symbol_messages(files):
    validator = _js_validator()
    issues = asyncio.run(
        validator.validate_cross_file_consistency(files, {"language": "javascript"})
    )
    return [issue["message"] for issue in issues if issue["type"].startswith("symbol_")]


def test_symbol_check_ignores_js_control_flow_and_methods():
    # if/for/while/switch 等关键字与方法定义不是符号引用
    files = {
        "src/Counter.jsx": (
            "import React from 'react'\n"
            "\n"
            "export default class Counter extends React.Component {\n"
            "  constructor(props) {\n"
            "    super(props)\n"
            "    this.state = { n: 0 }\n"
            "  }\n"
            "\n"
            "  increment() {\n"
            "    this.setState({ n: this.state.n + 1 })\n"
            "  }\n"
            "\n"
            "  render() {\n"
            "    return <button onClick={() => this.increment()}>{this.state.n}</button>\n"
            "  }\n"
            "}\n"
        ),
        "src/util.js": (
            "export function classify(value) {\n"
            "  if (value > 0) {\n"
            "    return 'pos'\n"
            "  }\n"
            "  for (let i = 0; i < 3; i += 1) {\n"
            "    value += i\n"
            "  }\n"
            "  while (value > 10) {\n"
            "    value -= 1\n"
            "  }\n"
            "  switch (value) {\n"
            "    case 1:\n"
            "      break\n"
            "  }\n"
            "  return value\n"
            "}\n"
        ),
    }
    assert _js_symbol_messages(files) == []


def test_symbol_check_ignores_default_exported_function_name():
    # export default function App() 是定义，不是对 App 的引用
    files = {
        "src/App.jsx": (
            "import Widget from './Widget'\n"
            "export default function App() {\n"
            "  return Widget()\n"
            "}\n"
        ),
        "src/Widget.jsx": "export default function Widget() {\n  return null\n}\n",
    }
    assert _js_symbol_messages(files) == []


def test_symbol_check_still_flags_undefined_js_symbol():
    files = {
        "src/main.js": (
            "export function boot() {\n"
            "  return missingHelper(1)\n"
            "}\n"
        ),
    }
    messages = _js_symbol_messages(files)
    assert any("missingHelper" in message for message in messages)


def test_symbol_check_skips_files_outside_adapter_extensions():
    # Python 适配器下，JS 文件不参与符号校验，避免跨语言误报
    files = {
        "backend/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n",
        "frontend/src/App.jsx": (
            "export default function App() {\n"
            "  return undefinedHelper(1)\n"
            "}\n"
        ),
    }
    validator = _python_validator()
    issues = asyncio.run(
        validator.validate_cross_file_consistency(files, {"language": "python"})
    )
    assert [issue for issue in issues if issue["type"].startswith("symbol_")] == []


def test_symbol_check_ignores_python_keywords_before_parens():
    # `not (x)`、`in (1, 2)`、`and (y)` 里的关键字不是符号引用
    files = {
        "main.py": (
            "values = [1, 2]\n"
            "if not (len(values) > 3):\n"
            "    print('ok')\n"
            "if 1 in (1, 2, 3):\n"
            "    print('contains')\n"
            "if (values and (len(values))):\n"
            "    print('truthy')\n"
            "if (1 == 1 or (2 == 2)):\n"
            "    print('logic')\n"
        ),
    }
    assert _symbol_issues(files) == []


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
