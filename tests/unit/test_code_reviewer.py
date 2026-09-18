"""CodeReviewer 对文档/文本类文件的审查口径。

文档不是代码：审查器不得对文档内容做基于 import 的版本兼容性扫描，也不得把
文档里描述的其他文件、目录或包结构判为本文件的高风险问题。
"""
import json
from unittest.mock import AsyncMock

import pytest

from app.agent.code_reviewer import CodeReviewer


class _StubReviewer(CodeReviewer):
    @property
    def SYSTEM_PROMPT(self) -> str:
        return "stub-system-prompt"


def _reviewer():
    reviewer = object.__new__(_StubReviewer)
    captured = {}

    async def fake_call_llm(prompt, _system_prompt):
        captured["prompt"] = prompt
        return json.dumps({
            "approved": True,
            "risk_level": "low",
            "issues": [],
            "suggestions": [],
            "needs_fix": False,
        })

    reviewer.call_llm = fake_call_llm
    reviewer._check_version_compatibility = AsyncMock(return_value=["版本不兼容"])
    return reviewer, captured


@pytest.mark.asyncio
async def test_documentation_review_skips_version_scan_and_scopes_prompt():
    reviewer, captured = _reviewer()

    result = await reviewer.review_code(
        "# 项目\n\n包含 src/greeting.py 与 main.py。\n", "README.md", "一行项目说明"
    )

    reviewer._check_version_compatibility.assert_not_awaited()
    assert "version_issues" not in result
    assert "不得据此判定本文件存在高风险" in captured["prompt"]
    assert "请审查以下代码" not in captured["prompt"]


@pytest.mark.asyncio
async def test_source_review_runs_version_scan():
    reviewer, captured = _reviewer()

    result = await reviewer.review_code("import fastapi\n", "main.py", "entry")

    reviewer._check_version_compatibility.assert_awaited_once()
    assert result["version_issues"] == ["版本不兼容"]
    assert "请审查以下代码" in captured["prompt"]
