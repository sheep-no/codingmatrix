"""evaluation_runner CLI 主流程补测。"""

import json

import pytest

from app.agent import evaluation_runner as runner


def _record():
    return {
        "case_id": "python-fastapi-crud",
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


def test_cli_prints_report_to_stdout(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "records.json"
    input_path.write_text(json.dumps([_record()]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["runner", str(input_path)])

    assert runner.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["successful"] == 1
    assert payload["matrix_complete"] is False


def test_cli_writes_report_to_output_file(tmp_path, monkeypatch):
    input_path = tmp_path / "records.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(json.dumps([_record()]), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["runner", str(input_path), "--output", str(output_path)]
    )

    assert runner.main() == 0

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["summary"]["successful"] == 1
    assert output_path.read_text(encoding="utf-8").endswith("\n")


def test_cli_propagates_invalid_input(tmp_path, monkeypatch):
    input_path = tmp_path / "records.json"
    input_path.write_text(json.dumps({"records": []}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["runner", str(input_path)])

    with pytest.raises(ValueError, match="JSON array"):
        runner.main()
