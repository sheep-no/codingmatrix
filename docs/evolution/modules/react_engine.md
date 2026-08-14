# react_engine.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / 统一 ReAct 引擎（A7 验证修复 + Specialist 全体系复用）
> 路径：`app/agent/react_engine.py`（770 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**统一的 ReAct 引擎基类**，两种运行模式：

- **simple 模式**（Specialist 使用）：Thought→Tool→Result 自然终止，安全阀强制生成
- **full 模式**（ReActAgent 使用）：Thought→Action→Observation→Reflection→Final 反射终止，带心跳超时

| 类 / 函数 | 位置 | 功能 |
|-----------|------|------|
| `ReActStep` / `ReActResult` | :23-43 | 步骤与结果 dataclass |
| `ReActEngine.__init__` | :73-124 | tools/call_llm_fn/project_path/max_rounds/mode/callback/memory 等配置 |
| `_estimate_tokens` / `_truncate_to_tokens` | :64-71/:398-406 | 中英混排 token 估算与截断 |
| `_build_system_prompt` | :136-177 | 按模式构建系统 prompt（含工具列表） |
| `_parse_tool_call` | :179-200 | JSON 解析工具调用（直接/parser 两级回退） |
| `_execute_tool` | :202-225 | 执行工具（同步/异步统一 + 超时 + MCPError 透传） |
| `_build_history_text` | :359-396 | 滑动窗口工具历史（最近 N 条完整 + 早期摘要 + token 兜底） |
| `_run_simple` | :408-518 | simple 循环（安全阀最后一轮强制生成） |
| `_run_full` | :520-557 | full 循环（心跳监控替代固定超时） |
| `_run_with_heartbeat` | :559-595 | 心跳超时监控（每 10s 检查，LLM 活动则续期） |
| `_run_full_iteration` | :606-743 | full 单轮：Thought→Action→工具→Observation→Reflection→终止判定 |
| `_build_final_result` / `_generate_final_answer` | :745-754/:293-327 | 最终答案生成（干净 system，防工具 JSON） |
| `_build_context` | :756-770 | full 模式上下文（最近 3 条工具历史 + 记忆） |

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

- `app.agent.architect_json_parser`（:17）：ArchitectJsonParser（JSON 容错解析）
- `app.agent.topology_scheduler`（:18）：HeartbeatTracker（心跳活动跟踪）
- `app.agent.mcp_client`（运行时 import :222/:488/:684）：MCPError（连接断开致命错误）
- **调用约定**：`call_llm_fn(prompt, system_prompt) -> str`；工具 fn 约定 **`fn(project_path=..., **params)`**（:209）

### 2.2 被消费方（4 个 ReActEngine 使用方）

| 使用方 | 模式 | project_path | 循环是否运行 |
|--------|------|-------------|-------------|
| `specialist_base.py:258`（主路径） | **full**（:26 `_REACT_MODE="full"`） | 正常传值（:261） | ✅ |
| `agent_executor.py:147`（分析子代理） | simple | 正常传值 | ✅ |
| `task_planner.py:160`（任务规划） | simple | 正常传值（max_rounds=3） | ✅ |
| `react_agent.py:146`（修复闭环） | full | **""（:149）** | ❌ 短路 |

> **2026-08-05 v1.21 修正**：`specialist_base.py:26` 实为 `_REACT_MODE = "full"`（v3.0 固定，注释「不再按复杂度分级」）——此前记录 specialist_base 为 simple 模式**错误**。full 模式每轮 4 次 LLM 调用（Thought/Action/Observation/Reflection，见 RE 潜在问题），且 specialist_base 构造 ReActEngine **未传 memory**（:258-268）——full 模式记忆能力未接线。见 modules/specialist_base.md SB1。

### 2.3 测试覆盖

- test_react_engine.py：**32 passed**。工具 fn 签名测试用 `my_tool(project_path="", **kwargs)`（:133/:144）——**佐证引擎侧调用约定**，executor wrapper 是破坏方（RA1）。**未覆盖**「full + 非空工具 + project_path 正常」组合（test_full_mode :101 用 `tools={}` 短路）。

## 3. 已探明 Bug（含 bug 代码）

