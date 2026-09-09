"""Run the fixed 24-case Core matrix with resumable JSON checkpoints."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent.evaluation_matrix import EvaluationRecord, FIXED_EVALUATION_MATRIX
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
    ))


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
        try:
            summary = run_case(case.case_id, url=args.url, timeout=args.timeout)
            records_by_id[case.case_id] = summary["record"]
            details[case.case_id] = summary
            failures += int(not summary["success"])
        except Exception as exc:
            elapsed = round(time.monotonic() - started, 3)
            records_by_id[case.case_id] = _failed_record(case, elapsed)
            details[case.case_id] = {
                "case_id": case.case_id,
                "strategy": case.strategy,
                "file_scale": case.file_scale,
                "success": False,
                "elapsed_seconds": elapsed,
                "errors": [{"code": type(exc).__name__, "message": str(exc)}],
            }
            failures += 1
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
