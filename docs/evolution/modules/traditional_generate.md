# 传统生成链路演化深扫文档

> 版本：v1.0 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 大系统 / 编排层·传统生成路径（补扫，不在原 13 模块索引内）
> 路径：`app/agent/orchestrator_generation/`（traditional_generate.py 427 行 + incremental_generate.py 85 行 + evaluate_mixin.py 351 行 + mixin.py 146 行 + coverage_checker.py 61 行 + feature_extractor.py 37 行）
> 索引：[TASKS.md](../TASKS.md)｜关联：[error_recovery_loop.md](error_recovery_loop.md)｜[incremental_modify.md](incremental_modify.md)｜[error_recovery.md](error_recovery.md)

## 1. 模块作用与功能

传统生成路径是 spec_first 之外的**第二套生成链路**，由 mixin.py 组装 6 个 Mixin：

- **`mixin.py`（146 行）**：`GenerationMixin` 组装层——`generate()` 入口三分流（evaluation_only→evaluate / spec_first→spec_first / 否则→`_generate_traditional`）；`_initialize_components` 初始化全部角色与工具
- **`traditional_generate.py`（427 行）**：`_generate_traditional` 主流程——缓存查找（embedding+审查闸门）→ 架构设计→成本估算→审批→依赖图分层生成→完整性验证→沙箱验证→动态测试→ReAct 自动修复→成本/覆盖率报告
- **`incremental_generate.py`（85 行）**：`_handle_incremental_generation`——会话恢复模式的增量生成（git stash 备份→并发生成→失败回滚）
- **`evaluate_mixin.py`（351 行）**：`evaluate()`——纯评价模式（evaluation_only），需求/架构双 LLM 评价 + 规则化风险评估 + 总评
- **`coverage_checker.py`（61 行）**：`check_requirement_coverage`——需求项关键词在 file_plan/架构文本的 30% 命中覆盖判定
- **`feature_extractor.py`（37 行）**：`extract_and_save_feature_list`——生成后功能清单提取 + 模板自动萃取

## 2. 依赖与被依赖

- **生产使用方**：`orchestrator.py` 组装 `GenerationMixin`（入口 generate）
- **传统链路关键依赖**：Architect/FrontendEngineer/BackendEngineer/CodeReviewer、ErrorRecoveryLoop（顶层）、CodeValidator、APIContractChecker、DependencyGraph、LanguageAdapterRegistry、IntegrityValidator、IsolatedTestRunner、`validate_in_sandbox`
- **ERR 链**：traditional_generate.py:297 `_try_react_auto_fix` → 子包 error_recovery.py:26（ERR1/ERR2 已确认失效）——传统链路动态测试失败后的 ReAct 修复**当前完全失效**
- **测试覆盖**：`test_aicloud` 47 passed 覆盖传统链路核心（全为敏感过滤）；spec_first 有独立测试集

## 3. 已探明 Bug

### TG1 [P2] 缺失文件补充走直连 LLM + 非原子写盘

- **Bug 代码**：

```python
# traditional_generate.py:250-257 - 补充缺失文件
content = await self._direct_llm_generate_file(missing_file, desc, project_context)
...
with open(full_path, 'w', encoding='utf-8') as f:   # 非 write_file_atomic
    f.write(content)
```

- **根因**：完整性验证补缺失文件用直连 LLM（无 semaphore/cost_tracker），且 `open` 直写（与 spec_first 的 write_file_atomic 不一致）
- **影响**：并发不受控、成本不计入、写盘非原子

### TG2 [P2] `success` 语义与 test_results 默认值耦合

- **Bug 代码**：

```python
# traditional_generate.py:201 - 默认 success=True
test_results = {"success": True, "message": "未运行动态测试"}
# :345 - 最终 success 与测试结果绑定
"success": len(self.errors) == 0 and test_results.get("success", True),
```

