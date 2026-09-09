import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app.agent.evaluation_runner import build_report_from_file, load_records, report_payload
from tests.manual import run_core_evaluation_case as evaluation_case_runner
from tests.manual.run_core_evaluation_case import (
    _failure_diagnostic,
    build_repair_change_plan,
    build_requirement,
    check_required_files,
    normalize_response_errors,
    record_from_summary,
    run_compile_check,
)
from app.utils.aicloud.llm_caller import (
    _SemaphoreWrappedAsyncIterator,
    _record_llm_call,
    _record_llm_response_metrics,
    _record_llm_stream_metrics,
    begin_llm_call_metrics,
    finish_llm_call_metrics,
)


def _record(case_id="python-fastapi-crud", **overrides):
    record = {
        "case_id": case_id,
        "plan_consistent": True,
        "interfaces_consistent": True,
        "dependency_closure": True,
        "files_complete": True,
        "compile_passed": True,
        "tests_passed": True,
        "startup_passed": True,
        "persistence_passed": True,
        "token_count": 10,
        "elapsed_seconds": 2.5,
    }
    record.update(overrides)
    return record


def test_runner_builds_json_compatible_report(tmp_path):
    input_path = tmp_path / "records.json"
    input_path.write_text(json.dumps([_record()]), encoding="utf-8")

    report = build_report_from_file(input_path)
    payload = report_payload(report)

    assert payload["summary"]["successful"] == 1
    assert "python-single-spec_first" in payload["missing_case_ids"]
    assert payload["matrix_complete"] is False
    assert payload["target_met"] is False


def test_load_records_rejects_invalid_record_shape():
    with pytest.raises(TypeError):
        load_records([{"case_id": "missing-fields"}])


