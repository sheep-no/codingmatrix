"""StrategyEvaluator 加载、A/B 选择、评估记录与策略提升测试。"""

import json
import time
from pathlib import Path

import pytest

import app.agent.strategy_evaluator as se
from app.agent.strategy_evaluator import (
    RepairStrategy,
    StrategyEvaluationResult,
    StrategyEvaluator,
)


def _strategy(strategy_id, error_type="NameError", success_rate=0.5, active=True, **kwargs):
    now = time.time()
    data = dict(
        strategy_id=strategy_id,
        error_type=error_type,
        template=f"tpl-{strategy_id}",
        created_at=now,
        last_updated=now,
        success_rate=success_rate,
        is_active=active,
    )
    data.update(kwargs)
    return RepairStrategy(**data)


def _result(strategy_id, success=True, quality=0.8, fix_time=10.0, ts=None):
    return StrategyEvaluationResult(
        strategy_id=strategy_id,
        success=success,
        fix_time=fix_time,
        code_quality_score=quality,
        timestamp=time.time() if ts is None else ts,
    )


@pytest.fixture
def evaluator(tmp_path):
    return StrategyEvaluator(strategies_file=tmp_path / "strategies.json")


class TestLoad:
    def test_loads_existing_strategies(self, tmp_path):
        path = tmp_path / "strategies.json"
        path.write_text(
            json.dumps(
                {
                    "NameError": [
                        {
                            "strategy_id": "s1",
                            "error_type": "NameError",
                            "template": "tpl",
                            "created_at": 1.0,
                            "last_updated": 2.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        instance = StrategyEvaluator(strategies_file=path)

        assert instance.strategies["NameError"][0].strategy_id == "s1"

    def test_load_failure_logs_warning(self, tmp_path, monkeypatch):
        warnings = []
        monkeypatch.setattr(se.logger, "warning", lambda fmt, err: warnings.append((fmt, err)))
        path = tmp_path / "strategies.json"
        path.write_text("{ not json", encoding="utf-8")

        instance = StrategyEvaluator(strategies_file=path)

        assert instance.strategies == {}
        assert warnings == [("加载修复策略失败: %s", warnings[0][1])]


class TestSave:
    def test_save_closes_fd_when_fdopen_fails(self, tmp_path, monkeypatch):
        evaluator = StrategyEvaluator(strategies_file=tmp_path / "strategies.json")
        closed = []
        monkeypatch.setattr(se.os, "fdopen", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
        monkeypatch.setattr(se.os, "close", lambda fd: closed.append(fd))

        evaluator._save_strategies()

        assert len(closed) == 1

    def test_save_removes_temp_when_replace_fails(self, tmp_path, monkeypatch):
        evaluator = StrategyEvaluator(strategies_file=tmp_path / "strategies.json")
        monkeypatch.setattr(
            se.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
        )

        evaluator._save_strategies()

        assert list(tmp_path.glob("*.tmp")) == []


class TestGetBestStrategy:
    def test_unknown_error_type(self, evaluator):
        assert evaluator.get_best_strategy("Missing") is None

    def test_all_inactive(self, evaluator):
        evaluator.strategies["E"] = [_strategy("a", error_type="E", active=False)]

        assert evaluator.get_best_strategy("E") is None

    def test_single_active_returns_it(self, evaluator):
        only = _strategy("a", error_type="E")
        evaluator.strategies["E"] = [only, _strategy("b", error_type="E", active=False)]

        assert evaluator.get_best_strategy("E") is only

    def test_exploit_returns_highest_rate(self, evaluator, monkeypatch):
        best = _strategy("best", error_type="E", success_rate=0.9)
        other = _strategy("other", error_type="E", success_rate=0.4)
        evaluator.strategies["E"] = [other, best]
        monkeypatch.setattr(se.random, "random", lambda: 0.1)

        assert evaluator.get_best_strategy("E") is best

    def test_explore_picks_from_rest(self, evaluator, monkeypatch):
        best = _strategy("best", error_type="E", success_rate=0.9)
        other = _strategy("other", error_type="E", success_rate=0.4)
        evaluator.strategies["E"] = [other, best]
        monkeypatch.setattr(se.random, "random", lambda: 0.95)
        monkeypatch.setattr(se.random, "choice", lambda items: items[0])

        assert evaluator.get_best_strategy("E") is other


class TestCreateStrategy:
    def test_new_main_strategy(self, evaluator):
        strategy_id = evaluator.create_or_update_strategy("NameError", "fix it")

        strategy = evaluator.strategies["NameError"][0]
        assert strategy.strategy_id == strategy_id
        assert strategy.success_rate == 0.5
        assert strategy.version == 1

    def test_new_variant_starts_exploratory(self, evaluator):
        evaluator.create_or_update_strategy("NameError", "first")
        evaluator.create_or_update_strategy("NameError", "variant", is_new_variant=True)

        variant = evaluator.strategies["NameError"][1]
        assert variant.success_rate == 0.1
        assert variant.version == 2


class TestRecordEvaluation:
    def test_first_result_initializes_averages(self, evaluator, monkeypatch):
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: None)
        evaluator.strategies["E"] = [_strategy("s", error_type="E")]

        evaluator.record_evaluation_result(_result("s", success=True, quality=0.7, fix_time=4.0))

        strategy = evaluator.strategies["E"][0]
        assert strategy.total_attempts == 1
        assert strategy.successful_attempts == 1
        assert strategy.success_rate == 1.0
        assert strategy.avg_fix_time == 4.0
        assert strategy.code_quality_score == 0.7

    def test_subsequent_results_use_ema(self, evaluator, monkeypatch):
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: None)
        monkeypatch.setattr(evaluator, "_check_strategy_promotion", lambda: None)
        evaluator.strategies["E"] = [
            _strategy(
                "s",
                error_type="E",
                total_attempts=1,
                successful_attempts=1,
                success_rate=1.0,
                avg_fix_time=10.0,
                code_quality_score=0.9,
            )
        ]

        evaluator.record_evaluation_result(_result("s", success=False, quality=0.5, fix_time=20.0))

        strategy = evaluator.strategies["E"][0]
        assert strategy.total_attempts == 2
        assert strategy.successful_attempts == 1
        assert strategy.success_rate == 0.5
        assert strategy.avg_fix_time == pytest.approx(11.0)
        assert strategy.code_quality_score == pytest.approx(0.86)

    def test_unknown_strategy_is_recorded_only(self, evaluator, monkeypatch):
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: None)
        monkeypatch.setattr(evaluator, "_check_strategy_promotion", lambda: None)

        evaluator.record_evaluation_result(_result("ghost"))

        assert len(evaluator.evaluation_history) == 1
        assert evaluator.strategies == {}

    def test_scans_remaining_groups_after_match(self, evaluator, monkeypatch):
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: None)
        monkeypatch.setattr(evaluator, "_check_strategy_promotion", lambda: None)
        evaluator.strategies["E"] = [
            _strategy("first", error_type="E"),
            _strategy("target", error_type="E"),
        ]
        evaluator.strategies["F"] = [_strategy("other", error_type="F")]

        evaluator.record_evaluation_result(_result("target"))

        assert evaluator.strategies["E"][0].total_attempts == 0
        assert evaluator.strategies["E"][1].total_attempts == 1
        assert evaluator.strategies["F"][0].total_attempts == 0


class TestPromotion:
    def _setup_pair(self, evaluator, main_rate=0.9, candidate_rate=0.4):
        main = _strategy("main", error_type="E", success_rate=main_rate)
        candidate = _strategy("cand", error_type="E", success_rate=candidate_rate)
        evaluator.strategies["E"] = [main, candidate]
        return main, candidate

    def test_single_strategy_is_skipped(self, evaluator):
        evaluator.strategies["E"] = [_strategy("only", error_type="E")]

        evaluator._check_strategy_promotion()

        assert evaluator.strategies["E"][0].is_active is True

    def test_fewer_than_two_active_is_skipped(self, evaluator):
        evaluator.strategies["E"] = [
            _strategy("a", error_type="E"),
            _strategy("b", error_type="E", active=False),
        ]

        evaluator._check_strategy_promotion()

        assert evaluator.strategies["E"][0].is_active is True

    def test_insufficient_history_is_skipped(self, evaluator):
        self._setup_pair(evaluator)
        evaluator.evaluation_history = [_result("cand"), _result("main")]

        evaluator._check_strategy_promotion()

        assert evaluator.strategies["E"][0].is_active is True

    def test_unrelated_strategy_results_are_filtered(self, evaluator):
        self._setup_pair(evaluator)
        evaluator.evaluation_history = [_result("other") for _ in range(8)]

        evaluator._check_strategy_promotion()

        assert evaluator.strategies["E"][0].is_active is True

    def test_no_consecutive_win_keeps_main(self, evaluator):
        self._setup_pair(evaluator)
        history = []
        for i in range(6):
            ts = float(i)
            if i % 2:
                history.append(_result("main", quality=0.9, ts=ts))
            else:
                history.append(_result("cand", quality=0.1, ts=ts))

        evaluator.evaluation_history = history
        evaluator._check_strategy_promotion()

        assert evaluator.strategies["E"][0].is_active is True

    def test_consecutive_win_promotes_candidate(self, evaluator, monkeypatch):
        main, candidate = self._setup_pair(evaluator)
        saved = []
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: saved.append(1))
        history = []
        for i in range(6):
            ts = float(i)
            if i % 2:
                history.append(_result("main", quality=0.1, ts=ts))
            else:
                history.append(_result("cand", quality=0.9, ts=ts))

        evaluator.evaluation_history = history
        evaluator._check_strategy_promotion()

        assert main.is_active is False
        assert candidate.version == 2
        assert saved == [1]

    def test_reset_on_candidate_loss(self, evaluator, monkeypatch):
        main, candidate = self._setup_pair(evaluator)
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: None)
        history = [
            _result("cand", quality=0.9, ts=0),
            _result("main", quality=0.1, ts=1),
            _result("cand", quality=0.9, ts=2),
            _result("main", quality=0.1, ts=3),
            _result("cand", quality=0.1, ts=4),
            _result("main", quality=0.9, ts=5),
            _result("cand", quality=0.9, ts=6),
            _result("main", quality=0.1, ts=7),
        ]

        evaluator.evaluation_history = history
        evaluator._check_strategy_promotion()

        assert main.is_active is True
        assert candidate.version == 1


