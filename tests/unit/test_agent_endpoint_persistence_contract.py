from pathlib import Path


def test_agent_entrypoints_pass_database_context_to_workflow_runner():
    generate_source = Path("app/api/v1/ai_agent/generate_endpoints.py").read_text(encoding="utf-8")
    orchestrate_source = Path("app/api/v1/ai_agent/orchestrate_endpoints.py").read_text(encoding="utf-8")

    assert generate_source.count("db=db") >= 1
    assert orchestrate_source.count("db=db") >= 3
