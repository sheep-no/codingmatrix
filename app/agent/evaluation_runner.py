"""Command-line report builder for the fixed multilingual evaluation matrix."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping, Any

from .evaluation_matrix import EvaluationRecord, EvaluationReport, FIXED_EVALUATION_MATRIX, build_report


def load_records(payload: Iterable[Mapping[str, Any]]) -> list[EvaluationRecord]:
    """Validate JSON-compatible records before building an evaluation report."""
    return [EvaluationRecord(**dict(record)) for record in payload]


def report_payload(report: EvaluationReport) -> dict[str, Any]:
    """Convert the immutable report model into stable JSON-compatible data."""
    return asdict(report)


def build_report_from_file(input_path: Path, *, cases=FIXED_EVALUATION_MATRIX) -> EvaluationReport:
    """Read an evaluation record list and calculate the fixed-matrix report."""
    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("evaluation input must be a JSON array")
    return build_report(load_records(payload), cases=cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON array containing evaluation records")
    parser.add_argument("--output", type=Path, help="Optional path for the JSON report")
    args = parser.parse_args()

    report = report_payload(build_report_from_file(args.input))
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
