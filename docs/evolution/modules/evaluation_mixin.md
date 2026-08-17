# EvaluationMixin + GenerationMixin + IncrementalGenerateMixin 深扫（evaluate_mixin.py 351 行 + mixin.py 146 行 + incremental_generate.py 85 行）

> 第一百零五轮推演 | 2026-08-17 | 定位：orchestrator_generation 子包收尾——评价模式（EvaluationMixin）、生成组合层（GenerationMixin）、会话增量生成（IncrementalGenerateMixin）

## 1. 模块定位

三个模块是 `GenerationMixin`（mixin.py:29-36）组合的组成部分，供 `OrchestratorAgent` 继承：

- `evaluate_mixin.py`（351 行）：评价模式（`evaluation_only=True` 时 mixin.py:116-117 走 `evaluate`）——复杂度分析 → 需求联想 → 架构设计（评价架构师）→ 需求/架构/风险三维评价 → 综合评级，不生成文件
- `mixin.py`（146 行）：`GenerationMixin` 组合层——`_initialize_components` 全量初始化（complexity/模型路由/四角色/验证器/错误恢复/API 契约/补丁器）+ `generate()` 分发（evaluation_only/spec_first/traditional）+ 覆盖率与功能提取适配
- `incremental_generate.py`（85 行）：`IncrementalGenerateMixin._handle_incremental_generation`——会话增量生成（detect_incremental_changes → 复用未变文件 → git stash 备份 → 并发生成 → 失败回滚）

**活跃模块**，调用链：

- `mixin.py:116-123`：`generate()` 三分发（评价/规范优先/传统），传统链路已建档（TG 详档）
- `evaluate_mixin.py:21`：`evaluate` 评价模式（evaluation_only 配置触发）
- `incremental_generate.py:13`：`_handle_incremental_generation`（traditional_generate.py:192 增量分支调用，TG 详档消费方）
- 依赖：`architect.py:537-550` 架构返回键集合（`has_backend`/`has_database` **不在此集合**）、`complexity.py`（CMP 详档）、`orchestrator_files.py:156` `_generate_files_small_project`、`orchestrator_progress.py`

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 上游 | `orchestrator.py` OrchestratorAgent | 宿主（_report_progress/architect/session_manager 等） |
| 上游 | `architect.py:537-550` | `design_architecture` 返回键集合（缺 has_backend/has_database） |
| 上游 | `complexity.py` ComplexityAnalyzer | `self.complexity.has_backend` 等真实来源（CMP 详档） |
| 上游 | `orchestrator_requirements/mixin.py:30` | 联想调用（OA 详档） |
| 下游 | `orchestrator_files.py:156/:215` | 小项目/分层文件生成（增量退化时） |
| 依赖 | `session_manager.py` | `detect_incremental_changes`（SM 详档：恒判 changed） |
| 测试 | `tests/unit/test_evaluate_mode.py` | **手工注入 has_backend/has_database 键固化错误预期** |

## 2. 深扫发现

### P2 项

- **EV1 [P2] `_evaluate_risks` 的 `architecture.get("has_backend"/"has_database")` 恒 None——两个 high 风险项恒死（实测）**——evaluate_mixin.py:260/:267 用 `architecture.get("has_backend")`/`get("has_database")` 判断后端/数据库项目是否缺 API 规范/Schema，但 `design_architecture` 返回键集合为 `project_type/tech_stack/language/frontend_language/backend_language/all_languages/file_plan/project_spec/dependencies/risks`（architect.py:537-550），**无 has_backend/has_database 键**（真实来源是 `self.complexity.has_backend`）→ 恒 None → `missing_api`/`missing_db_schema` 两个 high 风险项永不触发。实测：fullstack 架构 + 无 api_spec → 风险列表空、overall_severity=low。
- **EV2 [P2] 架构评价解析恒降级 fallback——架构评分恒 0（实测）**——`_parse_evaluation_json`（:339）校验 `parsed.get("score") or parsed.get("completeness")`，但架构 prompt（:191-222）返回 `architecture_quality/tech_stack_fitness/requirement_coverage/security_assessment/performance_assessment` 等键，**无顶层 score 也无 completeness** → 恒走 `_fallback_evaluation`（:346-351 返回 `{"score": 0, "error": ...}`）；且 `_build_overall_assessment`（:305）`architecture_evaluation.get("architecture_quality", {}).get("score", 0)`——fallback 返回体无 architecture_quality 键 → arch_score 恒 0。实测：合法架构 JSON → 返回 `{'score': 0, 'error': 'architecture 评价降级'}`；需求评价正常（completeness 键）。**整体评分只反映需求评价（req_score//2 再扣风险），架构评价完全失效**。
- **EV3 [P2] evaluate 模式 `models_used` 无 None 防护（全库确认）**——evaluate_mixin.py:109-110 `self.model_assignment.architect_model` 无 `if self.model_assignment` 防护（对比 :43 同处有 `if ... else DEFAULT_ARCHITECT_MODEL` 防护），`use_dynamic_topology=False` 时 model_assignment=None（:40-41）→ `evaluate` 末尾 AttributeError——评价模式在关闭动态拓扑的配置路径崩溃。

### P3 项

