# 错误分析决策链（complexity / error_classifier / strategy_evaluator）演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（错误恢复决策链 + 需求复杂度分析）
> 路径：app/agent/complexity.py（172 行）、app/agent/error_classifier.py（196 行）、app/agent/strategy_evaluator.py（329 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

三个小文件构成「错误恢复决策链」前端 + 需求复杂度分析：

| 文件 | 职责 | 主要类/函数 |
|------|------|------------|
| complexity.py | 需求关键词复杂度分析，产出 `ComplexityAnalysis`（level / 文件数 / 前后端数据库认证 / 技术栈 / 风险 / tokens / 成本） | `ProjectComplexity`（5 级枚举）、`ComplexityAnalyzer.analyze()`（complexity.py:59）、`_estimate_tokens()`（:129）、`analyze_with_llm()`（:170 兼容 alias） |
| error_classifier.py | 错误信息 → `ErrorClassification`（规则优先 + 模型兜底） | `ErrorClassifier._rule_based_classification()`（:110）、`_model_based_classification()`（:126）、`get_fix_strategy_by_type()`（:184 死代码）、`add_to_history()`（:190） |
| strategy_evaluator.py | 修复策略 A/B 测试框架（80/20 exploit/explore + 自动提升） | `StrategyEvaluator.get_best_strategy()`（:85）、`create_or_update_strategy()`（:119）、`record_evaluation_result()`（:163）、`_check_strategy_promotion()`（:206）、`get_strategy_template()`（:270） |

## 2. 依赖与被依赖

- **导入依赖**：error_classifier 依赖 `app.utils.call_llm`（error_classifier.py:8）+ `DEFAULT_CODE_MODEL`（:9）——直连模型客户端；strategy_evaluator 纯标准库（json/time/random）；complexity 纯标准库。
- **生产消费方**：
  - complexity：`orchestrator_generation/mixin.py:50-51`、`evaluate_mixin.py:28-29`（生成/评价两条链基类均实例化并 `analyze(requirement)`）；`orchestrator.py:7/115/128`；`api/v1/ai_agent/association_endpoints.py:32/36`；`api/v1/ai_agent/orchestrate_endpoints.py:1154-1156`。其 `level` 被 `orchestrator_utils.py:306-337 _estimate_generation_cost` 查表作为成本审批输入（traditional_generate.py:95-120）。
  - error_classifier：`error_recovery.py:19/201-202`（`classify_error` + `add_to_history`）；`fix_pattern_cache.py:19/103/108/121`（仅类型导入 `ErrorClassification`）。
  - strategy_evaluator：`error_recovery.py:20/205`（`get_strategy_template`）、`:278/315/344/361/381`（`record_evaluation_result`）。
- **测试覆盖**：`tests/unit/test_error_classifier.py`（91 行，测规则分类/字段/history，未测模型兜底路径）；`tests/unit/test_strategy_evaluator.py`（81 行，测 create/update/stats，**未测 80/20 分配与 promotion**）。两者均直接实例化框架本身，未覆盖生产接线。complexity 无独立测试（test_orchestrator.py 间接触碰）。

## 3. 已探明 Bug

### CEC1 [P2] strategy_evaluator A/B 框架空转，整条评估链为死路径

- **现象**：修复循环从不产生策略变体，`record_evaluation_result` 从不真正写统计。
- **Bug 代码**：

```python
# strategy_evaluator.py:119 - 唯一创建策略的入口，全代码库零调用
def create_or_update_strategy(self, error_type, template, is_new_variant=False) -> str:
    ...
    self.strategies[error_type].append(new_strategy)
    self._save_strategies()

# error_recovery.py:205-209 - get_strategy_template 恒返回 (None, None)，恒走默认模板
fix_template, strategy_id = strategy_evaluator.get_strategy_template(classification.error_type)
if fix_template is None:
    fix_template = self._build_default_fix_template()

# error_recovery.py:277 - strategy_id 恒为 None，评估记录被短路跳过
if strategy_id:
    strategy_evaluator.record_evaluation_result(...)
```

