# TaskPlanner 深扫（task_planner.py，180 行）

> 第八十三轮推演 | 2026-08-13 | 定位：任务规划器——将复杂任务拆解为可执行步骤；从 multi_model_agent 拆分而来（docstring :4），支持盲拆与 ReAct 探索两种模式

## 1. 模块定位

TaskPlanner.decompose 是 multi_model_agent 编排的步骤产出端：LLM 将任务分解为步骤列表（file_operation/code_generation/tool_call/ai_call），解析失败/schema 错误/异常时降级为 ai_call 步骤。_explore_project 用 ReActEngine simple 模式在拆解前了解项目结构。唯一生产消费方 multi_model_agent（:70 实例化 / :191 decompose）。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `multi_model_agent.py:70/:191` | 唯一生产实例化 + decompose 调用（production active） |
| 依赖 | `file_contract.py:126-141` | TaskStep 模型 + _degrade_step 降级构造 |
| 依赖 | `react_engine.py:160-167` | _explore_project 的 ReActEngine simple 模式 |
| 依赖 | `app.utils.call_llm`（:14/:98/:140） | 直连顶层 LLM 调用（不走 LLMClient） |
| 测试 | tests/unit/test_task_planner.py（212 行） | 初始化 2 + decompose 6 + explore 2 + degrade 1 |

## 2. 深扫发现

### P2 项

- **TP1 decompose 产出面与 execute 执行面错配（FCT6 触发端）**——decompose prompt（:84-88）引导 LLM 产出 4 种步骤类型，但 agent_executor.execute 只实现 file_operation/ai_call 2 种（file_contract.md FCT6 已证 code_generation/tool_call 落「未知步骤类型」:104）——**正常路径下 LLM 按 prompt 产出 code_generation/tool_call 步骤即执行失败**；test_decompose_success（test_task_planner.py:48-51）的 mock 响应恰好含 code_generation 步骤并断言 decompose 成功，掩盖了执行端无法处理的错配。
- **TP2 降级计划与 review 门禁冲突（降级路径双死）**——decompose 三处降级分支（:112/:122/:125）产出 `degraded=True` 的 ai_call 单步骤计划；multi_model_agent:209 review_plan 审查该计划——若 LLM 审查拒绝（降级计划内容单薄容易判定不合理）→ 返回「计划审查未通过」（:210-217）；若通过 → execute 对 ai_call 返回 pending 空转（AE1/FCT1）。**降级计划要么被 review 卡住（成功路径也失败），要么空转报成功**——两条路都没有「真正降级执行任务」。
- **TP3 默认模型硬编码 + 直连 call_llm（LCL1 家族）**——`model_key: str = "deepseek-r1-qwen3-8b"`（:30）硬编码（测试 test_init_default 断言此值 :27）；decompose（:98）与 _explore_project 的 call_llm_fn（:140）都直连 `app.utils.call_llm`，**不走 LLMClient 信号量/成本追踪/统一熔断**（LCL1 收敛范围）；_explore_project temperature=0.3/max_tokens=2048 硬编码。

### P3 项

- **TP4 `_explore_project` 声称「只读工具」但含 run_command（AE2 同源）**——:151 docstring「只用只读工具」，:152-155 白名单 `("list_files", "read_file", "read_symbols", "summarize_file", "run_command")`——run_command 前缀白名单（tools.py:630-648）含 `pip install`/`echo`/`git commit` 等写操作，探索路径工具面含写命令。
- **TP5 探索轮数声明与实现不一致**——docstring「只做 2 轮探索」（:135），ReActEngine 实例化 `max_rounds=3`（:164）——轮数比声明多 50%，token 消耗与注释不符（TS4 注释与实现不符家族）。
- **TP7 空步骤列表报成功**——LLM 返回 `[]`（:114-115 空列表合法通过）→ steps=[] → review 通过 → execute 循环 0 次 → `success: True`（multi_model_agent:245），**0 步骤完成报成功**；test_decompose_with_context（:127）把空列表当正常结果断言 isinstance list——测试固化空计划（「存在≠正确」家族，TS1/TR1 同族）。
- **TP9 `degraded` 字段的消费语义是「强制拒绝降级计划」（已接线，非死声明）**——file_contract.py:131 注释「供 review_plan 检测」**准确**：ai_reviewer.review_plan（:189-198）`has_degraded = any(s.get("degraded") for s in plan)`，含降级步骤且 LLM 输出 approved 或 risk_level != high 时强制改为 `approved=False, risk_level=high`——**任何含降级步骤的计划最终都 approved=False**（LLM 判 high 保持拒绝，判非 high 强制拒绝）——降级步骤在 enable_review=True 下永不执行，任务必定「计划审查未通过」失败（ARV1 确认，TP2 更新）。

## 3. 演化方向

### 3.1 步骤类型契约统一（TP1 与 FCT6/AE1 联动）

decompose prompt 的步骤类型应与 execute 实现面收敛：要么 execute 补 code_generation/tool_call 实现（LLM 子任务执行），要么 prompt 只引导 file_operation/ai_call 两种可执行类型。当前「prompt 引导 4 种 → 2 种执行失败」是 §5.6 支柱 1（产物协议）的直接反例——规划产物协议与执行器契约必须同源定义。

### 3.2 降级路径语义修复（TP2 与 FCT1/ARV1 联动）

降级步骤应真正执行任务（execute 对 ai_call 调 LLM 处理 task 参数），或降级时如实上报失败而非静默——当前降级路径行为取决于 enable_review：enable_review=True（默认）时降级计划被 review_plan 强制拒绝（ARV1）→ 任务「计划审查未通过」失败；enable_review=False 时降级步骤 execute 空转 pending → success:True 假成功（AE1/FCT1）。两种配置下降级执行都没真正发生——降级语义失真需 execute 真执行 + review 门禁联动（review_plan 识别 degraded 计划放行或直接跳过 review）统一修复。

### 3.3 模型调用收敛（TP3 归入 LCL1）

TaskPlanner 直连 call_llm 是 LCL1 收敛的 26+ 处之一（decompose + explore 两处调用点），应改走 LLMClient 统一信号量/成本/熔断。

## 4. 主线关联

- **步骤契约断裂链**：TP1（产出 4 种）→ FCT6（模型声明 4 种）→ AE1（execute 只实现 2 种且 ai_call 空转）——规划/类型/执行三段契约全不一致，是「声明与实现面不符」主线最完整的纵向链条
- **降级语义失真**：TP2（降级被 review 卡/空转）与 CD2（超时静默丢弃）、FCT1（降级 ai_call 空转）同族——「降级」承诺从未兑现为真实降级执行
- **「存在≠正确」再例**：TP7（空计划报成功）与 TS1（超时 success=True）、TR1（无测试文件=通过）同族——success 语义与真实产物脱节

## 5. 测试状态

test_task_planner.py 覆盖较全（初始化/成功/单 dict 包裹/解析失败降级/异常降级/context/依赖提示/schema 失败/explore 两分支/degrade 格式），但：test_decompose_success 的 mock 响应含 code_generation 步骤（掩盖 TP1 执行端错配）；test_decompose_with_context 把空列表当正常（固化 TP7）；降级→review→execute 的跨模块串联零测试（TP2/ARV1 不被暴露）；explore 的 run_command 含写工具（TP4）无测试。
