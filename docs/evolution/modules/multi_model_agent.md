# MultiModelAgent 深扫（multi_model_agent.py，251 行）

> 第八十四轮推演 | 2026-08-13 | 定位：多模型 Agent 编排中枢——整合路由（Router）、规划（Planner）、执行（Executor）、审查（Reviewer）、文件契约（FileContract），v5.14 拆分后保留编排主逻辑 + 向后兼容 re-export

## 1. 模块定位

MultiModelAgent.process 是编排主入口：任务类型路由 → 代码生成委托 OrchestratorAgent / 分析任务走 AgentExecutor.execute_analysis / 其余走 planner.decompose → review_plan → 逐步骤 execute。FileContract 前置验证在此层（:225-236）。是 TP/AE/FCT 三大模块的编排串联端，也是近期多轮（AE1/FCT1/TP2）发现的空转链条最终报喜者。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | models.py:259/:337 | route_dynamic / route_by_content |
| 依赖 | task_planner.py（:70/:191） | planner.decompose 步骤产出 |
| 依赖 | agent_executor.py（:72/:158/:238） | execute_analysis / execute 执行 |
| 依赖 | ai_reviewer.py（:71/:209） | review_plan 计划审查 |
| 依赖 | file_contract.py（:230-234） | FileContract 前置验证 |
| 依赖 | dynamic_model_router（:199-207） | reviewer 模型 5×5 切换 |
| 消费方 | **无生产消费方（顶层 Agent 编排层，由会话/服务层调用）** | app/ 内无 import MultiModelAgent 的生产代码（经 re-export 对外） |

## 2. 深扫发现

### P2 项

- **MMA1 `if task_type is None` 双重路由死代码（:178-180 恒不可达）**——:123-125 已保证 task_type 非 None（传入值或 route_by_content 赋值），:178-180 重复 `if task_type is None: task_type = self.router.route_by_content(...)` **恒假死代码**——route_by_content 调用点与 emit("task_routed") 各重复一份（:124-125 vs :179-180），重构残留。
- **MMA2 `success: True` 恒定（AE1/FCT1 编排端闭环确认）**——:244-251 步骤执行路径返回 `success: True` **从不检查 results 内容**：全部步骤 pending（ai_call 空转）/失败/降级都不影响 success——与 AE1（execute pending）+ FCT1（降级 ai_call 空转）+ TP2（降级被 review 卡/空转）组成完整闭环：**编排端是空转链条的最终报喜者**，前端/会话层拿到 success=True 即视为任务成功。
- **MMA3 reviewer 模型切换每任务重查 + 实例竞态 + review 直连 call_llm**——:199-207 每次 process 都 `get_dynamic_router()` + `get_assignment_with_learning()` + `ModelRegistry.get`（每任务一次动态路由查询，与 DMR 学习数据零写入矛盾——get_assignment 恒静态）；切换写 `self.reviewer.model`（实例共享），并发多任务互相覆盖模型（单例竞态 MCP1 家族）；AIReviewer.review_plan prompt 直连 `app.utils.call_llm`（ai_reviewer.py:13/:63）不走 LLMClient（LCL1 家族）。

### P3 项

- **MMA4 `emit` 流式回调失败静默**——:118-119 except 只 `logger.warning`，无降级/重试/上报——stream_callback 在流式场景是**唯一输出通道**，故障时用户零感知（TT5 家族）。
- **MMA5 FileContract 前置验证覆盖不全 + 与 AE2 分离**——:225-236 只对 `type == "file_operation"` 步骤验证，code_generation/tool_call 步骤无契约检查；只调 `validate_path` 不调 `validate_content`（FCT2 编排端确认）；且此验证与 execute_analysis 路径（:158，AE2 绕 FileContract）**两套校验并存**——编排层校验与工具层执行各自为政。
- **MMA6 `_get_semaphore` 获取失败静默降级无并发控制**——:85-90 except 返回 None → :173-174 `if sem is None: return await coro_factory(...)` 直接执行——全局 LLM 信号量获取失败静默退化为无并发限制（LC2 家族，docstring「所有 LLM 调用统一走全局信号量」:54 在失败时失效且无告警）。
- **MMA7 complexity 参数被计算展示但未参与路由（5×5 矩阵复杂度维度虚设）**——:121 effective_complexity 计算 + :188 logger 记录；但 route_dynamic 签名（models.py:259 `route_dynamic(cls, task_type, prefer_fast=False)`）**无 complexity 参数**——:156/:183 调用只传 task_type——docstring「接入 DynamicModelRouter 5×5 矩阵（按角色 + 复杂度路由）」（:53）的复杂度维度从未传递，复杂度只用于日志展示（SM2/参数虚设家族）。

## 3. 演化方向

### 3.1 编排端 success 语义收紧（MMA2 与 AE1/FCT1 联动）

步骤路径的 success 应检查 results：`all(r.get("status") != "pending" for r in results)` + 至少 1 个成功步骤。这是空转链条的**最后一个关卡**——修复 AE1（execute 真执行）+ FCT1（降级语义）+ TP2（review 联动）前，即使 MMA2 收紧也只是把「假成功」变「真失败」，仍不修复任务；三者需同批修复。§5.6 支柱 1（产物协议）要求 success 与产物真实性绑定。

### 3.2 编排层重构（MMA1/MMA3/MMA7）

死代码清理（:178-180）；reviewer 模型切换应做实例级缓存或依赖注入而非每任务重查 + 共享写（MCP1 修复方向）；5×5 矩阵复杂度维度要么传给 route_dynamic 要么从 docstring/日志移除（防虚设声明）。

### 3.3 校验统一（MMA5 与 FCT2/AE2 联动）

FileContract 验证下沉 tools.py 真实工具层后，编排层 :225-236 的前置验证与 execute_analysis 路径共用同一校验——MMA5 是 FCT2/AE2 在编排端的对应面。

## 4. 主线关联

- **空转链条完整闭环**：MMA2（编排报喜）← AE1（execute pending）← FCT1（降级 ai_call）← TP2（review 冲突）——五轮推演拼出的完整「假成功」纵向链条，MultiModelAgent 是最后一环
- **死代码家族**：MMA1（重复路由残留）与 OP4/OF10/TT3（死代码/死字段）同族
- **实例竞态**：MMA3（reviewer.model 共享写）与 MCP1（单例竞争）、UPL7（单例字典竞态）同族
- **参数虚设**：MMA7（complexity 计算未传）与 SM2（增量检测未接线）、CLH2（cache_dir 虚设）同族

## 5. 测试状态

无 multi_model_agent 专项测试文件（tests/test_multi_model_agent_stream.py 存在但为流式集成测试，tests/unit 无 process 单测）；MMA1 死代码、MMA2 success 恒 True、MMA3 竞态、MMA7 参数虚设全零覆盖——空转链条的编排端判定从未被测试验证。
