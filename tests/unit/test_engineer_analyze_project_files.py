"""Engineer.analyze 必须把项目文件结构注入分析 prompt。"""

import pytest

from app.agent.backend_engineer import BackendEngineer
from app.agent.frontend_engineer import FrontendEngineer


class _AnalyzeStub:
    """只实现 analyze 依赖的 call_llm / SYSTEM_PROMPT，避免构造真实 LLM 客户端。"""

    SYSTEM_PROMPT = "system"

    def __init__(self):
        self.prompts = []

    async def call_llm(self, prompt, system_prompt):
        self.prompts.append(prompt)
        return "analysis"


@pytest.mark.parametrize("engineer_cls", [BackendEngineer, FrontendEngineer])
async def test_analyze_includes_project_file_structure(engineer_cls, tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('hello')\n", encoding="utf-8")

    stub = _AnalyzeStub()
    result = await engineer_cls.analyze(
        stub, question="项目结构如何？", project_path=str(tmp_path)
    )

    assert result == "analysis"
    assert len(stub.prompts) == 1
    assert "app/main.py" in stub.prompts[0]
