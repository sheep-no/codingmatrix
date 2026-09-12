import json

import pytest

from app.agent.architect import Architect
from app.agent.complexity import ComplexityAnalysis, ProjectComplexity
from app.agent.generation_plan import GenerationPlan


def _simple_complexity() -> ComplexityAnalysis:
    return ComplexityAnalysis(
        level=ProjectComplexity.SIMPLE,
        estimated_files=1,
        has_frontend=False,
        has_backend=False,
        has_database=False,
        has_auth=False,
        key_technologies=["Python"],
        risk_factors=[],
    )


def _architect() -> Architect:
    agent = Architect.__new__(Architect)
    from app.agent.architect_json_parser import ArchitectJsonParser
    agent.json_parser = ArchitectJsonParser()
    agent.model_name = "glm-4.7-flash"
    return agent


def test_canonicalize_parses_glm_string_fields():
    architect = _architect()
    architecture = {
        "project_type": "script",
        "language": "python",
        "project_spec": json.dumps({"default": {"terminology": {"hello": "Hello"}}}),
        "file_plan": json.dumps([
            {
                "path": "hello.py",
                "file_type": "entry",
                "language": "python",
                "imports": [],
                "contract": json.dumps({"exports": ["main"]}),
            }
        ]),
        "interfaces": json.dumps({"hello.py": {"exports": ["main"]}}),
        "api_spec": "{}",
        "db_schema": "{}",
        "dependencies": "{}",
    }

    result = architect._canonicalize_architecture(
        architecture,
        "写一个 Python hello world 脚本",
        _simple_complexity(),
        "python",
        None,
    )

    assert isinstance(result["project_spec"], dict)
    assert result["project_spec"]["default"]["terminology"]["hello"] == "Hello"
    assert isinstance(result["file_plan"], list)
    assert result["file_plan"][0]["path"] == "hello.py"
    assert isinstance(result["file_plan"][0]["contract"], dict)
    assert result["file_plan"][0]["contract"]["exports"] == ["main"]
    assert isinstance(result["interfaces"], list)
    assert result["interfaces"][0]["module"] == "hello.py"
    assert isinstance(result["api_spec"], dict)
    assert isinstance(result["db_schema"], dict)
    plan = GenerationPlan.from_architecture(result)
    assert [item.path for item in plan.files] == ["hello.py"]


@pytest.mark.asyncio
async def test_design_architecture_canonicalizes_glm_string_payload():
    architect = _architect()
    parsed = {
        "project_type": "script",
        "project_spec": '{"default": {"terminology": {}}}',
        "file_plan": '[{"path": "hello.py", "file_type": "entry", "language": "python"}]',
        "interfaces": "hello.py exposes main",
        "api_spec": "{}",
        "db_schema": "{}",
    }
    async def fake_call(prompt, system_prompt="", stream=False, thinking_budget=None):
        return json.dumps(parsed)

    architect.call_llm = fake_call
    result = await architect.design_architecture(
        "写一个 Python hello world 脚本",
        _simple_complexity(),
    )

    assert isinstance(result["project_spec"], dict)
    assert isinstance(result["file_plan"], list)
    assert result["file_plan"][0]["path"] == "hello.py"
    assert isinstance(result["interfaces"], dict)
    GenerationPlan.from_architecture(result)


def test_enhance_api_spec_does_not_invent_health():
    architect = _architect()
    result = architect._validate_and_enhance_api_spec(
        {"api_spec": {}},
        _simple_complexity(),
    )
    assert result["api_spec"] == {}


def test_enhance_db_schema_does_not_invent_users():
    architect = _architect()
    result = architect._validate_and_enhance_db_schema(
        {"db_schema": {}},
        _simple_complexity(),
    )
    assert result["db_schema"] == {}


def test_hello_fallback_stays_single_file():
    architect = _architect()
    result = architect._get_requirement_aware_default_architecture(
        "写一个 Python 文件 hello.py，运行后打印 Hello World。"
        "只要这一个文件，不要数据库、不要前端、不要测试。",
        _simple_complexity(),
        language="python",
    )
    assert [item["path"] for item in result["file_plan"]] == ["hello.py"]
    assert result["api_spec"] == {}
    assert result["db_schema"] == {}
    assert not result["project_spec"]["default"].get("framework")