class TestHelpers:
    def test_template_returns_selected(self, evaluator, monkeypatch):
        strategy = _strategy("s", error_type="E")
        monkeypatch.setattr(evaluator, "get_best_strategy", lambda _: strategy)

        assert evaluator.get_strategy_template("E") == ("tpl-s", "s")

    def test_template_missing(self, evaluator):
        assert evaluator.get_strategy_template("none") == (None, None)

    def test_disable_existing(self, evaluator, monkeypatch):
        saved = []
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: saved.append(1))
        evaluator.strategies["E"] = [_strategy("s", error_type="E")]

        evaluator.disable_strategy("s")

        assert evaluator.strategies["E"][0].is_active is False
        assert saved == [1]

    def test_disable_missing_is_noop(self, evaluator, monkeypatch):
        saved = []
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: saved.append(1))

        evaluator.disable_strategy("none")

        assert saved == []

    def test_disable_walks_multiple_groups_and_strategies(self, evaluator, monkeypatch):
        monkeypatch.setattr(evaluator, "_save_strategies", lambda: None)
        evaluator.strategies["E"] = [_strategy("skip", error_type="E")]
        evaluator.strategies["F"] = [
            _strategy("other", error_type="F"),
            _strategy("target", error_type="F"),
        ]

        evaluator.disable_strategy("target")

        assert evaluator.strategies["E"][0].is_active is True
        assert evaluator.strategies["F"][0].is_active is True
        assert evaluator.strategies["F"][1].is_active is False

    def test_stats_for_one_error_type(self, evaluator):
        evaluator.strategies["E"] = [_strategy("s", error_type="E", total_attempts=3)]

        stats = evaluator.get_strategy_stats("E")

        assert stats["E"][0]["strategy_id"] == "s"
        assert stats["E"][0]["total_attempts"] == 3

    def test_stats_for_unknown_error_type(self, evaluator):
        assert evaluator.get_strategy_stats("none") == {"none": []}

    def test_stats_for_all_error_types(self, evaluator):
        evaluator.strategies["E"] = [_strategy("s", error_type="E")]
        evaluator.strategies["T"] = [_strategy("t", error_type="T")]

        stats = evaluator.get_strategy_stats()

        assert set(stats) == {"E", "T"}
