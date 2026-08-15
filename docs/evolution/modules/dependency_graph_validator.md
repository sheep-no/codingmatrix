# DependencyGraphValidator 深扫（dependency_graph_validator.py，344 行）

> 第九十五轮推演 | 2026-08-15 | 定位：通过 LLM 验证依赖图正确性的验证器（功能重复/错误路径/缺失依赖/文件类型/框架一致性/接口匹配），spec-first 链活跃消费

## 1. 模块定位

通过 LLM 审查 `DependencyGraph` 的节点/边/文件计划/框架信息，检测功能重复、错误路径、缺失依赖、文件类型错误、同名文件、框架不一致、接口不匹配 7 类问题。**活跃生产模块**，消费方 1 处（3 个调用点，全部在 spec_first_generate.py）：

- `spec_first_generate.py:228-253`：**full 模式**——首次生成时全图验证，最多 `MAX_VALIDATION_RETRIES+1 = 3` 次尝试，失败时 `format_validation_feedback` 反馈架构师重新设计 + 重建依赖图（:241-245），重试耗尽仅 warning「继续生成」（:247-248）
- `spec_first_generate.py:277-282`：**incremental 模式**——增量新增文件验证，失败只 logger.warning 继续
- `spec_first_generate.py:2292-2303`：**refactor 模式**——重构拆分后验证，失败只 logger.warning 继续

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `spec_first_generate.py:228-253` | full 验证 + 最多 3 次重试 + 反馈架构师 |
| 被消费 | `spec_first_generate.py:277-282` | incremental 验证（失败仅警告） |
| 被消费 | `spec_first_generate.py:2292-2303` | refactor 验证（失败仅警告） |
| 依赖 | `dependency_graph.py`（DependencyGraph.nodes/adjacency/reverse_adjacency） | 验证对象：节点/边 |
| 未消费 | 无（模块内全部方法均被消费） | |
| 测试 | **零测试覆盖**（tests/ 无任何 DependencyGraphValidator 用例） | |

## 2. 深扫发现

### P2 项

- **DGV1 [P2] LLM 验证失败全部兜底 passed=True（实测三路径）**——验证门禁在 LLM 异常/垃圾响应时静默放行，且 passed=True 使下游无法区分「真通过」与「验证失效」：
  1. **非 JSON 响应**：`_parse_response` 解析失败返回 `ValidationResult(passed=True)`（:307/:310）——实测 `validate(dg)` 返回非 JSON 字符串 → `passed=True`；
  2. **`issues: null` 崩溃被吞**：LLM 返回 `{"passed": false, "issues": null}` → :313 `for issue_data in data.get("issues", [])` 迭代 None 抛 TypeError → 被 validate 外层 `except Exception`（:92-102）吞掉 → 返回 passed=True——**LLM 已判定失败（passed=false）的响应因解析崩溃反而变通过**（实测确认）；
  3. **passed 缺失/顶层标量**：:323 `passed=data.get("passed", True)` 默认 True + `null` 顶层标量（JP1 家族）崩溃后兜底 True——实测 `{"issues":[...]}` 无 passed 键 → passed=True、`null` → passed=True。
  spec_first_generate:231 `if validation_result.passed: break` 直接跳过重试——**验证失效时连重试都不触发**，门禁整体形同虚设。:94 注释「验证失败不阻塞生成」是有意设计，但 passed=True 使「验证失效」与「验证通过」在下游不可区分，代价是静默跳过修复循环。
- **DGV2 [P2] 缺失依赖边被 `_build_context` 过滤（实测，检测目标与数据矛盾）**——`_build_context` 只收录 `source in nodes and target in nodes` 的边（:125-126），**指向不存在节点的边全部被过滤**；而系统 prompt 明确要求检测「缺失依赖：边的目标节点不在节点列表中」（:206）。实测手动构造 `a.py -> nonexistent.py` 后 `_build_context` 的 edges 只剩 `b.py -> a.py`、total_edges=1——**缺失依赖检测需要的证据在数据构建阶段已被抹掉**，LLM 永远看不到缺失依赖的边。检测能力与输入数据自相矛盾。
- **DGV3 [P2] incremental/refactor 模式验证失败零反馈零修复（全库确认）**——full 模式失败会反馈架构师重新设计（:241-245），但 incremental（:277-282）与 refactor（:2299-2303）验证失败只 `logger.warning` 后**继续生成，无修复循环、无反馈、无重试**——依赖图验证门禁在增量/重构两条副路径形同虚设，功能重复/接口不匹配等问题在增量修改场景（IM 增量链）完全不拦截。

