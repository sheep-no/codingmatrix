from pathlib import Path

from fastapi import HTTPException

from app.api.v1.ai_agent.orchestrate_endpoints import _generation_http_exception
from app.api.v1.ai_agent.orchestrate_endpoints import _generation_result_error


def test_agent_entrypoints_pass_database_context_to_workflow_runner():
    generate_source = Path("app/api/v1/ai_agent/generate_endpoints.py").read_text(encoding="utf-8")
    orchestrate_source = Path("app/api/v1/ai_agent/orchestrate_endpoints.py").read_text(encoding="utf-8")

    assert generate_source.count("db=db") >= 1
    assert orchestrate_source.count("db=db") >= 3


def test_provider_configuration_failure_is_actionable_service_unavailable():
    error = _generation_http_exception(
        RuntimeError("All providers failed. Last error: Provider siliconflow is not configured")
    )

    assert isinstance(error, HTTPException)
    assert error.status_code == 503
    assert "siliconflow" in error.detail


def test_unexpected_generation_failure_remains_internal_error():
    error = _generation_http_exception(RuntimeError("database exploded"))

    assert error.status_code == 500
    assert error.detail == "项目生成失败: database exploded"


def test_unsuccessful_generation_result_has_error_terminal_state():
    assert _generation_result_error({"success": False, "errors": ["crud.py 生成失败"]}) == "crud.py 生成失败"
    assert _generation_result_error({"success": True, "errors": []}) is None