### RE1 [P0] `project_path` 空串短路：run() 无项目路径时 ReAct 循环完全不执行 → 修复闭环退化

- **Bug 代码**：

```python
# react_engine.py:344-346 - run() 入口短路
if not self.project_path or not self.tools:
    logger.info(f"{self.role_name} ReAct: 无项目路径或无工具，直接调用 LLM")
    return await self.call_llm_fn(prompt, system_prompt)
```

- **触发链路**：react_agent.py:149 `project_path=""` → ReActEngine.run 短路 → **直接单次 call_llm_fn** → full 循环、工具调用、反思全部不执行 → steps 空 → `ReActResult.success = any(空) = False`
- **影响**：**error_recovery 的 ReAct 自动修复实际是「单次 LLM 调用 + 恒判失败」**——比 RA1（wrapper TypeError）更早触发，工具调用在 TypeErrror 之前就被短路跳过。RA1 的 TypeError 在短路修复前**不会到达**。修复闭环双重失效。
- **实测/佐证**：4 使用方中仅 react_agent 传 ""（短路）；其余 3 个传正常路径
- **关联**：react_agent.md RA2（context 丢弃）是本 bug 的直接成因

### RE2 [P0] 工具 fn 签名契约：`fn(project_path=..., **params)`（:209）与 executor wrapper `wrapper(params)` 冲突

- **Bug 代码**：

```python
# react_engine.py:208-209 - 引擎统一注入 project_path（约定 fn 首参为 project_path）
fn = self.tools[tool_name]["fn"]
result = fn(project_path=self.project_path, **tool_params)
```

- **根因**：引擎按 SPECIALIST_TOOLS 风格 fn（首参 `project_path`）设计（test_react_engine :133/:144 佐证）；executor ToolRegistry wrapper 签名 `wrapper(params)`（executor.py:204）破坏该约定 → 若 ReActAgent 修好 RE1 短路，将在此处 TypeError（RA1）
- **影响**：ReActAgent 栈工具契约断裂的**引擎侧根源**（修复闭环当前被 RE1 遮蔽）

### RE3 [P1] 同步工具无超时保护：wait_for 只包 coroutine，同步 fn 阻塞无界

- **Bug 代码**：

```python
# react_engine.py:209-213 - 同步 fn 直接调用，无 timeout 保护
result = fn(project_path=self.project_path, **tool_params)
if asyncio.iscoroutine(result):
    result = await asyncio.wait_for(result, timeout=timeout)
```

- **根因**：`_execute_tool(timeout=120)` 声称「带超时保护」（docstring :203），但 wait_for 仅覆盖 coroutine 分支；同步 fn（tools.py `_tool_read_file`/`_tool_run_command` 等）直接同步阻塞调用——`_tool_run_command` 长命令执行时**卡死事件循环，超时与取消均失效**
- **影响**：Specialist 主路径（simple 模式）工具全为同步 fn → 长命令可无限阻塞
- **建议**：`asyncio.wait_for(asyncio.to_thread(fn, ...))` 包裹同步调用

### RE4 [P1] `result_count` 恒 0：`result.get("results", [])` 对全工具无 results 键

- **Bug 代码**：

```python
# react_engine.py:504 - 仅取 "results" 键，search_files 返回的是 "matches"
result_count = len(tool_result.get("results", [])) if isinstance(tool_result, dict) and success else 0
```

- **根因**：search_files 返回 `{"success": True, "matches": [...]}`（tools.py:830 无 results 键）；read_file 返回 error 或业务数据 → **所有工具 result_count 恒 0**
- **影响**：事件展示层恒报「找到 0 条结果」（:506）——UI 误导、调试困难；已在 AGENT-ENGINE §12 记录，此处确认是引擎侧单一来源
- **关联**：tools.md T7 / AGENT-ENGINE §12

### RE5 [P2] full 模式 LLM 异常返回 `""` → run 提前终止丢全部步骤

- **Bug 代码**：

```python
# react_engine.py:547 - 非 None 即返回，"" 也触发提前终止
result = await self._run_with_heartbeat(task_coro, tracker)
if result is not None:
    return result

# react_engine.py:634/:654 - 异常路径返回 ""（而非 None/继续）
return ""
```

