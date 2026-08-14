# StrategyLearner 深扫（strategy_learner.py，399 行）

> 第七十五轮推演 | 2026-08-09 | 定位：§5.1 学习闭环「策略优化」组件（Q-Learning，学习闭环四组件深扫完成）

## 1. 模块定位

StrategyLearner 用 Q-Learning 优化生成策略：State（项目复杂度/文件类型/错误类型/历史错误）、Action（模型选择策略×4 × Prompt 模板×4 × 温度×4 × 预防开关×2 = 128 组合）、Reward（验证通过率+修复效率）。ε-greedy 选择（ε=0.2），Q 表 JSON 持久化。模块级单例 `get_strategy_learner`（:392）。这是 §5.3 Evaluator-optimizer 方向的「策略选择学习」组件。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | **生产代码零消费方** | rg 全库 `strategy_learner|StrategyLearner` 仅自身文件 |
| 理论关联 | 验证通过率 reward | 依赖验证端——TR1「无测试文件=通过」失真 → reward 信号污染 |

## 2. 深扫发现

### P2 项

- **SL1 生产代码零消费方（死代码模块）——学习闭环四组件深扫全部完成**——rg 全库仅自身文件；模块级单例 `get_strategy_learner` 从未被导入。§5.1 学习闭环四组件（strategy_learner/user_preference_learner/fix_pattern_cache/cloud_learning_hub）**全部零生产调用方确认完毕**。Q-Learning 策略优化从未接线到生成流程（select_action 无人调用、update 无人喂 reward）。修复方向：与 §5.3 Evaluator-optimizer 结合——strategy_evaluator 产出评估数据（当前 SE1 无输入）→ 喂 strategy_learner.update(reward) → select_action 驱动生成参数；**Q-Learning 是五条断裂学习链（SE1/FL1/FPC1/CLH1/DMR15）中策略选择维度的落地组件**。
- **SL2 `data_dir` 参数虚设（实测确认，与 CLH2 同款）**——`__init__` 收 data_dir（:110-111）并 mkdir，但 `_load_q_table`（:122）/`_save_q_table`（:148）用模块级 `STRATEGY_FILE`（`./data/strategy_learning/q_table.json`，:29）而非 `self.data_dir`。实测传 `data_dir=tmp_path`：update 后 tmp 空、`data/strategy_learning/q_table.json` 不存在 → `_save_q_table` 抛 Errno 2 被 except 吞（:152-153）。多实例/多项目隔离失效、相对 CWD 漂移（SE6/FL5 家族）。

### P3 项

- **SL3 单步 MDP 使折扣因子 γ 失效**——update（:222-276）生产语义是单步（select_action → update(reward, next_state=None)），:254 `max_next_q = 0.0` 终止态 → **γ×max_next_q 恒 0**，Q 更新退化为 `Q += α*(reward - Q)`（纯 reward 均值），无时序信用分配。若后续接线时 next_state 永远 None，Q-Learning 的表征能力（跨状态信用传播）无法发挥——接线时必须设计多步序列（生成→验证→修复循环）。
- **SL5 ε 无衰减**——EXPLORATION_RATE=0.2 固定（:103/:191），不随训练轮次衰减，探索永不收敛（最优动作会被持续 20% 概率打断）。
- **SL4 `_current_state`/`_current_action` 实例状态非并发安全**——select_action 设置、update 消费（:185-186/:240-241），多协程并发交错串扰（MCP1 家族）。
- **SL8 每 update 全量写 Q 表无锁**——:272 `_save_q_table` 全量 JSON dump，高频训练下 I/O 瓶颈 + 并发写竞态（FPC7 家族）。

## 3. 演化方向

### 3.1 Q-Learning 的接线语义

strategy_learner 是学习闭环中设计最完整的组件（State/Action/Reward/Q-Learning 算法齐全），但完全未接线。演化前提链：① 验证端修复（TR1 无测试文件=通过 → reward 才有意义）；② strategy_evaluator 接线（SE1 产生评估数据）；③ error_recovery 每轮修复结果 → update(reward)；④ select_action → 生成参数注入。**在这条链之前，SL2/SL3/SL5 的修复无生产价值**（与 CLH1/FL1 同理）。

### 3.2 与 DynamicModelRouter 学习路由的边界

strategy_learner（状态=复杂度/文件类型/错误，动作=完整生成策略）与 DMR15 的 LearningRouter（状态=task_type，动作=模型选择）**功能重叠**——学习路由是 strategy_learner 动作空间的一个子集（model_selection）。演化方向：LearningRouter 收敛进 strategy_learner 的动作空间，避免两个学习器并存（CR1 双轨家族）。

## 4. 主线关联

- **学习闭环主线（四组件全灭 + 第五断点）**：SL1（策略学习死代码）+ FPC1（复用死代码）+ CLH1（共享死代码）+ FL1（反馈拦截）+ SE1（评估无输入）+ DMR15（学习路由无写入）——学习闭环全链路无一接线，strategy_learner 深扫后四组件确认完毕
- **reward 信号污染**：SL3 依赖验证通过率，TR1 失真使 reward 不可信——「存在≠正确」验证端与学习端耦合
- **参数虚设**：SL2 data_dir（CLH2 同款）
- **双轨并存**：SL 与 LearningRouter 学习器重叠（CR1 家族）

## 5. 测试状态

`tests/unit/test_learning_capabilities.py` 有 TestStrategyLearner（:234-）——但全走内存态 Q 表断言，data_dir 落盘失败（SL2）被测试通过掩盖（TR2 家族，与 TestCloudLearningHub 同款缺陷）。
