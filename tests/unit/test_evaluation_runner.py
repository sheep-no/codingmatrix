import json
import subprocess

import pytest

from app.agent.evaluation_runner import build_report_from_file, load_records, report_payload
from tests.manual.run_core_evaluation_case import (
    check_required_files,
    normalize_response_errors,
    run_compile_check,
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
    assert "python-single-llm" in payload["missing_case_ids"]
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


def test_response_errors_preserve_structured_http_failure():
    result = normalize_response_errors({"code": "INTERNAL_ERROR", "message": "name resolution failed"})

    assert result == [{"code": "INTERNAL_ERROR", "message": "name resolution failed"}]