- **根因**：策略创建入口从未接线；`repair_strategies.json` 不存在（已确认），`self.strategies` 恒空，`get_best_strategy` 恒返回 None。
- **影响**：80/20 流量分配、成功率统计、自动提升、`get_strategy_stats` 全部空转；修复策略实际来源 = `_build_default_fix_template` 单一默认模板，「按错误类型选策略」未生效。
- **触发条件**：任何一次错误恢复流程。
- **验证方式**：`rg -n "create_or_update_strategy" app/` 仅 strategy_evaluator.py:119 定义处。

### CEC2 [P2] 默认修复模板占位符注入缺失，LLM 收到字面 `{content}`

- **现象**：system_prompt 中【修复策略】段含未替换的字面占位符。
- **Bug 代码**：

```python
# error_recovery.py:422-438 - 默认模板含三个占位符
return """请修复以下代码中的错误。
【当前代码】
```
{content}
```
【发现的错误】
{error_context}
【修复要求】
1. {suggested_fix_strategy}
..."""

# error_recovery.py:226-234 - 直接 f-string 插入，不替换占位符
system_prompt = f"""...【修复策略】
{fix_template}"""

# error_recovery.py:453 - 仅 error_context 被替换，且结果用于 fix_prompt 而非 system_prompt
if template and "{error_context}" in template:
    return template.replace("{error_context}", base_context)
```

- **根因**：模板注入只处理了 `{error_context}` 一处，且替换结果注入的是 fix_prompt（error_recovery.py:244），system_prompt 里的 fix_template 三个占位符全部保留字面量。
- **影响**：LLM 收到的修复指令含 `{content}` / `{suggested_fix_strategy}` 字面文本，修复质量依赖模型自行忽略乱码；ERL2 的具体化。
- **触发条件**：每次错误恢复（走默认模板时必现）。
- **验证方式**：打印 system_prompt 断言无 `{content}`。

### CEC3 [P2] 错误分类模型兜底直连 call_llm，绕过客户端收敛（LCL1 范围）

- **现象**：`_model_based_classification` 的模型调用不带 api_key_token、无信号量、无成本追踪。
- **Bug 代码**：

```python
# error_classifier.py:154-162
try:
    response = await call_llm(
        model=DEFAULT_CODE_MODEL,   # 无 api_key_token
        prompt=f"【USER】\n{prompt}",
        stream=False,
        max_tokens=500,             # 硬编码
        temperature=0.1,
        system_prompt=system_prompt
    )
```

- **根因**：与 ERL4（修复 LLM 无 cost_tracker）、EV1/TG1 同源——三处直连 call_llm 都不走统一客户端；且分类调用发生在 `self._semaphore` 之外（error_recovery.py:201 在循环外），并发下无节流。
- **影响**：错误分类成本不计入总成本（LC1 关联）；非默认 Key 用户的分类请求仍走默认模型配置。
- **触发条件**：错误信息未命中 8 类规则（如罕见错误）时走模型兜底。
- **验证方式**：构造不命中规则的错误串，观察 call_llm 实参缺 api_key_token。

### CEC4 [P3] 硬编码模型名/映射扩散，与 DMR 唯一决策源冲突

- **现象**：三处独立模型决策逻辑并存。
- **Bug 代码**：

```python
# error_classifier.py:93 / :180 - 修复策略内硬编码模型名
"fix_strategy": "使用 deepseek-r1 深度分析错误信息，重新生成核心逻辑"

# error_recovery.py:465-474 - 硬编码错误类型→模型映射兜底
DEFAULT_ERROR_MODEL_MAPPING = {
    "NameError": DEFAULT_FAST_MODEL,
    "AttributeError": DEFAULT_CODE_MODEL,
    ...
}
```

- **根因**：IM1（SiliconFlow 硬编码）、DMR 唯一模型决策源之外的第三/四处模型名硬编码，未收敛到 `load_agent_model_config`。
- **影响**：换 provider 时 `deepseek-r1` 与 DEFAULT_* 常量语义漂移，模型选择不可审计。
- **触发条件**：LogicError 分类或错误类型不在映射时。
- **验证方式**：rg 统计模型名散落点。

### CEC5 [P3] `_check_strategy_promotion` 连续性判定语义不成立

