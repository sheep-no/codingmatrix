# AgentExecutor 深扫（agent_executor.py，164 行）

> 第七十九轮推演 | 2026-08-13 | 定位：multi_model_agent 的执行器 + 分析工具注册表（从 multi_model_agent 拆分的 re-export 壳层）

## 1. 模块定位

AgentExecutor 承载 multi_model_agent 的两条执行路径：① `execute`/`execute_file_operation` 逐步执行 planner 产出的任务步骤（file_operation/ai_call）；② `execute_analysis` 委托 ReActEngine（simple 模式）执行代码分析任务。ANALYSIS_TOOLS 是只读分析工具注册表（SPECIALIST_TOOLS 子集 + run_command）。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `multi_model_agent.py:72/:158/:238` | execute_analysis（分析任务）+ execute（步骤执行），生产活跃 |
| 消费方 | `multi_model_agent.py:43` | re-export AgentExecutor/ANALYSIS_TOOLS |
| 依赖 | `react_engine.py` | ReActEngine simple 模式执行分析 |
| 依赖 | `tools.py:616-648` | run_command 的危险命令正则 + 前缀白名单 |

## 2. 深扫发现

### P2 项

- **AE1 `ai_call` 步骤类型空转（返回 pending 占位符）**——`execute`（:101-102）对 `ai_call` 步骤返回 `{"status": "pending", "task": ...}` **不真正执行任何 AI 调用**；task_planner 的 prompt 声明 ai_call 是合法步骤类型（task_planner.py:88），但 AgentExecutor 从不执行它——multi_model_agent:238 `result = await self.executor.execute(step)` 直接拿 pending 结果 append 进 results 当作已完成。**若 planner 产出 ai_call 步骤，任务静默跳过**（声称的「AI 调用」从未发生，结果列表含假成功条目）。`test_ai_call_step`（:127-135）把 pending 断言为正确行为 = **测试固化错误预期**（TR2 家族，掩盖 AE1）。
- **AE2 `execute_analysis` 绕过 FileContract + 工具面含写操作（docstring 声称「只读」不符）**——multi_model_agent:225 的 FileContract 前置验证（路径安全）只在 step 执行路径（:238 execute → execute_file_operation）；而 execute_analysis 路径（:153-165）走 ReActEngine + ANALYSIS_TOOLS，**完全绕过 FileContract**。且 ANALYSIS_TOOLS 含 `run_command`（:47-53），其前缀白名单（tools.py:630-648）含 `pip install`/`npm install`/`echo`/`git commit` 等**写操作**——docstring「只读操作，不修改文件」（:116）与工具面矛盾，分析任务实际可修改项目文件。MCP 工具合并（:138-145）也进 ANALYSIS_TOOLS 绕过 FileContract。

### P3 项

- **AE3 `execute_analysis` model 默认值硬编码 + 无统一信号量/成本**——`model_name: str = "Qwen/Qwen3-8B"`（:110）硬编码默认；call_llm_fn（:124-134）直连 `app.utils.call_llm` 不走 LLMClient 信号量/成本追踪（LCL1 收敛范围，ERL4/EV1 同族）。
- **AE4 `execute_file_operation` delete 无路径保护**——:83-84 直接调 `file_operator.delete`，依赖调用方（multi_model_agent:225）前置校验；若 AgentExecutor 被其他路径直接实例化调用（测试/独立使用），delete 任意路径无保护。
- **AE5 MCP 工具合并失败静默**——:143-145 `except Exception` 只 `logger.debug`，用户配置的分析类 MCP 工具获取失败时静默缺失，无任何可观测信号（TT2 家族）。
- **AE6 `_ANALYSIS_SYSTEM_PROMPT` 与工具面不一致**——prompt「只读操作」规则（:62）与 run_command 写操作前缀（AE2 同源），LLM 可能被诱导调用非只读命令。

## 3. 演化方向

### 3.1 执行器的契约收敛

execute 的 ai_call 分支要么真正接线（调 LLM 执行子任务），要么从 task_planner 的合法步骤类型中移除——当前「声明合法 + 实现空转 + 测试固化」是 §5.6 支柱 1（产物协议）的典型反例。execute_analysis 的「只读」契约应通过移除 run_command 或收紧前缀白名单（只留 grep/find/ls 等纯读命令）达成，与 FileContract 校验路径统一。

### 3.2 与验证链的关系

AE2 使分析任务成为 FileContract 的绕过面——文件操作安全验证（§5.6 支柱 2 执行端）在分析路径失效。修复应让 FileContract 校验下沉到 tools.py 的 `_tool_read_file` 等真实工具层（所有路径统一生效），而非在 multi_model_agent 编排层拦截。

## 4. 主线关联

- **「声明能力≠实现」**：AE1（ai_call 空转）与 SM2（增量检测声称未接线）、MEM1（embedding 声称未实现）同主线——prompt/测试声称的能力实际是占位
- **安全验证绕过**：AE2（分析路径绕 FileContract）与 CV2/CV3（验证假阳性）、UT5（验证空转）同属验证端失真——FileContract 是验证栈在文件操作维度的执行端，存在但被路径绕过
- **测试固化错误预期**：AE1（test_ai_call_step 断言 pending）与 JP2（test_truncated_json_object 固化补全）、TR2（内存态掩盖落盘失败）同族

## 5. 测试状态

test_agent_executor.py 覆盖较全（注册表 7 + 操作 5 + 步骤 3 + 分析 2），但：test_ai_call_step 固化 pending 占位（掩盖 AE1）；test_analysis_* 用 mock call_llm 单轮成功路径，未覆盖 FileContract 绕过（AE2）与工具执行真实行为。