- **EV4 [P3] `_parse_evaluation_json` 贪婪 `\{[\s\S]*\}` 跨块**——:336（MAR5/EC3/PM1/OA3 家族），多 JSON 块 LLM 输出跨块匹配失败走 fallback。
- **EV5 [P3] `_evaluate_risks` 硬编码阈值**——:246 `len(file_plan) > 50` high、:253 `len(tech_stack) > 6` medium，无配置来源；severity 判定粗糙（complexity 恒 high）。
- **EV6 [P3] 评价模式最多 6 次 LLM 调用且无超时预算**——`evaluate` 直接 await：联想 layer3 双模型最多 3 次（OA 详档）+ 需求评价 + 架构评价 + `design_architecture` 1 次；联想有 `TIME_BUDGET_SECONDS`（mixin.py:40-47 wait_for）但两个 `_evaluate_*` 与 `design_architecture` 均无超时包裹——评价链路无整体预算。
- **EV7 [P3] 需求/架构评价 fallback 同形 score:0 → 综合评分静默低分**——EV2 使架构评价恒 fallback 后，`_build_overall_assessment` 静默给出低分与降级评级（grade D）无降级标记透出（成功态谎报家族，MAR8 相关）。
- **IG1 [P3] 增量失败回滚后 `generated_files` 仍报告成功（全库确认）**——incremental_generate.py:78 在 `has_failure` 前已 append 成功项，:81-83 失败时 `_git_stash_pop` 回滚全部受影响文件（含已成功修改的），但 `self.generated_files` 中的成功项不回撤 → 最终报告与磁盘状态不一致（报告 success 的文件实际已还原）。
- **GM1 [P3] `_initialize_components` 每次生成全量重建组件**——mixin.py:39-99 每次 `generate` 都 new `ComplexityAnalyzer`/`LayeredModelRouter`/四角色/`CodeValidator`/`ErrorRecoveryLoop`/`APIContractChecker`/补丁器 + `_init_mcp_tools` 每次重连 MCP（:101-112 异常静默跳过），组件无缓存复用（评价模式 evaluate_mixin.py:28-52 同样各自新建）。

## 3. 演化方向

评价模式是「生成前可行性评估」入口（evaluation_only 配置触发），当前三维评价中**架构维度整体失效**（EV2 解析键不匹配）且风险规则半数恒死（EV1）：
- **键名对齐（EV2，最高优先）**：`_parse_evaluation_json` 校验改为按 eval_type 分派（requirement 认 completeness、architecture 认 architecture_quality 等六键任一存在），或架构 prompt 增加顶层 score 聚合字段——一处改动即恢复架构评价与综合评分的架构维度。
- **风险规则修复（EV1）**：`:260/:267` 改从 `self.complexity.has_backend`/`has_database` 读取（真实来源），或架构 dict 补键——与测试夹具（test_evaluate_mode.py 手工注入）同步修正。
- **防护补齐（EV3）**：`models_used` 与 `:43` 同款 `if self.model_assignment else` 防护。
- **评价超时（EV6）**：evaluate 整体加 `asyncio.wait_for`（参考联想 TIME_BUDGET）。
- **增量一致性（IG1）**：失败回滚时同步清除已 append 的成功项，或改为「成功后 drop、失败后 pop」且回滚项标记 reused=False。

**修复优先级**：EV2（架构评价恒 0）> EV1（风险恒死）> EV3（配置路径崩溃）> EV6 > IG1 > EV7 > EV4 > EV5 > GM1。

## 4. 主线关联

- **「测试固化错误预期」家族第 N 例**：test_evaluate_mode.py:74-149 的 `_evaluate_risks` 用例在 architecture dict **手工注入 `has_backend`/`has_database` 键**（:78/:92/:104）——真实架构返回结构（architect.py:537-550）无此二键，测试让恒死的风险规则「全绿」，与 OA1（FakeMixin 手工补齐宿主契约）、DGV4 同族——**测试夹具补的恰好是生产缺失的契约/键**。
- **「LLM 契约不匹配」主线**：EV2 与 OA1（宿主契约缺失）、CR1（两套 LLM 契约）、DGV1（验证键缺失兜底 passed）同族——prompt 输出键与解析校验键两处各自演化产生漂移。
- **「存在≠正确」/「成功态谎报」家族**：EV7（降级静默低分）、IG1（回滚后仍报告成功）延续 TR1/MAR8 主线。
- **评价模式是「能力未接线」的反向实例**：评价模式已接线（evaluation_only 配置）但三维中两维失真（架构评分恒 0 + 风险规则恒死）——接线 ≠ 正确（TG 详档同主线）。

## 5. 测试状态

**测试覆盖风险规则但与生产数据流脱节**——test_evaluate_mode.py（229 行）覆盖 `_parse_evaluation_json`（正常/非法）、`_fallback_evaluation`、`_evaluate_risks` 六场景（文件数/API/Schema/魔鬼代言人/无风险/技术多样性）、overall assessment 等，**但**：
1. `_evaluate_risks` 用例手工注入 has_backend/has_database 键（:78/:92/:104）——生产架构 dict 无此键，EV1 恒死却测试全绿（TR2 家族）；
2. `_parse_evaluation_json` 用例只测 requirement 语义（completeness 键，:55-60），**架构语义（architecture_quality 键）零用例**——EV2 实测可复现却无保护；
3. `evaluate()` 主流程与 `models_used`（EV3）、增量生成 `_handle_incremental_generation`（IG1）零测试。
