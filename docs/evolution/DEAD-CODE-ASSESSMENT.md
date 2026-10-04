# 死代码集群评估（2026-09-28）

> 范围：agent 系统内「生产零消费」的模块与类。本次为最终评估，结论固化于此，
> 后续仅在接线或产品裁定退役时变更。

## 结论：全部保留，撤销删除计划

全库 AST 核实（`from X import (...)` 含多行）确认以下目标均为零生产消费，
但仓库已建立「实验性能力显式登记 + 门禁守护」机制
（`app/agent/capability_registry.py` + `tests/unit/test_capability_registry.py`，
后者把登记表变成契约：`wired` 必须有非测试调用点，`experimental` 必须确实零消费），
所有零消费能力均处于**被管理的透明状态**，保留成本为零（不进生产路径），
删除不可逆。故保留全部，逐项状态如下：

| 目标 | 行数 | 治理状态 |
|------|------|---------|
| `MultiModelAgent` 类（multi_model_agent.py） | ~200 | 已登记 experimental；同文件 `ModelRegistry`/`ModelRouter`/`TaskType` 被 react_agent 消费，文件必须保留 |
| `ai_reviewer.py` / `agent_executor.py` / `task_planner.py` | 568 | MultiModelAgent 组件，随其登记状态保留；ReAct 全链路未上线但完整 |
| `fix_pattern_cache.py` | 266 | 已登记 experimental；与 `feedback_learner.FixPattern` 为平行双实现，接线时二选一收敛 |
| `cloud_learning_hub.py` | — | 已登记 experimental |
| `strategy_learner.py` / `user_preference_learner.py` 等 21 项 | — | 均已登记，门禁测试守护 |
| shared_context SC7 五方法 | — | 方法级零消费（登记表为能力级，未覆盖）；与 SC1/SC8 边界决策绑定，保留待决 |
| `CodeReviewAgent`（app/utils/review/code_review_agent.py） | 583 | **本次补登记 experimental**（此前治理缺口：零生产实例化且未登记）；`.claude/skills/code-review` 文档引用其契约，属人工/外部流程调用面 |

## 本批改动

- `capability_registry.py` 补 `CodeReviewAgent` 条目（experimental），
  门禁测试 `test_capability_registry.py` 21 项通过。

## 接线提示（未来若激活）

- ReAct 链激活入口是 `MultiModelAgent.process_task(task_type=...)`，其内部
  TaskPlanner → AgentExecutor → AIReviewer 管线已闭环；`error_recovery.py:32`
  已单独使用 `ReActAgent`（ReAct 链唯一活着的入口）。
- `fix_pattern_cache` 与 `feedback_learner` 收敛时注意：前者的
  `is_anti_pattern`（失败>=3 且成功率<0.3）闸门逻辑有独立测试
  （`test_cache_review_gate.py` / `test_anti_pattern.py`），feedback_learner 无对应物。
- `CodeReviewAgent` 若退役需同步删除 `.claude/skills/code-review/SKILL.md` 引用
  与 `tests/unit/test_code_review_agent_skills.py`。
