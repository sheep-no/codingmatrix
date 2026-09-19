"""默认引擎契约：legacy 是唯一受支持默认，core 未通过评估矩阵前不得成为默认。

固定 24 例矩阵（``tests/manual/run_core_evaluation_matrix.py``）当前的
engineering/quality 通过率为 0/24、``target_met=false``，因此 core 只能
opt-in（显式传 ``engine="core"`` 或设置 ``AGENT_ORCHESTRATION_ENGINE=core``），
不能占据默认路径。若要把 ``DEFAULT_ENGINE`` 改成 core，必须同时提供一份
通过的矩阵证据 ``evaluation_report.json``，否则本文件会失败。
"""

import json
from pathlib import Path

import pytest

from app.agent.orchestration.routing import (
    CORE_ENGINE,
    DEFAULT_ENGINE,
    LEGACY_ENGINE,
    engine_metadata,
    select_engine,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_EVIDENCE = REPO_ROOT / "evaluation_report.json"
MATRIX_RUNNER = "tests/manual/run_core_evaluation_matrix.py"


@pytest.fixture(autouse=True)
def _isolate_engine_env(monkeypatch):
    """默认引擎断言不能被外部环境变量污染。"""
    monkeypatch.delenv("AGENT_ORCHESTRATION_ENGINE", raising=False)


def test_default_engine_is_legacy():
    assert DEFAULT_ENGINE == LEGACY_ENGINE
    assert select_engine() == LEGACY_ENGINE


def test_default_engine_route_is_supported():
    assert engine_metadata(DEFAULT_ENGINE)["engine_route"] == "stable", (
        "默认引擎必须处于受支持路由；把实验性引擎设为默认前需先通过评估矩阵。"
    )


def test_core_needs_a_passing_matrix_to_become_default():
    if DEFAULT_ENGINE != CORE_ENGINE:
        # 默认仍是 legacy，门禁无额外要求。
        return
    assert MATRIX_EVIDENCE.exists(), (
        f"core 被设为默认引擎，但缺少评估矩阵证据 {MATRIX_EVIDENCE.name}。"
        f"请先运行 {MATRIX_RUNNER} 生成报告。"
    )
    report = json.loads(MATRIX_EVIDENCE.read_text(encoding="utf-8"))
    assert report.get("matrix_complete") is True, (
        "评估矩阵未跑满，无法作为把 core 设为默认的依据。"
    )
    assert report.get("target_met") is True, (
        "core 尚未通过评估矩阵（target_met=false），不得成为默认引擎。"
    )


def test_explicit_core_opt_in_is_still_allowed(monkeypatch):
    """门禁约束默认值，不禁止显式选择 core。"""
    monkeypatch.setenv("AGENT_ORCHESTRATION_ENGINE", CORE_ENGINE)
    assert select_engine() == CORE_ENGINE
    assert select_engine(CORE_ENGINE) == CORE_ENGINE
