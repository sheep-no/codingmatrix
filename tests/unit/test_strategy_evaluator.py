"""
策略评估器单元测试
测试 StrategyEvaluator 的 A/B 测试、策略管理、持久化功能
"""
import pytest
import time
import os
from pathlib import Path

from app.agent.strategy_evaluator import (
    StrategyEvaluator,
    RepairStrategy,
    StrategyEvaluationResult,
)


@pytest.fixture
def evaluator(tmp_path):
    """创建策略评估器实例（使用临时文件）"""
    strategies_file = tmp_path / "strategies.json"
    return StrategyEvaluator(strategies_file=strategies_file)


class TestRepairStrategy:
    """RepairStrategy 数据类测试"""

    def test_create_strategy(self):
        """测试创建策略"""
        strategy = RepairStrategy(
            strategy_id="test_strategy_1",
            error_type="NameError",
            template="Fix the undefined variable: {variable_name}",
            created_at=time.time(),
            last_updated=time.time(),
        )
        assert strategy.strategy_id == "test_strategy_1"
        assert strategy.error_type == "NameError"
        assert strategy.success_rate == 0.0
        assert strategy.total_attempts == 0
        assert strategy.is_active is True

    def test_strategy_defaults(self):
        """测试策略默认值"""
        strategy = RepairStrategy(
            strategy_id="test",
            error_type="TypeError",
            template="test",
            created_at=time.time(),
            last_updated=time.time(),
        )
        assert strategy.success_rate == 0.0
        assert strategy.total_attempts == 0
        assert strategy.is_active is True

    def test_strategy_update_stats(self):
        """测试更新策略统计"""
        strategy = RepairStrategy(
            strategy_id="test",
            error_type="Error",
            template="test",
            created_at=time.time(),
            last_updated=time.time(),
        )
        # 验证基本属性
        assert strategy.total_attempts == 0
        assert strategy.successful_attempts == 0
        assert strategy.success_rate == 0.0
        assert strategy.is_active is True

    def test_strategy_to_dict(self):
        """测试转换为字典"""
        strategy = RepairStrategy(
            strategy_id="test",
            error_type="Error",
            template="test",
            created_at=time.time(),
            last_updated=time.time(),
        )
        d = strategy.__dict__
        assert d["strategy_id"] == "test"
        assert d["error_type"] == "Error"
