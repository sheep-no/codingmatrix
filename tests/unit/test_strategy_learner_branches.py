"""Branch coverage for app/agent/strategy_learner.py."""

import json
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.agent.strategy_learner as module
from app.agent.strategy_learner import (
    QValue,
    StrategyAction,
    StrategyLearner,
    StrategyState,
    get_strategy_learner,
)


class TestStateActionKeys:
    def test_state_key_roundtrip_with_error(self):
        state = StrategyState("medium", "python", "syntax", True)
        key = state.to_key()
        assert key == "medium:python:syntax:True"
        assert StrategyState.from_key(key) == state

    def test_state_key_roundtrip_without_error(self):
        state = StrategyState("simple", "ts", None, False)
        assert StrategyState.from_key(state.to_key()) == state

    def test_action_key_roundtrip(self):
        action = StrategyAction("fast", "minimal", 0.5, False)
        assert StrategyAction.from_key(action.to_key()) == action


class TestPersistence:
    def test_loads_existing_q_table(self, tmp_path, monkeypatch):
        target = tmp_path / "q_table.json"
        target.write_text(
            json.dumps(
                {
                    "s": {
                        "a": {"value": 1.0, "visits": 2, "last_updated": "t"}
                    }
                }
            )
        )
        monkeypatch.setattr(module, "STRATEGY_FILE", target)
        learner = StrategyLearner(data_dir=tmp_path)
        assert learner.q_table["s"]["a"].value == 1.0

    def test_load_failure_logs_error(self, tmp_path, monkeypatch):
        target = tmp_path / "bad.json"
        target.write_text("not json")
        monkeypatch.setattr(module, "STRATEGY_FILE", target)
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        StrategyLearner(data_dir=tmp_path)

        assert fake_logger.error.called

    def test_save_failure_logs_error(self, tmp_path, monkeypatch):
        target = tmp_path / "dir_for_file"
        target.mkdir()
        monkeypatch.setattr(module, "STRATEGY_FILE", target)
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        learner = StrategyLearner(data_dir=tmp_path)
        learner._save_q_table()

        assert fake_logger.error.called

    def test_save_success_roundtrip(self, tmp_path, monkeypatch):
        target = tmp_path / "q.json"
        monkeypatch.setattr(module, "STRATEGY_FILE", target)
        learner = StrategyLearner(data_dir=tmp_path)
        state = StrategyState("medium", "python", None, False)
        learner.select_action(state)
        learner.update(reward=1.0)
        assert target.exists()


class TestSelectAction:
    def _state(self):
        return StrategyState("medium", "python", None, False)

    def test_exploration(self, learner, monkeypatch):
        monkeypatch.setattr(random, "random", MagicMock(return_value=0.0))
        action = learner.select_action(self._state())
        assert action.model_selection in learner.MODEL_SELECTION_STRATEGIES

    def test_exploitation_new_state(self, learner, monkeypatch):
        monkeypatch.setattr(random, "random", MagicMock(return_value=0.99))
        monkeypatch.setattr(random, "choice", MagicMock(side_effect=lambda seq: seq[0]))
        action = learner.select_action(self._state())
        assert action is not None

    def test_exploitation_best_known(self, learner, monkeypatch):
        monkeypatch.setattr(random, "random", MagicMock(return_value=0.99))
        state = self._state()
        state_key = state.to_key()
        preferred = StrategyAction("fast", "standard", 0.3, True)
        other = StrategyAction("balanced", "standard", 0.3, True)
        learner.q_table[state_key][preferred.to_key()] = QValue(value=5.0, visits=1)
        learner.q_table[state_key][other.to_key()] = QValue(value=1.0, visits=1)

        action = learner.select_action(state, [preferred, other])

        assert action == preferred

    def test_exploitation_no_known_action_falls_back(self, learner, monkeypatch):
        monkeypatch.setattr(random, "random", MagicMock(return_value=0.99))
        monkeypatch.setattr(random, "choice", MagicMock(side_effect=lambda seq: seq[0]))
        state = self._state()
        known = StrategyAction("fast", "standard", 0.3, True)
        learner.q_table[state.to_key()][known.to_key()] = QValue(value=1.0)

        unknown = [StrategyAction("balanced", "minimal", 0.9, False)]
        action = learner.select_action(state, unknown)
        assert action == unknown[0]