def test_runner_rejects_non_array_input(tmp_path):
    input_path = tmp_path / "records.json"
    input_path.write_text(json.dumps({"records": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON array"):
        build_report_from_file(input_path)


def test_compile_check_reports_python_syntax_error(tmp_path):
    (tmp_path / "main.py").write_text("def broken(:\n", encoding="utf-8")

    result = run_compile_check(tmp_path, "python")

    assert result["supported"] is True
    assert result["passed"] is False
    assert result["stderr"] or result["stdout"]


def test_compile_check_reports_success(tmp_path):
    (tmp_path / "main.py").write_text("app = True\n", encoding="utf-8")

    result = run_compile_check(tmp_path, "python")

    assert result["supported"] is True
    assert result["passed"] is True


def test_compile_check_marks_unknown_language_unsupported(tmp_path):
    result = run_compile_check(tmp_path, "ruby")

    assert result["supported"] is False
    assert result["passed"] is False


def test_compile_check_uses_maven_for_java(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(command, 0, "compiled", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_compile_check(tmp_path, "java")

    assert result["passed"] is True
    assert result["command"] == ["mvn", "-q", "-DskipTests", "compile"]
    assert captured == {"command": result["command"], "cwd": tmp_path}


def test_required_file_check_reports_frozen_plan_gaps(tmp_path):
    (tmp_path / "app.py").write_text("app = True\n", encoding="utf-8")

    result = check_required_files(tmp_path, ("app.py", "tests/test_app.py"))

    assert result == {"passed": False, "missing": ["tests/test_app.py"]}


def test_repair_change_plan_adds_missing_files_and_modifies_existing_files(tmp_path):
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")

    plan = build_repair_change_plan(tmp_path, ("existing.py", "missing.py"))

    assert [(item["path"], item["action"]) for item in plan] == [
        ("existing.py", "modify"),
        ("missing.py", "add"),
    ]


def test_repair_change_plan_limits_existing_files_to_diagnostic_paths(tmp_path):
    (tmp_path / "stable.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("VALUE =\n", encoding="utf-8")

    plan = build_repair_change_plan(
        tmp_path,
        ("stable.py", "broken.py", "tests/test_app.py"),
        {"compile": {"passed": False, "stderr": "broken.py: syntax error"}},
    )

    assert [(item["path"], item["action"]) for item in plan] == [
        ("broken.py", "modify"),
        ("tests/test_app.py", "add"),
    ]


def test_repair_change_plan_repairs_full_contract_for_runtime_failures(tmp_path):
    required_files = (
        "app/main.py",
        "app/models.py",
        "app/schemas.py",
        "app/crud.py",
        "tests/test_crud.py",
    )
    for path in required_files:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# generated\n", encoding="utf-8")

    plan = build_repair_change_plan(
        tmp_path,
        required_files,
        {"runtime": {"passed": False, "stderr": "POST returned HTTP 422"}},
    )

    assert [item["path"] for item in plan] == list(required_files)


def test_repair_request_stays_within_endpoint_requirement_limit(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", str(tmp_path.parent))
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {"success": False}

    def post(*args, **kwargs):
        captured["requirement"] = kwargs["json"]["requirement"]
        assert kwargs["json"]["engine"] == "core"
        assert kwargs["json"]["incremental"] is True
        return Response()

    monkeypatch.setattr(evaluation_case_runner.httpx, "post", post)
    evaluation_case_runner.repair_generation_failure(
        "http://127.0.0.1:8000/api/v1/agent/orchestrate",
        "token",
        "python-small-spec_first",
        {"tests": {"passed": False, "stderr": "x" * 10000}},
        tmp_path,
    )

    assert len(captured["requirement"]) <= 5000


@pytest.mark.parametrize("relative_response", [False, True])
def test_repair_maps_response_directory_to_actual_orchestrator_target(tmp_path, monkeypatch, relative_response):
    from app.agent.orchestrator import OrchestratorAgent
    from app.api.v1.ai_agent.schemas import OrchestratorRequest
    from app.api.v1.ai_agent.orchestrate_endpoints import resolve_sync_output_dir

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", "./projects")
    target = tmp_path / "projects" / "1" / "canonical"
    target.mkdir(parents=True)

    class Response:
        status_code = 200

        def json(self):
            return {"success": True}

    def post(*args, **kwargs):
        request = OrchestratorRequest.model_validate(kwargs["json"])
        assert request.project_path == request.output_dir == "1/canonical"
        resolved = resolve_sync_output_dir(request.project_path, request.output_dir, "1", "unused")
        orchestrator = OrchestratorAgent(output_dir=resolved, memory_enabled=False)
        assert orchestrator.output_dir.resolve() == target
        return Response()

    monkeypatch.setattr(evaluation_case_runner.httpx, "post", post)
    evaluation_case_runner.repair_generation_failure(
        "http://localhost/unused", "token", "python-small-spec_first", {},
        target.relative_to(tmp_path) if relative_response else target,
    )


@pytest.mark.parametrize("target", ["outside/project", "projects"])
def test_repair_rejects_unmappable_directory_before_http(tmp_path, monkeypatch, target):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", "./projects")
    monkeypatch.setattr(evaluation_case_runner.httpx, "post", lambda *a, **kw: pytest.fail("unexpected HTTP"))
    with pytest.raises(ValueError, match="repair target must"):
        evaluation_case_runner.repair_generation_failure(
            "http://localhost/unused", "token", "python-small-spec_first", {}, Path(target),
        )


def test_initial_core_evaluation_request_selects_core(monkeypatch):
    class RequestCaptured(Exception):
        pass

    def post(*args, **kwargs):
        assert kwargs["json"]["engine"] == "core"
        assert kwargs["json"]["spec_first"] is True
        assert not kwargs["json"].get("incremental", False)
        raise RequestCaptured

    monkeypatch.setattr(evaluation_case_runner, "create_access_token", lambda **kw: "test-token")
    monkeypatch.setattr(evaluation_case_runner.httpx, "post", post)
    with pytest.raises(RequestCaptured):
        evaluation_case_runner.run_case("python-small-spec_first")


def test_run_case_rechecks_disk_after_failed_repair_response(tmp_path, monkeypatch):
    case = evaluation_case_runner.get_case("go-modular-traditional")
    failed = {
        "files_complete": {"passed": True, "missing": []},
        "compile": {"passed": False, "stderr": "compile failed"},
        "tests": {"passed": False, "stderr": "tests failed"},
        "runtime": {"passed": False, "stderr": "runtime failed"},
        "passed": False,
    }
    passed = {
        "files_complete": {"passed": True, "missing": []},
        "compile": {"passed": True},
        "tests": {"passed": True},
        "runtime": {"passed": True},
        "passed": True,
    }

    class Response:
        status_code = 200

        def json(self):
            return {
                "success": True,
                "output_dir": str(tmp_path),
                "files": [{"path": path} for path in case.required_files],
            }

    verifications = iter((failed, passed, passed))
    monkeypatch.setattr(evaluation_case_runner.httpx, "post", lambda *args, **kwargs: Response())
    monkeypatch.setattr(evaluation_case_runner, "_verify_case", lambda *args: next(verifications))
    monkeypatch.setattr(evaluation_case_runner, "repair_generation_failure", lambda *args: {
        "http_status": 200,
        "response": {
            "success": False,
            "files": [{"path": path} for path in case.required_files],
        },
    })

    summary = evaluation_case_runner.run_case(case.case_id)

    assert summary["repaired_passed"] is False
    assert summary["repair_stop_reason"] == "no_progress_repeated_diagnostic"
    assert summary["verification"] == passed


@pytest.mark.parametrize("case", (*evaluation_case_runner.CORE_EVALUATION_CASES, replace(
    evaluation_case_runner.CORE_EVALUATION_CASES[0],
    case_id="custom-inventory", framework="custom-framework", runtime="custom-runtime",
    request="Update inventory.", routes=(("PATCH", "/inventory/{sku}", 202),),
    http_contracts=(evaluation_case_runner.HttpContract(
        method="PATCH", path="/inventory/{sku}",
        request_body_schema={"type": "object", "properties": {"quantity": {"type": "integer"}}},
        response_body_schema={"type": "object", "properties": {"accepted": {"type": "boolean"}}},
        serialization_guidance="Encode inventory values using the configured JSON serializer.",
    ),),
)), ids=lambda case: case.case_id)
def test_initial_and_repair_requests_share_case_contract(case, tmp_path, monkeypatch):
    from app.api.v1.ai_agent.schemas import OrchestratorRequest

    monkeypatch.setattr("app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", str(tmp_path.parent))
    monkeypatch.setattr(evaluation_case_runner, "CORE_EVALUATION_CASES", (case,))
    requests = []
    existing = case.required_files[0]
    existing_path = tmp_path / existing
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text("fixture", encoding="utf-8")

    class Response:
        status_code = 200

        def json(self):
            return {"success": True, "output_dir": str(tmp_path), "files": [{"path": existing}]}

    def post(*args, **kwargs):
        requests.append(OrchestratorRequest.model_validate(kwargs["json"]).model_dump())
        return Response()

    failed = {
        "files_complete": {"passed": False, "missing": list(case.required_files[1:])},
        "compile": {"passed": False, "stderr": f"{existing}: broken"},
        "tests": {"passed": False},
        "runtime": {"passed": False},
        "passed": False,
    }
    monkeypatch.setattr(evaluation_case_runner.httpx, "post", post)
    monkeypatch.setattr(evaluation_case_runner, "create_access_token", lambda **kwargs: "token")
    monkeypatch.setattr(evaluation_case_runner, "_verify_case", lambda *args: failed)
    monkeypatch.setattr(evaluation_case_runner, "MAX_REPAIR_ATTEMPTS", 1)

    evaluation_case_runner.run_case(case.case_id)

    initial, repair = requests
    for key in ("framework", "runtime", "contracts"):
        assert initial[key] == repair[key] == evaluation_case_runner.build_case_contract(case)[key]
    assert [
        {key: route[key] for key in ("method", "path", "status_code")}
        for route in initial["contracts"]["routes"]
    ] == [
        {"method": method, "path": path, "status_code": status}
        for method, path, status in case.routes
    ]
    assert initial["framework"] == case.framework
    assert initial["runtime"] == case.runtime
    for contract in case.http_contracts:
        route = next(item for item in repair["contracts"]["routes"]
                     if (item["method"], item["path"]) == (contract.method, contract.path))
        assert route["request_body_schema"] == contract.request_body_schema
        assert route["serialization_guidance"] == contract.serialization_guidance
        if contract.response_body_schema is not None:
            assert route["response_body_schema"] == contract.response_body_schema
    assert repair["output_dir"] == tmp_path.name == repair["project_path"]
    assert repair["output_dir"] != initial["output_dir"]
    assert repair["output_dir"] != str(tmp_path)
    assert [(item["path"], item["action"]) for item in repair["change_plan"]] == [
        (path, "modify" if path == existing else "add") for path in case.required_files
    ]


def test_contract_and_requirement_follow_custom_case_data(monkeypatch):
    case = replace(
        evaluation_case_runner.get_case("python-single-spec_first"),
        framework="custom-framework",
        runtime="custom-runtime",
        routes=(("PATCH", "/inventory/{sku}", 202),),
        http_contracts=(),
        request="Update inventory.",
    )
    monkeypatch.setattr(evaluation_case_runner, "CORE_EVALUATION_CASES", (case,))

    assert evaluation_case_runner.build_case_contract(case) == {
        "framework": "custom-framework",
        "runtime": "custom-runtime",
        "contracts": {"routes": [{"method": "PATCH", "path": "/inventory/{sku}", "status_code": 202}]},
    }
    requirement = build_requirement(case.case_id)
    assert "PATCH /inventory/{sku} returning HTTP 202" in requirement
    assert "/api/v1/todos" not in requirement


@pytest.mark.parametrize("response_files", [["app/main.py"], []])
@pytest.mark.parametrize("disk_difference", [None, "extra.py", ".unexpected", "nested/.dep_graph.json", "missing"])
def test_repair_report_uses_full_disk_project(tmp_path, monkeypatch, response_files, disk_difference):
    case = evaluation_case_runner.get_case("python-small-spec_first")
    for path in (*case.required_files, ".dep_graph.json", "__pycache__/main.pyc", ".pytest_cache/README.md", "todos.db", "target/compiled.class"):
        file_path = tmp_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("fixture", encoding="utf-8")
    if disk_difference and disk_difference != "missing":
        (tmp_path / disk_difference).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / disk_difference).write_text("unexpected", encoding="utf-8")
    elif disk_difference == "missing":
        (tmp_path / case.required_files[-1]).rename(tmp_path.parent / f"{tmp_path.name}-missing.py")

    class Response:
        status_code = 200

        def json(self):
            return {"success": True, "output_dir": str(tmp_path), "files": [{"path": path} for path in case.required_files]}

    def verify(*args):
        passed = bool(verifications)
        verifications.append(True)
        return {
            "files_complete": check_required_files(tmp_path, case.required_files),
            "compile": {"passed": passed},
            "tests": {"passed": passed},
            "runtime": {"passed": passed},
            "passed": passed,
        }

    verifications = []
    monkeypatch.setattr(evaluation_case_runner.httpx, "post", lambda *args, **kwargs: Response())
    monkeypatch.setattr(evaluation_case_runner, "create_access_token", lambda **kwargs: "token")
    monkeypatch.setattr(evaluation_case_runner, "_verify_case", verify)
    monkeypatch.setattr(evaluation_case_runner, "repair_generation_failure", lambda *args: {
        "http_status": 200,
        "response": {"success": True, "files": [{"path": path} for path in response_files]},
    })

    summary = evaluation_case_runner.run_case(case.case_id)

    expected = set(case.required_files)
    if disk_difference and disk_difference != "missing":
        expected.add(disk_difference)
    elif disk_difference == "missing":
        expected.remove(case.required_files[-1])
    assert summary["files"] == response_files
    assert summary["project_files"] == sorted(expected)
    assert summary["record"]["plan_consistent"] is (disk_difference is None)
    assert summary["record"]["files_complete"] is (disk_difference != "missing")


def test_response_errors_preserve_structured_http_failure():
    result = normalize_response_errors({"code": "INTERNAL_ERROR", "message": "name resolution failed"})

    assert result == [{"code": "INTERNAL_ERROR", "message": "name resolution failed"}]


@pytest.mark.parametrize("scenario,expected_attempts,reason", [
    ("different", 2, "passed"),
    ("repeated_diagnostic", 2, "no_progress_repeated_diagnostic"),
    ("repeated_candidate", 2, "no_progress_repeated_candidate"),
    ("cycle", 3, "no_progress_repeated_diagnostic"),
    ("budget", 3, "budget_exhausted"),
    ("failed_core_good_disk", 3, "budget_exhausted"),
])
def test_repair_loop_uses_latest_candidate_and_bounded_progress(tmp_path, monkeypatch, scenario, expected_attempts, reason):
    inputs = []
    class Response:
        status_code = 200

        def json(self):
            return {"success": False, "output_dir": str(tmp_path), "errors": ["initial error"]}

    def verify(*args):
        passed = (scenario == "different" and len(inputs) >= 2) or scenario == "failed_core_good_disk"
        return {"passed": passed, **{
            stage: {"passed": passed, "stderr": "OldRuntimeError: disk baseline"}
            for stage in ("files_complete", "compile", "tests", "runtime")
        }}

    def repair(url, token, case_id, failure, output_dir):
        inputs.append(failure)
        attempt = len(inputs)
        diagnostic = 1 if scenario == "repeated_diagnostic" else attempt
        if scenario == "cycle" and attempt == 3:
            diagnostic = 1
        candidate = 1 if scenario == "repeated_candidate" else attempt
        return {"http_status": 200, "response": {
            "success": scenario == "different" and attempt == 2,
            "repair_feedback": {"candidate_fingerprint": str(candidate), "rolled_back": True,
                                "diagnostics": [{"code": "project.validation_failed", "details": {
                                    "attempts": attempt,
                                    "diagnostics": [f"NewRuntimeError{diagnostic}: candidate failed in {attempt}.12s"]}}]},
        }}

    monkeypatch.setattr(evaluation_case_runner.httpx, "post", lambda *args, **kwargs: Response())
    monkeypatch.setattr(evaluation_case_runner, "create_access_token", lambda **kwargs: "token")
    monkeypatch.setattr(evaluation_case_runner, "_verify_case", verify)
    monkeypatch.setattr(evaluation_case_runner, "repair_generation_failure", repair)
    summary = evaluation_case_runner.run_case("python-small-spec_first")
    assert len(inputs) == expected_attempts
    assert summary["repair_stop_reason"] == reason
    assert summary["success"] is (scenario == "different")
    assert "NewRuntimeError1" in str(inputs[1]["diagnostics"])
    assert "OldRuntimeError" not in str(inputs[1])
    assert inputs[1]["source"] == "core_candidate"


def test_repair_request_contains_new_runtime_evidence_after_rollback(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", str(tmp_path.parent))
    requests = []
    class Response:
        status_code = 200

        def json(self):
            return {"success": False}

    def post(*args, **kwargs):
        requests.append(kwargs["json"])
        return Response()

    monkeypatch.setattr(evaluation_case_runner.httpx, "post", post)
    failure = evaluation_case_runner._repair_failure(
        {"success": False, "repair_feedback": {"diagnostics": [{"details": {"stderr": "NewRuntimeError: app/models.py"}}]}},
        {"runtime": {"passed": False, "stderr": "OldRuntimeError"}},
    )
    evaluation_case_runner.repair_generation_failure("http://localhost", "token", "python-small-spec_first", failure, tmp_path)
    assert "NewRuntimeError" in requests[0]["requirement"]
    assert "OldRuntimeError" not in requests[0]["requirement"]


def test_expanded_case_requirement_uses_real_strategy_case():
    requirement = build_requirement("python-single-spec_first")

    assert "single project" in requirement
    assert "main.py" in requirement
    assert "Fixture contract v1" in requirement
    assert "fastapi.testclient.TestClient(app)" in requirement


def test_failure_diagnostic_preserves_output_from_each_failed_stage():
    result = _failure_diagnostic({
        "compile": {"passed": True},
        "tests": {"passed": False, "stdout": "pytest assertion failed", "stderr": ""},
        "runtime": {"passed": False, "stdout": "", "stderr": "application import failed"},
    })

    assert result["diagnostics"] == [
        "[tests]\nstdout:\npytest assertion failed",
        "[runtime]\nstderr:\napplication import failed",
    ]


def test_record_projects_real_stage_and_metrics():
    summary = {
        "case_id": "python-single-traditional",
        "strategy": "traditional",
        "file_scale": "single",
        "required_files": ["main.py"],
        "files": ["main.py"],
        "project_files": ["main.py"],
        "http_status": 200,
        "token_count": 123,
        "model_call_count": 2,
        "elapsed_seconds": 4.5,
        "first_passed": False,
        "candidate_passed": True,
        "repaired_passed": True,
        "verification": {
            "files_complete": {"passed": True},
            "compile": {"passed": True},
            "tests": {"passed": True},
            "runtime": {"passed": True},
        },
    }

    record = record_from_summary(summary)

    assert record.success is True
    assert record.first_passed is False
    assert record.candidate_passed is True
    assert record.model_call_count == 2
    assert record.token_count == 123


def test_request_scoped_llm_metrics_count_calls_and_tokens():
    token = begin_llm_call_metrics()
    _record_llm_call()
    _record_llm_call()
    _record_llm_response_metrics({"usage": {"total_tokens": 37}})
    _record_llm_stream_metrics('data: {"usage": {"total_tokens": 5}}')

    assert finish_llm_call_metrics(token) == {
        "model_call_count": 2,
        "token_count": 42,
    }


@pytest.mark.asyncio
async def test_request_scoped_llm_metrics_counts_cumulative_stream_usage_once():
    token = begin_llm_call_metrics()
    class Stream:
        def __init__(self):
            self.chunks = iter((
                'data: {"usage": {"total_tokens": 5}}',
                'data: {"usage": {"total_tokens": 12}}',
            ))

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration:
                raise StopAsyncIteration

        async def aclose(self):
            return None

    stream = _SemaphoreWrappedAsyncIterator(Stream(), None, None)
    async for _ in stream:
        pass

    assert finish_llm_call_metrics(token)["token_count"] == 12
