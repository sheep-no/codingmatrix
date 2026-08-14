# AIReviewer 深扫（ai_reviewer.py，223 行）

> 第八十五轮推演 | 2026-08-13 | 定位：AI 审查器——从 multi_model_agent 拆分而来（docstring :4），审查执行计划（review_plan）/代码（review_code）/文件操作（review_file_operation），产出 ReviewResult

## 1. 模块定位

AIReviewer 承载 multi_model_agent 的审查门禁：review_plan 审查执行计划（生产活跃，multi_model_agent:209 调用）；review_code/review_file_operation 审查代码与文件操作（生产零消费方）。review_plan 内含 degraded 检测（:189-198）——**本模块是本轮主线的重要修正点**：上一轮（v1.85 TaskPlanner 详档 TP9）误判 degraded 字段为死声明，实际 review_plan 明确消费它且消费语义是「强制拒绝降级计划」。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `multi_model_agent.py:71/:209` | 唯一生产实例化 + review_plan 调用（production active） |
| 依赖 | `file_contract.py:118-123/:26-116` | ReviewResult 模型 + FileContract（review_file_operation 用 validate_path/validate_content） |
| 依赖 | `app.utils.call_llm`（:13/:62/:168） | 直连顶层 LLM 调用（不走 LLMClient） |
| 依赖 | `json_parser.py`（:14/:73/:179） | safe_parse_json 统一解析 |
| 测试 | tests/unit/test_review_result_parsing.py | review_plan 解析 5 处直接调用（生产未接线的 review_code 却有测试覆盖，CR3 已确认） |

## 2. 深扫发现

### P2 项

- **ARV1 降级计划被 review_plan 强制拒绝——降级执行承诺完全未兑现（TP2 确证）**——:189-198 `has_degraded = any(s.get("degraded") for s in plan)`，含降级步骤且 LLM 输出 `approved or risk_level != "high"` 时强制改为 `approved=False, risk_level=high`——**任何含降级步骤的计划最终都 approved=False**（LLM 判 high 保持拒绝、判非 high 强制拒绝）。串联 multi_model_agent:210-217：降级计划 → review 拒绝 → 返回「计划审查未通过」**任务必定失败**。降级路径在 enable_review=True（默认）下**永不真正降级执行**——「降级执行」承诺是「必定拒绝」；enable_review=False 时降级步骤 execute 空转 pending → success:True 假成功（AE1/FCT1）。两种配置下降级执行都没发生（TP2 更新：不是「卡住或空转」双死，而是**按配置二选一的确定性双死**）。
- **ARV2 review_code / review_file_operation 生产零消费方（孤儿方法）**——multi_model_agent 只调 review_plan（:209）；review_code（:31-103，审查代码安全/正确性/性能）与 review_file_operation（:105-142，路径+内容安全验证）**全库零生产调用方**——「验证执行结果的质量和安全性」（docstring :23）的代码审查能力从未接线；review_file_operation 是 FileContract.validate_content 的**唯一生产消费方**（FCT2 确认），该消费方本身孤儿使 validate_content 安全拦截死链坐实。
- **ARV3 降级检测先于 LLM 审查则 LLM 调用纯浪费**——既然 has_degraded（:189）检测后强制拒绝，而降级计划的 LLM 审查结果会被无条件覆盖（:193），**对降级计划调用一次 LLM 审查纯属成本浪费**——应先查 has_degraded 直接拒绝，省一次 LLM 调用（每降级任务一次无意义 LLM 调用）。

### P3 项

- **ARV4 降级检测逻辑不一致：LLM 判 high 时无「需人工审查」标记**——:193 条件 `result.approved or result.risk_level != "high"` 触发才加标记「计划中包含降级步骤，需人工审查」；若 LLM 恰好输出 `approved=False + risk_level=high`（降级单薄计划很易被判定高风险），条件不触发直接返回 LLM 结果——**issues 里没有「需人工审查」提示**，同是拒绝但语义标记取决于 LLM 偶然输出。
- **ARV5 review_code 的 except 面过宽且降级语义**——:97-103 任意 Exception（含网络/超时/内部错误）转 `approved=False, risk_level=medium` 拒绝——**审查失败=代码被拒**，而 review_plan 的同款 except（:217-223）转 risk_level=high——两方法错误降级严重度不一致（medium vs high），且「审查过程出错」与「代码真有安全问题」不可区分（用户看到同样的拒绝）。
- **ARV6 prompt 无 degraded 字段说明，LLM 盲审降级计划**——review_plan prompt（:154-165）只让 LLM 审查「计划是否合理安全」，不告知 degraded 字段语义——降级计划的审查依赖代码层事后强制，LLM 审查结果本就无意义（ARV3 相关）。

## 3. 演化方向

### 3.1 降级语义统一修复（ARV1 与 AE1/FCT1/TP2 联动）

降级路径三选一：① execute 真执行 ai_call（LLM 处理 task）；② 降级时跳过 review 直接失败并如实上报「降级执行不可用」；③ 降级时跳过 review 直接真正执行降级任务（如任务直接交 LLM 无步骤执行）。当前「enable_review=True 必定拒绝 / False 空转报成功」的配置相关双死必须收敛为一种有意义的降级行为。ARV3（先查 degraded 再决定是否调 LLM）是此方向的第一步低成本修复。

### 3.2 孤儿方法接线或收敛（ARV2）

review_code 是唯一的「代码质量审查」生产能力但零调用——multi_model_agent 审查的是执行计划而非产出代码；若审查门禁延伸到代码产物，review_code 是现成实现（§5.6 支柱 2 验证端）。review_file_operation 的 validate_content 随 FCT2/AE2 的 FileContract 下沉一并处理。

## 4. 主线关联

- **自我纠错记录（重要）**：v1.85 TaskPlanner 详档 TP9 曾断言 degraded「死声明」（review_plan 无处理）——**本轮实测修正**：ai_reviewer:189-198 明确消费 degraded，消费语义为「强制拒绝降级计划」。TP9 从「死声明」改为「已接线但语义为强制拒绝」，修正了「声明与实现面不符」主线的误归类——degraded 字段反而是少见的「声明+消费都实现」的例子，其问题在消费语义（拒绝而非降级）。
- **降级语义失真家族**：ARV1 使降级失真闭环完整——CD2（决策超时静默丢弃）+ FCT1（降级 ai_call 空转）+ ARV1（降级计划强制拒绝）——「降级」承诺在决策/步骤/审查三个维度都未兑现为真实降级。
- **LCL1 家族**：ARV3（降级任务无意义 LLM 调用）+ 本模块两处直连 call_llm——review 侧与 TaskPlanner/AIReviewer 全链路直连 app.utils.call_llm。

## 5. 测试状态

tests/unit/test_review_result_parsing.py 覆盖 review_plan 解析路径（5 处），但：degraded 强制拒绝（:189-198）的 has_degraded 分支零测试——TP2/ARV1 的「降级计划必定拒绝」未被任何测试捕获；review_code/review_file_operation 零生产测试（生产也零调用）；ARV4 的 LLM 输出相关性、ARV3 的浪费调用均无验证。