class TestUpdate:
    def _state(self):
        return StrategyState("medium", "python", None, False)

    def test_update_without_state_warns(self, learner, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)
        learner.update(1.0)
        assert fake_logger.warning.called

    def test_update_terminal_state(self, learner):
        state = self._state()
        learner.select_action(state)
        learner.update(reward=1.0)
        stats = learner.get_learning_stats()
        assert stats["total_visits"] == 1

    def test_update_with_next_state_known(self, learner):
        state = self._state()
        next_state = StrategyState("large", "ts", None, False)
        learner.q_table[next_state.to_key()]["a"] = QValue(value=2.0)
        learner.select_action(state)
        learner.update(reward=0.5, next_state=next_state)
        assert any(v.visits == 1 for v in learner.q_table[state.to_key()].values())

    def test_update_with_next_state_unknown(self, learner):
        state = self._state()
        next_state = StrategyState("large", "ts", None, False)
        learner.select_action(state)
        learner.update(reward=0.5, next_state=next_state)
        assert any(v.visits == 1 for v in learner.q_table[state.to_key()].values())

    def test_update_with_empty_next_state_actions(self, learner):
        state = self._state()
        next_state = StrategyState("large", "ts", None, False)
        learner.q_table[next_state.to_key()] = {}
        learner.select_action(state)
        learner.update(reward=0.5, next_state=next_state)
        assert any(v.visits == 1 for v in learner.q_table[state.to_key()].values())


class TestQueries:
    def test_best_action_missing_state(self, learner):
        assert learner.get_best_action(StrategyState("x", "y", None, False)) is None

    def test_best_action_empty_actions(self, learner):
        state = StrategyState("x", "y", None, False)
        learner.q_table[state.to_key()] = {}
        assert learner.get_best_action(state) is None

    def test_best_action_returns_highest(self, learner):
        state = StrategyState("x", "y", None, False)
        high = StrategyAction("fast", "standard", 0.3, True)
        low = StrategyAction("balanced", "standard", 0.3, True)
        learner.q_table[state.to_key()][high.to_key()] = QValue(value=9.0)
        learner.q_table[state.to_key()][low.to_key()] = QValue(value=1.0)
        assert learner.get_best_action(state) == high

    def test_recommendation_default(self, learner):
        result = learner.get_strategy_recommendation("medium", "python")
        assert result["is_learned"] is False
        assert result["model_selection"] == "balanced"

    def test_recommendation_learned(self, learner):
        state = StrategyState("medium", "python", "syntax", True)
        action = StrategyAction("fast", "minimal", 0.3, False)
        learner.q_table[state.to_key()][action.to_key()] = QValue(value=2.5, visits=6)
        result = learner.get_strategy_recommendation("medium", "python", "syntax", True)
        assert result["is_learned"] is True
        assert result["q_value"] == 2.5
        assert result["visits"] == 6

    def test_learning_stats_empty(self, learner):
        stats = learner.get_learning_stats()
        assert stats["avg_q_value"] == 0
        assert stats["top_strategies"] == []

    def test_learning_stats_with_visits(self, learner):
        state = StrategyState("medium", "python", None, False)
        action = StrategyAction("fast", "standard", 0.3, True)
        learner.q_table[state.to_key()][action.to_key()] = QValue(value=3.0, visits=5)
        other = StrategyAction("balanced", "standard", 0.3, True)
        learner.q_table[state.to_key()][other.to_key()] = QValue(value=1.0, visits=1)

        stats = learner.get_learning_stats()

        assert stats["total_visits"] == 6
        assert len(stats["top_strategies"]) == 1

    def test_clear_q_table_removes_file(self, learner, monkeypatch):
        target = learner.data_dir / "q.json"
        target.write_text("{}")
        monkeypatch.setattr(module, "STRATEGY_FILE", target)
        learner.clear_q_table()
        assert learner.q_table == {}
        assert not target.exists()

    def test_clear_q_table_without_file(self, learner, monkeypatch):
        monkeypatch.setattr(module, "STRATEGY_FILE", learner.data_dir / "absent.json")
        learner.clear_q_table()


@pytest.fixture
def learner(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "STRATEGY_FILE", tmp_path / "q_table.json")
    return StrategyLearner(data_dir=tmp_path)


@pytest.mark.asyncio
async def test_get_strategy_learner_singleton(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "_strategy_learner", None)
    monkeypatch.setattr(module, "STRATEGY_FILE", tmp_path / "q.json")
    first = await get_strategy_learner()
    second = await get_strategy_learner()
    assert first is second


@pytest.mark.asyncio
async def test_get_strategy_learner_double_check_race(monkeypatch):
    existing = StrategyLearner(data_dir=Path("/tmp/opencode/sl_race"))

    class _Lock:
        async def __aenter__(self):
            monkeypatch.setattr(module, "_strategy_learner", existing)
            return self

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(module, "_strategy_learner", None)
    monkeypatch.setattr(module, "_learner_lock", _Lock())

    assert await get_strategy_learner() is existing