- **现象**：即使接线，提升判定也几乎无法正确触发。
- **Bug 代码**：

```python
# strategy_evaluator.py:243-260
consecutive_better = 0
for i in range(len(recent_evaluations) - 1):
    if (recent_evaluations[i].strategy_id == candidate.strategy_id and
        recent_evaluations[i+1].strategy_id == current_main.strategy_id):
        candidate_score = recent_evaluations[i].success * 1.0 + recent_evaluations[i].code_quality_score
        main_score = recent_evaluations[i+1].success * 1.0 + recent_evaluations[i+1].code_quality_score
        if candidate_score > main_score:
            consecutive_better += 1
        else:
            consecutive_better = 0
```

- **根因**：A/B 对照要求「同一错误上两策略配对对比」，此处却比较时间上相邻的两个独立事件（candidate 在前、main 在后），且要求严格相邻交替模式才能累积计数；`recent_evaluations[-10:]` 跨所有 error_type 全局过滤，配对不成立。`main_score` 用 candidate 后一时刻的 main 记录，非同一错误。
- **影响**：自动提升逻辑即使接线也是伪 A/B，无法产出可信的策略替换。
- **触发条件**：A/B 接线后（当前空转不触发）。
- **验证方式**：构造 10 条交替评估记录，观察提升是否按预期触发/不触发。

### CEC6 [P3] 策略文件非原子写 + CWD 敏感相对路径 + 全局单例

- **现象**：`repair_strategies.json` 直接覆盖写、路径相对 CWD、全局单例跨请求共享。
- **Bug 代码**：

```python
# strategy_evaluator.py:52 - 相对路径，随 CWD 变化
self.strategies_file = strategies_file or Path("repair_strategies.json")
# :73-83 - 直接 json.dump 覆盖，无临时文件+rename
with open(self.strategies_file, 'w', encoding='utf-8') as f:
    json.dump(strategies_dict, f, indent=2)
# :329 - 全局单例
strategy_evaluator = StrategyEvaluator()
```

- **根因**：ERL5/MCP1 同类全局单例污染（跨请求累积 stats/evaluation_history）；文件写无原子性与并发保护；路径依赖启动目录。
- **影响**：并发错误恢复下文件损坏；跨请求统计串扰。
- **触发条件**：多请求并发恢复、或 CWD 变化。
- **验证方式**：单例 `is` 断言 + 并发写文件内容损坏复现。

### CEC7 [P3] 成本估算体系分裂，complexity 估算未被审批使用

- **现象**：两套成本估算并存且结果不一致。
- **Bug 代码**：

```python
# complexity.py:112-113 - 估算 A：tokens/1000 * $0.001
estimated_cost_usd = (estimated_tokens / 1000) * 0.001

# orchestrator_utils.py:306-337 - 估算 B：按 level 查固定表
cost_estimates = {
    "simple": {"tokens": 5000, ...},
    "medium": {"tokens": 45000, ...},
    ...
}
```

- **根因**：`complexity._estimate_tokens`（files×3000 + 系数，基于估算文件数）与 `orchestrator_utils._estimate_generation_cost`（level→固定 tokens 查表）两套独立逻辑。传统生成链的成本审批（traditional_generate.py:95-120）只用估算 B；估算 A 仅作 reporting 展示。
- **影响**：`ComplexityAnalysis.estimated_tokens/estimated_cost_usd` 与审批结果不一致，用户看到两种成本数字；成本估算与 LC1 实际成本主线脱节。
- **触发条件**：任何生成任务（reporting 与审批显示差异）。
- **验证方式**：同一需求对比 complexity.py:113 与 orchestrator_utils.py:318 输出。

### CEC8 [P3] 杂项：死代码 / 无界内存 / print 日志

- **现象**：
  - `error_classifier.get_fix_strategy_by_type`（error_classifier.py:184-188）全代码库零调用；
  - `classification_history`（error_classifier.py:98/190-192）只追加无读取，error_recovery.py:202 每次修复 append，无界增长；
  - 四处 `print()`（error_classifier.py:173、strategy_evaluator.py:71/83/264）替代 logger。
