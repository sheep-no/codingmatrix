"""`agent_core.ProjectGeneratorAgent._parse_tool_calls` 尝试4 路径回归。

LLM 未走工具调用格式、直接输出代码块时，原实现把目标路径硬编码为
`./projects/user_api/{filename}`，无视本次生成的 output_dir，导致文件写到
错误位置。修复后按传入 output_dir 拼装，缺省回退 ./projects。
"""
from pathlib import Path

from app.utils.agent_core import ProjectGeneratorAgent

DIRECT_CODE_BLOCK = """main.py:
```python
print("hi")
```
"""


def _parse(content: str, output_dir=None):
    # _parse_tool_calls 不依赖实例字段，绕过 pydantic 初始化
    agent = object.__new__(ProjectGeneratorAgent)
    return agent._parse_tool_calls(content, output_dir)


def test_direct_code_block_uses_output_dir():
    output_dir = "./projects/20260101_ab_user_1"
    tool_calls, _ = _parse(DIRECT_CODE_BLOCK, output_dir)
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "create_project_file"
    args = tool_calls[0]["function"]["arguments"]
    assert args["file_path"] == str(Path(output_dir) / "main.py")


def test_direct_code_block_default_has_no_hardcoded_user_api():
    tool_calls, _ = _parse(DIRECT_CODE_BLOCK)
    args = tool_calls[0]["function"]["arguments"]
    assert "user_api" not in args["file_path"]
    assert args["file_path"].endswith("main.py")