- **影响**：`enable_validation=False` 时 `should_test` 恒 False，test_results 保持默认 True——success 只依赖 errors；但 `enable_validation=True` 且动态测试失败但 ReAct 修复失效（ERR 链）时 success=False 且无修复——**语义合理但掩盖了 ReAct 修复完全失效的事实**（用户只看到 success=False，不知修复机制已坏）

### TG3 [P2] 缓存审查闸门失败后重新设计架构——但缓存命中路径跳过成本估算

- 缓存命中（:60-66）直接加载 architecture/file_plan，**跳过 :95 成本估算后的审批**（:105 只在高成本+require_approval 时暂停）——缓存命中时无成本审批流程，语义不一致

### TG4 [P2] 项目级沙箱仅 import 级验证

- **Bug 代码**：:270 `validate_in_sandbox(..., level="import", ...)`——只验证 import 级错误，运行级/API 级不验证；且结果仅 warning（:278）不阻塞
- **影响**：项目级问题只在 warnings 里，`success` 不受影响

### IG1 [P2] 增量生成依赖 LLMClient 内部信号量——并发不受本链路控制

- **Bug 代码**：incremental_generate.py:60-61 注释「由 LLMClient 内部信号量控制并发度」——`asyncio.gather` 无本地信号量，完全依赖 LLMClient（LCL1 缺陷：全局→按模型顺序泄漏）——若 LLMClient 信号量修复延迟，增量并发生成可无界

### IG2 [P3] `generated_files` 结构与复用项混用

- incremental_generate.py:44-49 append 的 reused 项（path/description/success/reused）与 :78 正常项（含 size/action 等）结构不一致——下游消费方（completeness 验证 :211-219 只读 path/content）兼容，但结构不统一

### IG3 [P3] stash 失败静默继续

- incremental_generate.py:63 `stashed = _git_stash_push(...)`——若 push 失败 stashed=False，仍继续生成且失败不回滚

### EV1 [P2] 评价 LLM 调用绕开 model_config/信号量/成本追踪

- **Bug 代码**：

```python
# evaluate_mixin.py:156-160 - 直连 call_llm，无 max_tokens/config/semaphore/cost_tracker
response = await call_llm(model=EVALUATION_MODEL, prompt=prompt, api_key_token=self.api_key_token)
```

- **影响**：与 SFG3/ERL4 同源——评价模式的 LLM 调用不受模型配置（按上下文窗口动态）与信号量约束、成本不计入；且 `EVALUATION_MODEL` 是模块级常量（:15）而非 model_assignment 分配

### EV2 [P2] 评价 JSON schema 混用——总评分可能恒 0

- **Bug 代码**：`_parse_evaluation_json` :339 接受「顶层 score 或 completeness」两套格式；`_build_overall_assessment` :304-305 只读 `completeness.score`——若 LLM 返回顶层 score 格式，`completeness` 缺失 → req_score=0 → 总评分拉低
- **影响**：评价结果 grade 可能系统性偏低；`_fallback_evaluation`（:346-351）也返回顶层 score——fallback 时 req_score=0 必然发生

### EV3 [P3] 评价模式 architect/reviewer 无 semaphore/cost_tracker

- evaluate_mixin.py:43-52 构造 Architect/CodeReviewer 未传 semaphore/cost_tracker——评价模式 LLM 并发不受控、成本不计入

### CC1 [P2] 覆盖率 30% 关键词命中判定过宽——覆盖率虚高

- **Bug 代码**：

```python
# coverage_checker.py:45-46 - 30% 关键词命中即算已覆盖
matched_kw = sum(1 for kw in keywords if len(kw) > 2 and kw in combined_text)
if matched_kw < len(keywords) * 0.3:
    uncovered.append(...)
```

- **根因**：需求项 10 个词命中 3 个（30%）即判覆盖；且 `re.findall(r'\w+', item.content)` 对中文需求按整词匹配（Python 3 `\w` 含 Unicode）——中文长句极难整词命中，实际可能**反向偏低**或按关键词碎片误判
- **影响**：coverage_rate 与「功能真实实现」无强相关——只反映关键词文本出现；传统链路 :315 仅当 uncovered 非空才报 warning，`coverage_rate=1.0`（无 association 时 :12/:16 硬编码）直接展示为「全覆盖」