- **根因**：历史遗留未清理。
- **影响**：长期运行内存增长；调试残留污染 stdout（SSE 输出流可能受影响）。
- **验证方式**：rg 各符号消费方。

## 4. 潜在问题与未知点

- strategy_evaluator 若保留 A/B 能力，需要明确种子策略来源与配对语义（LangGraph Evaluator-optimizer 方向见 EVOLUTION.md §5.3），当前实现即使接线也不满足对照实验要求。
- complexity 关键词列表中英文混合（FRONTEND_KEYWORDS 有 'ui' 无 'frontend'，BACKEND_KEYWORDS 有 'server' 无 'backend'），纯英文需求（如 "Build a REST API backend"）可能被低估为 SIMPLE，连带成本审批偏低。
- `analyze_with_llm`（complexity.py:170）名不符实——纯关键词 alias，注释已自认「不再使用 LLM 校准」，是废弃 API 保留。
- fix_pattern_cache.py:103-121 消费 `ErrorClassification` 但签名来自何处实例化待确认（error_recovery 或 specialist 链是否构造 FixPatternCache 实例）。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | strategy_evaluator 二选一：a) 接线 `create_or_update_strategy`（按 error_type 种入规则模板作为种子策略）并修复 promotion 配对语义；b) 若无需 A/B 则降级为纯模板库，删除 promotion/stats 死逻辑 | 消除空转死路径，明确修复策略真实来源 | strategy_evaluator.py:119/206、error_recovery.py:205 | 待记 |
| 2 | P2 | 修复默认模板占位符：插入 system_prompt 前用 f-string 替换 `{content}`/`{suggested_fix_strategy}`（`{error_context}` 保留给 targeted 函数） | LLM 收到完整修复指令，ERL2 落地 | error_recovery.py:226-234/422-438/453 | 待记 |
| 3 | P2 | error_classifier 模型兜底走统一 LLM 客户端：补 api_key_token、信号量、cost_tracker，max_tokens 从配置取；`classification_history` 改有界或有读取方 | 错误分类成本可测、token 正确、LCL1 收敛范围扩展覆盖 | error_classifier.py:126-182/98 | 待记 |
| 4 | P3 | 删除硬编码模型决策：fix_strategy 中 `deepseek-r1` 改为通用描述，`DEFAULT_ERROR_MODEL_MAPPING` 删除、统一查 DMR | 唯一模型决策源，换 provider 可审计 | error_classifier.py:93/180、error_recovery.py:465-474 | 待记 |
| 5 | P3 | 策略文件原子写（临时文件+rename）与固定项目内路径；全局单例改按请求实例或加锁 | 防并发损坏与跨请求污染 | strategy_evaluator.py:52/73-83/329 | 待记 |
| 6 | P3 | 成本估算统一：删除 complexity.py:112-113 独立估算或让 `_estimate_generation_cost` 复用 `complexity.estimated_tokens`；补 frontend/backend 英文关键词 | 审批与 reporting 成本一致，英文需求不低估 | complexity.py:49-50/113、orchestrator_utils.py:306-337 | 待记 |
| 7 | P3 | 删 `get_fix_strategy_by_type` 死代码；`classification_history` 清理；print→logger | 消除死代码与内存/输出污染 | error_classifier.py:184/98、strategy_evaluator.py:71/83/264 | 待记 |

## 6. 演化方向关联

- 错误恢复决策链是 LangGraph **Evaluator-optimizer** 模式（EVOLUTION.md §5.3）的轻量实现雏形：error_classifier=评估端、strategy_evaluator=优化策略库。当前卡在 strategy_evaluator 空转——接线（建议 1）是该方向成立的前提，否则维持「分类→默认模板」简化链路。
- 成本估算分裂（CEC7）归入 LC1 成本主线；错误分类直连 LLM（CEC3）归入 LCL1 收敛范围（与 ERL4/EV1/TG1 同源，收敛范围需统一扩展）。
- 硬编码模型名（CEC4）归入 DMR 唯一模型决策源主线（IM1 同类），阶段一 RA2/RE1 收敛模型决策时可一并纳入。
- 全局单例（CEC6）与 ERL5/MCP1 同类，归入「单例→按需实例」收敛主线。
