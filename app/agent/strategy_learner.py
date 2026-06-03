"""
StrategyLearner - 策略优化学习

使用强化学习优化生成策略：
1. State: 项目复杂度、技术栈、错误上下文
2. Action: 模型选择、Prompt 模板、生成参数
3. Reward: 验证通过率 + 修复效率

支持：
- Q-Learning 策略优化
- 上下文感知的策略选择
- 策略效果追踪
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

# 策略数据目录
STRATEGY_DATA_DIR = Path("./data/strategy_learning")
# 策略文件
STRATEGY_FILE = STRATEGY_DATA_DIR / "q_table.json"


@dataclass
class StrategyState:
    """策略状态"""
    project_complexity: str  # simple/small/medium/large
    file_type: str  # python/javascript/typescript/vue 等
    error_type: Optional[str]  # 错误类型
    has_history_errors: bool  # 是否有历史错误

    def to_key(self) -> str:
        """转换为状态键"""
        return f"{self.project_complexity}:{self.file_type}:{self.error_type or 'none'}:{self.has_history_errors}"

    @classmethod
    def from_key(cls, key: str) -> "StrategyState":
        """从键还原状态"""
        parts = key.split(":")
        return cls(
            project_complexity=parts[0],
            file_type=parts[1],
            error_type=parts[2] if parts[2] != "none" else None,
            has_history_errors=parts[3] == "True"
        )


@dataclass
class StrategyAction:
    """策略动作"""
    model_selection: str  # 模型选择策略
    prompt_template: str  # Prompt模板类型
    temperature: float  # 温度参数
    enable_prevention: bool  # 是否启用预防提示

    def to_key(self) -> str:
        """转换为动作键"""
        return f"{self.model_selection}:{self.prompt_template}:{self.temperature}:{self.enable_prevention}"

    @classmethod
    def from_key(cls, key: str) -> "StrategyAction":
        """从键还原动作"""
        parts = key.split(":")
        return cls(
            model_selection=parts[0],
            prompt_template=parts[1],
            temperature=float(parts[2]),
            enable_prevention=parts[3] == "True"
        )


@dataclass
class QValue:
    """Q 值"""
    value: float = 0.0
    visits: int = 0
    last_updated: str = ""


class StrategyLearner:
    """
    策略优化学习器

    使用 Q-Learning 算法优化生成策略：
    Q(s,a) = Q(s,a) + α * (r + γ * max(Q(s',a')) - Q(s,a))

    其中：
    - α (learning_rate): 学习率 0.1
    - γ (discount_factor): 折扣因子 0.9
    - ε (exploration_rate): 探索率 0.2
    """

    LEARNING_RATE = 0.1
    DISCOUNT_FACTOR = 0.9
    EXPLORATION_RATE = 0.2

    # 可选的动作空间
    MODEL_SELECTION_STRATEGIES = ["best_performance", "balanced", "fast", "high_quality"]
    PROMPT_TEMPLATES = ["standard", "detailed", "minimal", "preventive"]
    TEMPERATURES = [0.3, 0.5, 0.7, 0.9]

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or STRATEGY_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.q_table: Dict[str, Dict[str, QValue]] = defaultdict(dict)
        self._current_state: Optional[StrategyState] = None
        self._current_action: Optional[StrategyAction] = None

        self._load_q_table()

    def _load_q_table(self):
        """加载 Q 表"""
        if STRATEGY_FILE.exists():
            try:
                with open(STRATEGY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for state_key, actions in data.items():
                    for action_key, q_data in actions.items():
                        self.q_table[state_key][action_key] = QValue(**q_data)

                logger.info(f"StrategyLearner: 加载了 {len(self.q_table)} 个状态的 Q 值")
            except Exception as e:
                logger.error(f"StrategyLearner: 加载 Q 表失败 {e}")

    def _save_q_table(self):
        """保存 Q 表"""
        try:
            data = {}
            for state_key, actions in self.q_table.items():
                data[state_key] = {}
                for action_key, q_value in actions.items():
                    data[state_key][action_key] = {
                        "value": q_value.value,
                        "visits": q_value.visits,
                        "last_updated": q_value.last_updated
                    }

            with open(STRATEGY_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"StrategyLearner: 保存了 {len(self.q_table)} 个状态的 Q 值")
        except Exception as e:
            logger.error(f"StrategyLearner: 保存 Q 表失败 {e}")

    def _get_all_actions(self) -> List[StrategyAction]:
        """获取所有可能的动作"""
        actions = []
        for model in self.MODEL_SELECTION_STRATEGIES:
            for template in self.PROMPT_TEMPLATES:
                for temp in self.TEMPERATURES:
                    for prevention in [True, False]:
                        actions.append(StrategyAction(
                            model_selection=model,
                            prompt_template=template,
                            temperature=temp,
                            enable_prevention=prevention
                        ))
        return actions

    def select_action(
        self,
        state: StrategyState,
        available_actions: Optional[List[StrategyAction]] = None
    ) -> StrategyAction:
        """
        使用 ε-greedy 策略选择动作

        Args:
            state: 当前状态
            available_actions: 可用动作列表（None 表示使用全部动作）

        Returns:
            选择的动作
        """
        self._current_state = state
        state_key = state.to_key()
        actions = available_actions or self._get_all_actions()

        # ε-greedy 策略
        import random
        if random.random() < self.EXPLORATION_RATE:
            # 探索：随机选择
            action = random.choice(actions)
            logger.debug(f"StrategyLearner: 探索模式选择动作 {action.to_key()}")
        else:
            # 利用：选择 Q 值最高的动作
            if state_key not in self.q_table or not self.q_table[state_key]:
                # 新状态，随机选择
                action = random.choice(actions)
            else:
                # 选择 Q 值最高的可用动作
                best_action = None
                best_q = float('-inf')
                for act in actions:
                    act_key = act.to_key()
                    if act_key in self.q_table[state_key]:
                        q = self.q_table[state_key][act_key].value
                        if q > best_q:
                            best_q = q
                            best_action = act

                if best_action is None:
                    action = random.choice(actions)
                else:
                    action = best_action

            logger.debug(f"StrategyLearner: 利用模式选择动作 {action.to_key()}")

        self._current_action = action
        return action

    def update(
        self,
        reward: float,
        next_state: Optional[StrategyState] = None
    ):
        """
        更新 Q 值

        Q(s,a) = Q(s,a) + α * (r + γ * max(Q(s',a')) - Q(s,a))

        Args:
            reward: 奖励值
            next_state: 下一状态（None 表示终止状态）
        """
        if self._current_state is None or self._current_action is None:
            logger.warning("StrategyLearner: 无法更新 Q 值，当前状态或动作未设置")
            return

        state_key = self._current_state.to_key()
        action_key = self._current_action.to_key()

        # 获取当前 Q 值
        current_q = self.q_table[state_key].get(action_key, QValue())

        # 计算下一状态的最大 Q 值
        if next_state is not None:
            next_state_key = next_state.to_key()
            if next_state_key in self.q_table and self.q_table[next_state_key]:
                max_next_q = max(q.value for q in self.q_table[next_state_key].values())
            else:
                max_next_q = 0.0
        else:
            max_next_q = 0.0  # 终止状态

        # Q-Learning 更新
        target = reward + self.DISCOUNT_FACTOR * max_next_q
        new_q_value = current_q.value + self.LEARNING_RATE * (target - current_q.value)

        # 更新 Q 表
        self.q_table[state_key][action_key] = QValue(
            value=new_q_value,
            visits=current_q.visits + 1,
            last_updated=datetime.now().isoformat()
        )

        logger.debug(
            f"StrategyLearner: 更新 Q 值 state={state_key} action={action_key} "
            f"reward={reward:.2f} new_q={new_q_value:.2f}"
        )

        self._save_q_table()

        # 重置当前状态和动作
        self._current_state = None
        self._current_action = None

    def get_best_action(self, state: StrategyState) -> Optional[StrategyAction]:
        """获取某状态下的最佳动作"""
        state_key = state.to_key()

        if state_key not in self.q_table or not self.q_table[state_key]:
            return None

        best_action_key = max(
            self.q_table[state_key].keys(),
            key=lambda k: self.q_table[state_key][k].value
        )

        return StrategyAction.from_key(best_action_key)

    def get_strategy_recommendation(
        self,
        project_complexity: str,
        file_type: str,
        error_type: Optional[str] = None,
        has_history_errors: bool = False
    ) -> Dict[str, Any]:
        """
        获取策略推荐

        Args:
            project_complexity: 项目复杂度
            file_type: 文件类型
            error_type: 错误类型
            has_history_errors: 是否有历史错误

        Returns:
            推荐策略字典
        """
        state = StrategyState(
            project_complexity=project_complexity,
            file_type=file_type,
            error_type=error_type,
            has_history_errors=has_history_errors
        )

        best_action = self.get_best_action(state)

        if best_action is None:
            # 返回默认策略
            return {
                "model_selection": "balanced",
                "prompt_template": "standard",
                "temperature": 0.7,
                "enable_prevention": True,
                "is_learned": False
            }

        # 获取 Q 值
        state_key = state.to_key()
        action_key = best_action.to_key()
        q_value = self.q_table[state_key].get(action_key, QValue())

        return {
            "model_selection": best_action.model_selection,
            "prompt_template": best_action.prompt_template,
            "temperature": best_action.temperature,
            "enable_prevention": best_action.enable_prevention,
            "q_value": q_value.value,
            "visits": q_value.visits,
            "is_learned": True
        }

    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计"""
        total_states = len(self.q_table)
        total_actions = sum(len(actions) for actions in self.q_table.values())
        total_visits = sum(
            q.visits for state_actions in self.q_table.values()
            for q in state_actions.values()
        )

        # 找出 Q 值最高的策略
        best_strategies = []
        for state_key, actions in self.q_table.items():
            for action_key, q_value in actions.items():
                if q_value.visits >= 5:  # 至少访问 5 次
                    best_strategies.append({
                        "state": state_key,
                        "action": action_key,
                        "q_value": q_value.value,
                        "visits": q_value.visits
                    })

        best_strategies.sort(key=lambda x: x["q_value"], reverse=True)

        return {
            "total_states": total_states,
            "total_actions": total_actions,
            "total_visits": total_visits,
            "avg_q_value": sum(
                q.value for state_actions in self.q_table.values()
                for q in state_actions.values()
            ) / total_actions if total_actions > 0 else 0,
            "top_strategies": best_strategies[:5]
        }

    def clear_q_table(self):
        """清空 Q 表"""
        self.q_table.clear()
        if STRATEGY_FILE.exists():
            STRATEGY_FILE.unlink()
        logger.info("StrategyLearner: 已清空 Q 表")


# 全局单例
_strategy_learner: Optional[StrategyLearner] = None
_learner_lock = asyncio.Lock()


async def get_strategy_learner() -> StrategyLearner:
    """获取 StrategyLearner 单例"""
    global _strategy_learner
    if _strategy_learner is None:
        async with _learner_lock:
            if _strategy_learner is None:
                _strategy_learner = StrategyLearner()
    return _strategy_learner
