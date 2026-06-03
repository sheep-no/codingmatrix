"""
策略评估器 - 修复策略的 A/B 测试和自动优化框架
"""
import json
import time
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path



@dataclass
class RepairStrategy:
    """修复策略定义"""
    strategy_id: str
    error_type: str
    template: str  # 修复提示词模板
    created_at: float
    last_updated: float
    success_rate: float = 0.0
    total_attempts: int = 0
    successful_attempts: int = 0
    avg_fix_time: float = 0.0
    code_quality_score: float = 0.0  # 通过后续审查轮次的通过率
    is_active: bool = True
    version: int = 1


@dataclass
class StrategyEvaluationResult:
    """策略评估结果"""
    strategy_id: str
    success: bool
    fix_time: float
    code_quality_score: float
    timestamp: float


class StrategyEvaluator:
    """
    策略评估器 - 实现修复策略的 A/B 测试和自动优化

    核心功能：
    1. 对每种错误类型维护多个修复策略（exploit/explore）
    2. 记录修复成功率、耗时、代码质量等指标
    3. 80/20 流量分配：80% 走已验证策略，20% 随机探索
    4. 自动策略替换：当探索策略连续 N 次表现更优时替换主策略
    """

    def __init__(self, strategies_file: Path = None):
        self.strategies_file = strategies_file or Path("repair_strategies.json")
        self.strategies: Dict[str, List[RepairStrategy]] = {}
        self.evaluation_history: List[StrategyEvaluationResult] = []
        self.N_CONSECUTIVE_BETTER = 3  # 连续 N 次表现更好就替换

        self._load_strategies()

    def _load_strategies(self):
        """从文件加载策略"""
        if self.strategies_file.exists():
            try:
                with open(self.strategies_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for error_type, strategies_data in data.items():
                        self.strategies[error_type] = [
                            RepairStrategy(**strategy_data)
                            for strategy_data in strategies_data
                        ]
            except Exception as e:
                print(f"加载修复策略失败: {e}")

    def _save_strategies(self):
        """保存策略到文件"""
        try:
            strategies_dict = {
                error_type: [asdict(strategy) for strategy in strategies]
                for error_type, strategies in self.strategies.items()
            }
            with open(self.strategies_file, 'w', encoding='utf-8') as f:
                json.dump(strategies_dict, f, indent=2)
        except Exception as e:
            print(f"保存修复策略失败: {e}")

    def get_best_strategy(self, error_type: str) -> Optional[RepairStrategy]:
        """
        获取最佳修复策略（带 A/B 测试逻辑）

        Args:
            error_type: 错误类型

        Returns:
            选中的修复策略
        """
        if error_type not in self.strategies:
            return None

        active_strategies = [s for s in self.strategies[error_type] if s.is_active]
        if not active_strategies:
            return None

        # 80% 走已验证策略（最高成功率），20% 随机探索
        if len(active_strategies) == 1:
            return active_strategies[0]

        # 按成功率排序
        sorted_strategies = sorted(
            active_strategies,
            key=lambda s: s.success_rate,
            reverse=True
        )

        # 80/20 流量分配
        if random.random() < 0.8:
            return sorted_strategies[0]  # exploit
        else:
            return random.choice(sorted_strategies[1:])  # explore

    def create_or_update_strategy(
        self,
        error_type: str,
        template: str,
        is_new_variant: bool = False
    ) -> str:
        """
        创建或更新修复策略

        Args:
            error_type: 错误类型
            template: 修复提示词模板
            is_new_variant: 是否为新变体（用于探索）

        Returns:
            策略ID
        """
        if error_type not in self.strategies:
            self.strategies[error_type] = []

        current_time = time.time()
        strategy_id = f"{error_type}_{int(current_time)}"

        new_strategy = RepairStrategy(
            strategy_id=strategy_id,
            error_type=error_type,
            template=template,
            created_at=current_time,
            last_updated=current_time,
            version=len([s for s in self.strategies[error_type] if s.error_type == error_type]) + 1
        )

        if is_new_variant:
            # 新变体，初始成功率设为较低值以鼓励探索
            new_strategy.success_rate = 0.1
        else:
            # 主策略，初始成功率设为中等值
            new_strategy.success_rate = 0.5

        self.strategies[error_type].append(new_strategy)
        self._save_strategies()

        return strategy_id

    def record_evaluation_result(self, result: StrategyEvaluationResult):
        """
        记录策略评估结果

        Args:
            result: 评估结果
        """
        self.evaluation_history.append(result)

        # 更新策略统计信息
        for error_type, strategies in self.strategies.items():
            for strategy in strategies:
                if strategy.strategy_id == result.strategy_id:
                    strategy.total_attempts += 1
                    if result.success:
                        strategy.successful_attempts += 1

                    strategy.success_rate = (
                        strategy.successful_attempts / strategy.total_attempts
                    )

                    # 更新平均修复时间
                    if strategy.avg_fix_time == 0:
                        strategy.avg_fix_time = result.fix_time
                    else:
                        strategy.avg_fix_time = (
                            strategy.avg_fix_time * 0.9 + result.fix_time * 0.1
                        )

                    # 更新代码质量分数
                    if strategy.code_quality_score == 0:
                        strategy.code_quality_score = result.code_quality_score
                    else:
                        strategy.code_quality_score = (
                            strategy.code_quality_score * 0.9 + result.code_quality_score * 0.1
                        )

                    strategy.last_updated = time.time()
                    break

        self._save_strategies()
        self._check_strategy_promotion()

    def _check_strategy_promotion(self):
        """
        检查是否需要提升探索策略为主策略

        如果某个探索策略连续 N 次表现优于当前主策略，则提升为主策略
        """
        for error_type, strategies in self.strategies.items():
            if len(strategies) < 2:
                continue

            # 找到当前主策略（最高成功率）
            active_strategies = [s for s in strategies if s.is_active]
            if len(active_strategies) < 2:
                continue

            sorted_strategies = sorted(
                active_strategies,
                key=lambda s: s.success_rate,
                reverse=True
            )
            current_main = sorted_strategies[0]
            candidates = sorted_strategies[1:]

            # 检查每个候选策略是否连续表现更好
            for candidate in candidates:
                recent_evaluations = [
                    r for r in self.evaluation_history[-10:]  # 最近10次评估
                    if r.strategy_id in [current_main.strategy_id, candidate.strategy_id]
                ]

                if len(recent_evaluations) < self.N_CONSECUTIVE_BETTER * 2:
                    continue

                # 按时间排序
                recent_evaluations.sort(key=lambda x: x.timestamp)

                # 检查是否连续 N 次候选策略表现更好
                consecutive_better = 0
                for i in range(len(recent_evaluations) - 1):
                    if (recent_evaluations[i].strategy_id == candidate.strategy_id and
                        recent_evaluations[i+1].strategy_id == current_main.strategy_id):

                        candidate_score = (
                            recent_evaluations[i].success * 1.0 +
                            recent_evaluations[i].code_quality_score
                        )
                        main_score = (
                            recent_evaluations[i+1].success * 1.0 +
                            recent_evaluations[i+1].code_quality_score
                        )

                        if candidate_score > main_score:
                            consecutive_better += 1
                        else:
                            consecutive_better = 0

                        if consecutive_better >= self.N_CONSECUTIVE_BETTER:
                            # 提升候选策略为主策略
                            print(f"策略提升: {candidate.strategy_id} 替换 {current_main.strategy_id} 作为 {error_type} 的主策略")
                            current_main.is_active = False
                            candidate.version += 1
                            self._save_strategies()
                            break

    def get_strategy_template(self, error_type: str) -> Tuple[Optional[str], Optional[str]]:
        """
        获取修复策略模板

        Returns:
            (模板内容, 策略ID)
        """
        strategy = self.get_best_strategy(error_type)
        if strategy:
            return strategy.template, strategy.strategy_id
        return None, None

    def disable_strategy(self, strategy_id: str):
        """禁用策略"""
        for error_type, strategies in self.strategies.items():
            for strategy in strategies:
                if strategy.strategy_id == strategy_id:
                    strategy.is_active = False
                    strategy.last_updated = time.time()
                    self._save_strategies()
                    return

    def get_strategy_stats(self, error_type: str = None) -> Dict:
        """获取策略统计信息"""
        stats = {}

        if error_type:
            strategies = self.strategies.get(error_type, [])
            stats[error_type] = [
                {
                    "strategy_id": s.strategy_id,
                    "success_rate": s.success_rate,
                    "total_attempts": s.total_attempts,
                    "avg_fix_time": s.avg_fix_time,
                    "code_quality_score": s.code_quality_score,
                    "is_active": s.is_active,
                    "version": s.version
                }
                for s in strategies
            ]
        else:
            for et, strategies in self.strategies.items():
                stats[et] = [
                    {
                        "strategy_id": s.strategy_id,
                        "success_rate": s.success_rate,
                        "total_attempts": s.total_attempts,
                        "avg_fix_time": s.avg_fix_time,
                        "code_quality_score": s.code_quality_score,
                        "is_active": s.is_active,
                        "version": s.version
                    }
                    for s in strategies
                ]

        return stats


# 全局策略评估器实例
strategy_evaluator = StrategyEvaluator()