### FE1 [P3] 特征提取静默丢文件

- feature_extractor.py:20 `if path and content:` 才收录——缺 content 键的文件静默跳过；`trigger_template_extraction` 无超时（但异常已捕获）

## 4. 潜在问题与未知点

- **两套生成链路并存**：传统（traditional_generate，缓存/依赖图/沙箱）vs spec_first（2383 行编排 Mixin）——入口 `generate()` 按 `spec_first` 开关分流，后续迭代维护成本双倍（TG 系列与 SPFG 系列问题大量同构）
- `_cache_review_gate`（traditional_generate.py:44）——缓存命中后 reviewer 审查，闸门失败回退重新设计——审查用 reviewer（架构模型）成本不低，缓存命中被审查逻辑部分抵消
- `_estimate_generation_cost` 与 LC1（成本恒 0）联动——成本估算基于 token 估算而非实测
- `_wait_for_approval("cost_estimation", timeout=300.0)`（:112）——300 秒等待用户审批，阻塞式

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | TG1：补缺失文件走统一生成入口（semaphore/cost_tracker/write_file_atomic） | 并发/成本/写盘统一 | traditional_generate.py:250-257 | 新增 |
| 2 | P2 | TG3：缓存命中路径也过成本审批（或显式声明跳过） | 成本审批语义一致 | traditional_generate.py:60-66 | 新增 |
| 3 | P2 | TG4：项目级沙箱按需提升 level 且结果进 errors（可配置） | 项目级问题不被淹没 | traditional_generate.py:270 | 新增 |
| 4 | P2 | IG1：增量并发生成本地加信号量（不依赖 LLMClient 内部） | 并发有界可预测 | incremental_generate.py:65 | 新增 |
| 5 | P2 | EV1/EV3：评价模式 LLM 调用统一走客户端配置（model_config/semaphore/cost_tracker） | 评价成本计入、并发受控 | evaluate_mixin.py:43-52/:156-160 | 新增 |
| 6 | P2 | EV2：评价 JSON 解析统一 schema（completeness.score 单一入口），fallback 同 schema | 总评分不因格式混用失真 | evaluate_mixin.py:304-305/:339/:346 | 新增 |
| 7 | P2 | CC1：覆盖率判定改为语义化（LLM 判定或提升命中阈值+需求结构解析） | 覆盖率反映真实实现 | coverage_checker.py:44-52 | 新增 |
| 8 | P3 | IG2：generated_files 统一结构（reused 项补 size 等字段） | 下游消费稳定 | incremental_generate.py:44-49 | 新增 |
| 9 | P3 | IG3：stash push 失败告警/中止 | 失败可回滚保证 | incremental_generate.py:63 | 新增 |
| 10 | P3 | FE1：缺 content 文件记录 warning 而非静默跳过 | 提取不静默丢文件 | feature_extractor.py:20 | 新增 |

## 6. 演化方向关联

- **两套链路收敛**（最大演化项）：传统路径（traditional_generate）与 spec_first 路径在验证/修复/缓存/沙箱各环节大量同构——演化蓝图 §1「编排层职责归位」：收敛为统一生成管线，传统模式作为无 spec 的降级配置而非独立实现
- **ERR 链**：traditional_generate.py:297 是 ReAct 自动修复唯一调用方（已被 ERR1/ERR2 确认失效）——修复 RA2+RE1 后传统链路动态测试闭环恢复
- **EV2/CC1** → 「验证语义化」主线（Evaluator-optimizer 条件回边方向）：LLM 判定替代关键词/评分启发式
- **EV1/TG1** → 客户端收敛主线（LC1/LCL1 同源）：所有 LLM 调用统一过模型配置+信号量+成本