- **根因**：`_run_full_iteration` 的 Thought/Action LLM 调用异常时返回 `""`，run 层把 "" 当正常终止值返回——**单次 LLM 抖动即丢弃全部已执行步骤**
- **影响**：full 模式（ReActAgent）稳定性脆弱；修复闭环即使短路过，单次调用失败也是静默 `""`

### RE6 [P2] `_reflect` JSON 解析失败默认 `continue=True` → full 模式跑满轮次

- **Bug 代码**：react_engine.py:286 解析失败/非 dict → `{"continue": True, "task_complete": False}`（设计为「继续而非终止」）
- **影响**：反射不稳定时 full 模式恒跑满 max_rounds（成本），never 自然终止；:736-739 `should_stop = not continue or task_complete` 对 `{"continue": False, "task_complete": False}` 矛盾响应也会 stop——语义模糊

### RE7 [P2] clean_system 双份重复定义

- **Bug 代码**：`_generate_final_answer` :311-321 与 `_run_simple` 安全阀 :435-445 定义**完全相同**的干净 system prompt 文本（仅 :446 用 call_llm_fn 而非 _generate_final_answer）
- **影响**：simple 模式最终答案生成与 full 模式路径分叉（两处逻辑重复），修改易失同步

### RE8 [P2] `_build_history_text` 边界

- :388-394 兜底截断 `cut_chars = int(len(summary) * overflow_tokens / max(summary_tokens, 1))`——summary 空时 cut 全部（有 `max(0, ...)` 保护），但 summary_tokens 为 0 时 `len(summary)-cut_chars` 可为负→`[:max(0,负)]`=空串，行为可用但粗糙
- :370/:388 只对 `>MAX_HISTORY_TOKENS` 分支处理，`==` 边界不断言

## 4. 潜在问题与未知点

- **simple 模式工具超时是 Specialist 主路径稳定性风险**（RE3）——tools.py 同步 fn 阻塞
- full 模式 **Thought/Action 每轮两次 LLM 调用 + Observation + Reflection 一次** = 每轮 4 次 LLM 调用，成本高（:631/:651/:714/:725）
- `_build_context` 只含最近 3 条工具历史 + 记忆（:760-768），长任务的早期关键信息被挤出
- `emit_event`/`stream`/`callback` 三套事件机制并存（:232-246），语义重叠
- `memory` 只在 full 模式接线（:528/:660/:721/:730/:751），simple 模式无记忆

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | RE1：ReActAgent.process 消费 context 的 project_path 传入引擎（不短路） | 修复闭环恢复 ReAct 循环 | react_agent.py:149 / error_recovery.py:26 | #14 |
| 2 | P0 | RE2：统一工具 fn 签名（wrapper 接受 project_path，或引擎按 wrapper 约定调用） | 消除工具契约断裂 | react_engine.py:209 / executor.py:204 | #6、#13 |
| 3 | P1 | RE3：同步 fn 用 `asyncio.wait_for(asyncio.to_thread(...))` 包裹 | 同步工具真正超时可控 | react_engine.py:207-213 | 新增 |
| 4 | P1 | RE4：result_count 兼容 `matches`/`results`/业务长度 | 事件统计真实 | react_engine.py:504 | §12、新增 |
| 5 | P2 | RE5：full 异常路径返回 None 继续 | 单次抖动不丢全部步骤 | react_engine.py:634/:654 | 新增 |
| 6 | P2 | RE6：反射解析失败改保守终止或可配置 | 控制 full 模式成本 | react_engine.py:283-289 | 新增 |
| 7 | P2 | RE7：提取 `_GENERATION_SYSTEM` 常量统一最终答案生成路径 | simple/full 行为一致 | react_engine.py:311-321/:435-445 | 新增 |

## 6. 演化方向关联

- **§13 修正（react_agent 深扫）**：RE1 是 react_agent.md RA2 的**引擎侧放大**——project_path="" 不仅丢上下文，直接短路整个循环
- **统一工具 Schema（§11.4 #6）**：RE2 是工具 fn 签名统一的核心节点（引擎侧约定）
- **§12 已记录**：RE4（result_count 恒 0）确认引擎侧单一来源
- **Backlog 关联**：#6、#13、#14，新增 RE3-RE7