### P3 项

- **DGV4 [P3] `error_count`/`warning_count` 白名单外 issue_type 计数丢失（实测）**——`ValidationResult.__post_init__`（:40-42）只认 4 个 error 类型 + 3 个 warning 类型，LLM 输出白名单外类型（含 validate 自身构造的 `validation_error`、LLM 自由发挥的 `unknown` 等）时 error_count/warning_count 恒 0——实测 `{"issue_type": "some_made_up"}` → error=0/warning=0，而 issues 列表仍保留该条。计数统计与 issues 内容不一致（下游若按计数判断严重度会失真）。
- **DGV5 [P3] 验证结果不落上下文/追踪（全库确认）**——spec_first_generate 三处消费验证结果后只 logger，**不写入 ctx.set_metric、不记录到 orchestration_progress**——依赖图验证的成败、issue 明细、重试次数在生成事件流/审计中无任何痕迹，验证门禁是否生效、多少次才通过完全不可观测（OP 家族：进度/指标通道缺此项）。
- **DGV6 [P3] `_build_prompt` 在架构缺失时零上下文空验证（实测推断）**——`_build_context` 依赖 `architecture.get("file_plan")`（:132），architecture=None 时 nodes/edges/file_plan_descriptions 全空，full prompt 只剩「文件总数: 0、依赖关系数: 0」两行——空依赖图验证 LLM 只能返回 passed=true，冷启动空图验证无意义但会消耗一次 LLM 调用。incremental 模式 `new_files` 传空时同理会构造空验证（:159 `if scope=="incremental" and new_files` 有保护，但 full 无）。

## 3. 演化方向

依赖图验证是 spec-first 链「架构设计 → 文件计划」的质量门禁，但**门禁的失效路径（DGV1）与数据矛盾（DGV2）叠加使其拦截能力大幅退化**：
- **失效语义（DGV1）**：LLM 验证失败（解析失败/异常/垃圾响应）全部转 passed=True 且下游不可区分——修复方向：ValidationResult 增加「验证是否成功执行」字段（或 passed 三态：pass/fail/inconclusive），inconclusive 时 spec_first 应重试而非 break。这是「存在≠正确」在验证器自身的实例——**验证器自己也分不清「验证通过」和「验证没做成」**。
- **数据矛盾（DGV2）**：缺失依赖检测目标被数据构建过滤——修复方向：edges 收集时保留指向不存在节点的边（这正是缺失依赖的定义），或单独收集 orphan_targets 传给 LLM。
- **门禁强度分裂（DGV3）**：full 有重试反馈、incremental/refactor 无——增量修改链（IM 增量驱动）是当前重点，增量验证形同虚设使功能重复/接口不匹配在增量场景不拦截。修复方向：incremental/refactor 至少复用 full 的反馈机制（反馈架构师重新拆分）。

**修复优先级**：DGV2（缺失依赖检测数据矛盾，结构性缺陷）> DGV1（验证失效静默通过，拦截失效）> DGV3（增量/重构门禁空缺）> DGV5（可观测性）> DGV4/DGV6（计数与空验证）。

## 4. 主线关联

- **「存在≠正确」主线**：DGV1 是验证器自身的失效语义问题——**验证链末端（LLM 输出解析）把「没验证成」当「验证通过」**，与 JP1（顶层标量穿透）、TR1（无测试=通过）、OP1（成本恒零）同族，且直接位于 AI1/AI2（架构检查门禁失效）之后的**第二道门禁**，两道门禁的失效路径都指向 passed 恒真。
- **检测端失真家族**：DGV2 与 CV2/CV3（CrossValidator 假阳性/假阴性）、LD1（漏检）同族——验证器的输入数据准备阶段就已丢失检测目标。
- **LLM 输出契约**：DGV1 的 issues:null/顶层标量直接命中 JP1 家族——验证器依赖 LLM 严格 JSON 输出但无类型保护（AJP1 同类模式，验证器自身缺少 safe 解析）。
- **可观测性主线**：DGV5 与 OP1/OP2（进度/成本通道缺陷）同族——验证门禁状态在事件流中零记录。

## 5. 测试状态

**零测试覆盖**——tests/ 无任何 DependencyGraphValidator 用例。DGV1/DGV2/DGV4 全部实测可复现但无任何用例保护。spec_first 链的依赖图验证门禁（full 重试 + incremental + refactor 三模式）端到端无回归保护，LLM 响应解析的健壮性（非 JSON/null/标量/缺键）零用例。
