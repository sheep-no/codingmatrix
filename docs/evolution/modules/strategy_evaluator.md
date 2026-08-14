# strategy_evaluator.py 深扫详档

> 版本：v1.63 | 日期：2026-08-09 | 文件：`app/agent/strategy_evaluator.py`（329 行，另附 `strategy_learner.py` 399 行 Q-learning 死代码核验）｜方法 9 个
> 结论：**P2 3 项（SE1 实测、SE2/SE7 静态）、P3 3 项**｜单元测试：零

## 定位

错误修复策略的 **A/B 测试与自动优化框架**（Evaluator-optimizer 的 evaluator 侧）：80/20 exploit/explore 流量分配、成功率/耗时/质量统计、连续 N 次更优则提升为主策略。全库唯一消费方是顶层错误恢复循环 `error_recovery.py`。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | error_recovery.py | :205 `get_strategy_template(classification.error_type)`；:278/:315/:344/:361/:381 `record_evaluation_result`（均带 `if strategy_id:` 保护） | 修复模板选择 + 结果回馈 |
| 被消费 | error_recovery_loop.py（顶层，已扫） | 经 error_recovery 间接 | 完整恢复链 |
| 依赖 | repair_strategies.json（默认相对路径 :52） | `_load_strategies`/`_save_strategies` | 策略持久化 |
| 关联 | strategy_learner.py（399 行） | **全库无消费方**（rg 零结果），且不引用 evaluator | Q-learning 策略学习器，完整死模块 |
| 测试 | — | — | **零测试** |

## 关键代码路径

`get_best_strategy`（:85）：策略组内按 success_rate 排序 → 80% 取最高（exploit）/ 20% 取 `random.choice(rest)`（explore）。`record_evaluation_result`（:163）：追加 history + 更新命中策略统计 + 全量写盘 + 触发 `_check_strategy_promotion`。`_check_strategy_promotion`（:206）：最近 10 次评估窗口内找 `(candidate, main)` 严格相邻对，累计 candidate 连续更优 ≥3 次则提升。

## Bug 清单

### P2

**SE1 [P2] A/B 框架策略库恒空——无创建接线 + 持久化文件不存在（实测）**

- 位置：`create_or_update_strategy`（:119）**全库无调用方**；`repair_strategies.json` **全盘不存在**（`find / -name` 零结果）
- 实测：
  ```
  StrategyEvaluator(空文件) → get_strategy_template("syntax_error") → (None, None)
  record_evaluation_result(strategy_id=None, ...) → 只 append history，strategies 仍 0 条
  ```
- 现象：error_recovery.py 只读（:205 get_strategy_template）只写（record_evaluation_result），从不 `create_or_update_strategy`；record 侧又有 `if strategy_id:` 保护（:274/:313 等）——strategy_id 恒 None → **连评估记录都不落**
- 影响：80/20 exploit/explore、variant 探索（success_rate=0.1 冷启动）、连续 N 次提升主策略——**全部死路径**。error_recovery:210 `if fix_template is None: fix_template = self._build_default_fix_template()` 恒走默认模板 → 修复模板从未被 A/B 优化过。§5.3 Evaluator-optimizer 方向的评估侧无数据输入
- 修复方向：error_recovery 无策略时先 `create_or_update_strategy(error_type, default_template)` 建立基线；或首次运行自动 seed 策略库

**SE2 [P2] promotion 连续更优判定要求严格交替配对，结构上几乎不可触发（静态确认）**

- 位置：`_check_strategy_promotion` :244-246 `if recent[i].id == candidate and recent[i+1].id == current_main`——只在 `(candidate, main)` **相邻**时计分；:236 `len < N_CONSECUTIVE_BETTER * 2` 需 ≥6 条
- 现象：真实 80/20 随机流量下评估序列是 mixed（含 candidate-candidate、main-main、main-candidate 相邻），`(candidate, main)` 这种严格交替相邻对出现且连续 3 次且每次都 candidate 更优的概率极低；且 `evaluation_history[-10:]` 是全局窗口（:232），被跨 error_type 评估稀释
- 影响：即使 SE1 修复（库有数据），promotion 也难以触发——「自动策略替换」承诺需重写判定（按时间窗口分组统计各策略胜率，而非相邻配对）
- 修复方向：改为候选策略独立窗口统计（其最近 N 次 vs 主策略同时段），或简化为主策略定期重排

**SE3 [P2] strategy_learner.py（399 行 Q-learning）全库死代码（静态确认）**

- 位置：`app/agent/strategy_learner.py`（StrategyState/StrategyAction/QValue/StrategyLearner，Q-table 持久化）——`rg` 全库零消费方，也不引用 strategy_evaluator
- 影响：完整的「策略学习器」（强化学习侧）从未接线，与 SE1 的「评估器无数据」成对——**Evaluator-optimizer 的两侧（评估无数据、学习无入口）都未落地**。TASKS 汇总此前判断「strategy_evaluator A/B 框架接线是 Evaluator-optimizer 方向的前提」得到确认：接线缺失
- 修复方向：决策（纳入 P0 后）——要么让 error_recovery 先走通 SE1，再决定 strategy_learner 是否复用 evaluator 的策略库还是独立演进

### P3

**SE4 [P3] 全模块用 print 而非 logger**

- `_load_strategies`（:71）、`_save_strategies`（:83）、`_check_strategy_promotion`（:264）用 `print` 输出——生产日志链路丢失

**SE5 [P3] `_save_strategies` 无锁并发写同一 JSON**

- 每次 record 全量写盘（:203），多实例/并发请求下竞态丢策略

**SE6 [P3] 策略库默认相对路径依赖工作目录**

- `:52` `Path("repair_strategies.json")`——工作目录变化即丢库/错库，与 spec_cache CACHE_DIR（SC1 同类）、utils 沙箱配置同类路径卫生问题；应并入 §5.6 支柱 4（检查点持久化的路径规范）

## 与既有主线闭环

- **§5.3 Evaluator-optimizer 主线**：strategy_evaluator 本应是「生成器-评估器」中评估侧的落点（修复模板的自动择优），但 SE1（无数据）+ SE3（学习器无入口）使该方向**零落地**——这是除五支柱结构外最大的架构承诺缺口
- **错误恢复闭环**：error_recovery（顶层恢复循环执行器）的修复模板恒默认（SE1）→ 修复效果仅靠单模板 + refinement_loop（RL1 空操作）→ 修复循环质量端无任何自适应
- **§5.6 支柱 4（检查点）**：策略库是「经验检查点」，与 spec_cache SC1（重启全丢）同源的持久化路径/加载问题家族
