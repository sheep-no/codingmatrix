import pytest

from app.agent import utils


@pytest.mark.parametrize(
    ("label", "file_path"),
    (("app/main.py", "app/main.py"), ("File: src/app.ts", "src/app.ts")),
)
def test_strip_leading_file_label(label, file_path):
    content = f"{label}\nprint('ready')\n"

    assert utils.strip_leading_file_label(content, file_path) == "print('ready')\n"


def test_strip_leading_file_label_preserves_regular_first_line():
    content = "from pathlib import Path\n"

    assert utils.strip_leading_file_label(content, "app/main.py") == content


def test_clean_code_block_strips_leading_think_block():
    content = "<think>let me plan</think>\n```python\nx = 1\n```"

    assert utils.clean_code_block(content) == "x = 1"


def test_clean_code_block_keeps_think_literal_inside_code():
    content = 'PROMPT = "<think>请思考</think>"\ndef build():\n    return PROMPT\n'

    assert utils.clean_code_block(content) == content.strip()


def test_clean_code_block_keeps_thinking_literal_in_docstring():
    content = '"""解释 <thinking> 标签的用法"""\ndef doc():\n    pass\n'

    assert utils.clean_code_block(content) == content.strip()


def test_reusable_existing_file_content_accepts_complete_python():
    content = "def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()\n"
    reusable, reason = utils.reusable_existing_file_content("hello.py", content)
    assert reusable is True
    assert reason == ""


def test_reusable_existing_file_content_rejects_stub_and_metadata():
    stub_ok, stub_reason = utils.reusable_existing_file_content("app.py", "pass\n")
    assert stub_ok is False
    assert stub_reason

    meta_ok, meta_reason = utils.reusable_existing_file_content(
        "main.py",
        '{"status": "ok", "message": "file written", "file_path": "main.py"}',
    )
    assert meta_ok is False
    assert meta_reason


def test_extract_rejects_tool_call_json_before_persistence(tmp_path):
    content = '{"tool":"read_file","params":{"path":"app/models.py"}}'
    assert utils.is_placeholder_content(content, "app/models.py")[0] is True


def test_placeholder_accepts_tool_registry_data():
    """工具注册表里的 {"tool": ..., "params": ...} 是合法业务数据，不是泄漏。"""
    content = (
        "TOOLS = [\n"
        '    {"tool": "search", "params": {"q": "text"}},\n'
        '    {"tool": "calc", "params": {"expr": "1+1"}},\n'
        "]\n"
        "\n"
        "\n"
        "def get_tool(name):\n"
        '    return next((t for t in TOOLS if t["tool"] == name), None)\n'
    )

    assert utils.is_placeholder_content(content, "app/tools.py")[0] is False


def test_placeholder_accepts_llm_function_schema():
    content = (
        'SCHEMA = {"tool": "get_weather", "params": {"city": "beijing"}}\n'
        "\n"
        "\n"
        "def build_prompt(schema):\n"
        "    return str(schema)\n"
    )

    assert utils.is_placeholder_content(content, "app/llm.py")[0] is False


def test_placeholder_rejects_whole_content_tool_call_json():
    assert utils.is_placeholder_content('{"tool": "search"}\n', "app/x.py")[0] is True


def test_placeholder_accepts_module_docstring_with_reexports():
    content = '"""Module: app.services"""\nfrom .auth import login\n'

    assert utils.is_placeholder_content(content, "app/__init__.py")[0] is False


def test_placeholder_accepts_small_implementation_with_todo_comment():
    content = "# TODO: 支持环境变量\ndef get():\n    return 1\n"

    assert utils.is_placeholder_content(content, "app/config.py")[0] is False


def test_placeholder_rejects_todo_without_effective_code():
    assert utils.is_placeholder_content("# TODO: implement\n", "app/mod.py")[0] is True


def test_placeholder_rejects_truncated_llm_output():
    content = '''import json
from fastapi import FastAPI

app = FastAPI()

@router.post("/login")
async def login():
    return {"access_token": "token123"}

# 其他路由和功能保持不变
# ...（后续代码与用户提供的原始代码相同，未展示完整）
'''
    is_placeholder, reason = utils.is_placeholder_content(content, "main.py")
    assert is_placeholder is True
    assert reason


def test_placeholder_accepts_docs_with_changelog_prose():
    content = "# 更新日志\n\n## v1.2\n\n- 新增登录接口\n- 其他代码保持不变\n"

    assert utils.is_placeholder_content(content, "README.md")[0] is False


def test_placeholder_accepts_docs_with_english_truncation_prose():
    content = "# Guide\n\nAfter the change, the rest of the code remains the same.\n"

    assert utils.is_placeholder_content(content, "docs/guide.md")[0] is False


def test_compact_project_context_keeps_current_file_only():
    context = {
        "requirement": "工单服务",
        "architecture": {
            "language": "python",
            "tech_stack": ["fastapi"],
            "file_plan": [
                {"path": "main.py", "file_type": "entry", "description": "入口", "imports": [], "contract": {"exports": ["app"]}},
                {"path": "models.py", "file_type": "model", "description": "模型"},
            ],
        },
    }
    compact = utils.compact_project_context_for_file("main.py", context)
    assert "models.py" not in compact
    assert "工单服务" in compact
    assert "entry" in compact


def test_compact_project_context_keeps_original_content_for_modify():
    context = {
        "requirement": "补全 subtract 和 multiply",
        "original_content": "from calc import add, subtract, multiply\nprint(add(1, 2)\n",
        "modification_reason": "补上 main.py 缺失的右括号",
        "architecture": {
            "language": "python",
            "file_plan": [
                {"path": "main.py", "file_type": "entry", "description": "入口"},
            ],
        },
    }
    compact = utils.compact_project_context_for_file("main.py", context)
    assert "from calc import add, subtract, multiply" in compact
    assert "is_modification" in compact
    assert "补上 main.py 缺失的右括号" in compact


@pytest.mark.asyncio
async def test_validate_language_with_llm_skips_model_call_for_python():
    called = []

    async def llm_caller(_prompt):
        called.append(1)
        return "NO"

    is_valid, reason = await utils.validate_language_with_llm(
        file_path="main.py",
        content="def main():\n    return 'ready'\n",
        expected_language="Python",
        llm_caller=llm_caller,
    )

    assert is_valid is True
    assert reason == ""
    assert called == []
