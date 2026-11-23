"""Run the fixed 24-case Core matrix with resumable JSON checkpoints."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent.evaluation_matrix import FIXED_EVALUATION_MATRIX, EvaluationRecord
from tests.manual.run_core_evaluation_case import DEFAULT_URL, run_case


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _failed_record(case, elapsed: float) -> dict[str, Any]:
    """Transport/runner exceptions are infrastructure failures, not quality results."""
    return asdict(EvaluationRecord(
        case_id=case.case_id,
        plan_consistent=False,
        interfaces_consistent=False,
        dependency_closure=False,
        files_complete=False,
        compile_passed=False,
        tests_passed=False,
        startup_passed=False,
        persistence_passed=False,
        token_count=0,
        elapsed_seconds=elapsed,
        model_call_count=0,
        strategy=case.strategy,
        file_scale=case.file_scale,
        first_passed=False,
        candidate_passed=False,
        repaired_passed=False,
        evaluation_status="evaluation_infrastructure_failure",
    ))


def _would_overwrite_completed(existing: Any, new: dict[str, Any]) -> bool:
    """A failed rerun must not replace real evidence with an infrastructure failure."""
    return (
        isinstance(existing, dict)
        and existing.get("evaluation_status") == "completed"
        and new.get("evaluation_status") == "evaluation_infrastructure_failure"
    )


def _would_overwrite_successful_detail(existing: Any, new: dict[str, Any]) -> bool:
    """Keep the detail payload of a successful run when a rerun fails."""
    return (
        isinstance(existing, dict)
        and existing.get("success") is True
        and new.get("success") is not True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--records", type=Path, default=Path("evaluation_records_24.json"))
    parser.add_argument("--details", type=Path, default=Path("evaluation_details_24.json"))
    parser.add_argument("--language", choices=("python", "typescript", "go", "java"))
    parser.add_argument("--scale", choices=("single", "small", "modular"))
    parser.add_argument("--strategy", choices=("traditional", "spec_first"))
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--rerun", action="store_true", help="Run selected cases already present in records")
    args = parser.parse_args()

    selected = [
        case for case in FIXED_EVALUATION_MATRIX
        if (args.language is None or case.language == args.language)
        and (args.scale is None or case.file_scale == args.scale)
        and (args.strategy is None or case.strategy == args.strategy)
        and (not args.case_id or case.case_id in args.case_id)
    ]
    records_by_id = {
        item["case_id"]: item for item in _read_json(args.records, [])
        if isinstance(item, dict) and item.get("case_id")
    }
    details = _read_json(args.details, {})
    failures = 0

    for case in selected:
        if case.case_id in records_by_id and not args.rerun:
            continue
        started = time.monotonic()
        previous_detail = details.get(case.case_id)
        try:
            summary = run_case(case.case_id, url=args.url, timeout=args.timeout)
            failures += int(not summary["success"])
            record = summary["record"]
            detail = summary
        except Exception as exc:
            elapsed = round(time.monotonic() - started, 3)
            record = _failed_record(case, elapsed)
            detail = {
                "case_id": case.case_id,
                "strategy": case.strategy,
                "file_scale": case.file_scale,
                "success": False,
                "elapsed_seconds": elapsed,
                "errors": [{"code": type(exc).__name__, "message": str(exc)}],
            }
            failures += 1
        # 失败重跑不得覆盖既有成功证据。
        if not _would_overwrite_completed(records_by_id.get(case.case_id), record):
            records_by_id[case.case_id] = record
        if not _would_overwrite_successful_detail(previous_detail, detail):
            details[case.case_id] = detail
        _write_json(args.records, [records_by_id[key] for key in sorted(records_by_id)])
        _write_json(args.details, details)

    print(json.dumps({
        "selected": len(selected),
        "recorded": len(records_by_id),
        "failed_in_this_run": failures,
        "records": str(args.records),
        "details": str(args.details),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
