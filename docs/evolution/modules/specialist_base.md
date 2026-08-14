# specialist_base.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / 专业角色基类（A3 生成 A7 修复主路径入口）
> 路径：`app/agent/specialist_base.py`（294 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**专业角色基类 Specialist**——封装 LLMClient + ReActEngine + 工具调用 + 编辑记录，供全部专业角色（backend/frontend 等）继承使用。

| 类 / 函数 | 位置 | 功能 |
|-----------|------|------|
| `_REACT_MODE` / `_REACT_MAX_ROUNDS` | :26/:27 | v3.0 固定 full 模式 + 3 轮安全阀 |
| `Specialist.__init__` | :33-57 | LLMClient 构造 + model_config + 编辑记录初始化 |
| `get_edited_files` / `clear_edits` / `update_edited_file_path` | :59-85 | 编辑记录管理（后缀匹配 fallback） |
| `call_llm` | :88-94 | 委托 LLMClient.call（stream 参数无效） |
| `_build_tools_description` | :96-103 | 工具描述注入 system prompt |
| `call_llm_with_tools` | :110-283 | **核心**：ReActEngine 构造 + 流式 thinking 合并窗口 + 编辑记录追踪 |
| `_emit_event` | :285-294 | 事件推送（fire-and-forget task） |

### call_llm_with_tools 执行流

1. `max_rounds=3`（:144-145）；tools 默认 SPECIALIST_TOOLS + MCP 合并（:146-157）
2. 流式 thinking 分支（enable_streaming_thinking + callback）：50ms 合并窗口推送 reasoning（:162-244）或普通分支（:245-256）
3. ReActEngine 构造（:258-268）：**mode=full**（:263）、无 memory
4. `tracked_execute_tool` 包装（:270-281）：写工具成功后记录 edited_files
5. `engine.run(prompt, system_prompt)`（:283）

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

- `app.utils`（:9）：call_llm（未被直接使用——实际走 LLMClient，遗留 import）
- `app.agent.dynamic_model_router`（:10）：get_dynamic_router / LayeredModelRouter
- `app.agent.react_engine`（:12）：ReActEngine（**full 模式**）
- `app.agent.llm_client`（:13）：LLMClient / LLMClientError / MAX_CONCURRENT_LLM_CALLS / get_global_semaphore
- `app.agent.tools`（:17）：SPECIALIST_TOOLS
- `app.agent.mcp_client`（运行时 :150）：MCPClientManager（工具合并）
- `app.agent.json_parser`（:14）：parse_tool_call

### 2.2 被消费方

- 专业角色子类：backend_engineer.py:221/:299、frontend_engineer.py:221/:269（调用 call_llm_with_tools，传 project_path）等全部 Specialist 体系

### 2.3 测试覆盖

- **test_specialist_base.py：收集失败（SB7）**——import `_REACT_MODE_BY_COMPLEXITY`（v3.0 已删）→ **测试文件不可运行**，主路径无有效测试

### 2.4 交叉回注（2026-08-09 支撑模块深扫）

- **tracing 依赖影响**：specialist_base 是 `traced` 装饰器的 12 个消费方之一（tracing.md TT1）——`OTEL_SAMPLING_RATE` 被误设非法值时 import tracing 抛 ValueError，本模块 import 链会随之崩溃（单点环境变量误设全系统启动失败）。
- **成本链路**：本模块主路径走 LLMClient（cost_tracker 注入），成本金额恒 0（orchestrator_progress.md OP1，LC1/DMR1 实测确认）——SB1 的 LLM 调用次数放大与成本恒零叠加，成本评估失真。

## 3. 已探明 Bug（含 bug 代码）

### SB1 [P1] full 模式 + 无 memory：主路径每轮 4 次 LLM 调用，记忆能力未接线

- **Bug 代码**：

```python
# specialist_base.py:26 - v3.0 固定 full 模式
_REACT_MODE = "full"
_REACT_MAX_ROUNDS = 3

# specialist_base.py:258-268 - 构造 ReActEngine 未传 memory
engine = ReActEngine(
    tools=tools, call_llm_fn=call_llm_fn, project_path=project_path,
    max_rounds=max_rounds, mode=react_mode, callback=callback,
    emit_event_fn=self._emit_event, role_name=self.role_name, cancel_event=self.cancel_event,
    # ← 无 memory
)
```

- **根因**：full 模式（react_engine.py `_run_full_iteration`）每轮 **Thought→Action→工具→Observation→Reflection 共 4 次 LLM 调用**（:631/:651/:714/:725）；`_REACT_MAX_ROUNDS=3` → 主路径单次最多 **12 次 LLM 调用**；且 full 模式的 memory 分支（react_engine.py:528/:660/:721/:730/:751）因**未传 memory 全部跳过**——full 模式退化（有 Reflection 无记忆），成本却照 full 计
- **影响**：Specialist 主路径（backend/frontend 全体系）LLM 调用成本放大 + 记忆能力未用
- **修正记录**：此前 react_engine.md 记录 specialist_base 为 simple 模式**错误**，v1.21 已修正
- **关联**：react_engine.md RE 潜在问题（每轮 4 次调用）

### SB2 [P1] 测试文件破碎：test_specialist_base.py 收集失败（残留旧常量引用）

- **现象**：`pytest tests/unit/test_specialist_base.py` → `ImportError: cannot import name '_REACT_MODE_BY_COMPLEXITY' from 'app.agent.specialist_base'`
- **根因**：v3.0 将 `_REACT_MODE_BY_COMPLEXITY`（按复杂度分级）改为固定 `_REACT_MODE`（:26 注释「不再按复杂度分级」），测试未同步更新
- **影响**：**主路径基类无任何有效测试**；与 §9.1/RA1 同模式（测试未跟上代码演化）

### SB3 [P2] `_build_tools_description` 用 `info["params"]` 直接下标

- **Bug 代码**：specialist_base.py:101 `info["params"].items()`——若工具条目无 params 键 → KeyError（SPECIALIST_TOOLS 当前 20 工具全带 params，契约脆弱）；react_engine.py:131 同场景用 `.get("params", {})`，两处不一致

### SB4 [P2] `update_edited_file_path` 后缀匹配可误改多个

- **Bug 代码**：:80-85 `f.replace('\\','/').endswith(old_suffix)`——`foo/bar.py` 与 `baz/bar.py` 同 suffix 时两个都被改（:82-84 无 break）
- **触发条件**：同项目存在同路径后缀文件且发生移动

### SB5 [P2] `tracked_execute_tool` 编辑记录依赖返回契约

- **Bug 代码**：:273 `result.get("success")` + :274 `tool_params.get("path", "")`——当前 write 类工具返回 `{"success": True, "path": ...}`（tools.py:887）正确；但契约脆弱（若未来写工具改返回格式，编辑记录静默失效）；且 `_write_tools` 集（:45）**不含 `delete_files_by_pattern`**（删除工具不在记录范围，语义可接受但集合需随工具演进同步）

### SB6 [P2] `_emit_event` fire-and-forget task 无引用

- **Bug 代码**：:291-292 `asyncio.create_task(result)`——不保留引用，task 可能被 GC；未 await 的 task 异常无观察者

### SB7 [P2] `call_llm(stream=...)` 参数无效

- **Bug 代码**：:88-94 `self._llm_client.call(prompt, system_prompt, stream, ...)`——LLMClient.call 的 stream 参数被忽略（llm_client.md LC6），流式须 call_stream——本方法 stream 参数形同虚设
- **遗留 import**：:9 `from app.utils import call_llm` 实际未被使用（走 LLMClient）

## 4. 潜在问题与未知点

- **v3.0 架构决策回顾**：`_REACT_MODE_BY_COMPLEXITY`（按复杂度分级）被固定 full 替代——full 模式 4 次/轮的成本放大是否是预期权衡未验证
- full 模式无 memory 时 Reflection 的 continue 判定（react_engine.py:736-739）依赖工具历史——工具调用少时反射语义弱
- 流式合并窗口 `_merge_tasks`（:226-230）：50ms 延迟 flush 的 task 生命周期由 `finally` 清理（:236-239），但 `_flush_buffer` 里 `_merge_tasks.pop(key, None)`（:186）与 finally 的 pop 竞态——双 pop 无保护，极低概率 KeyError？`pop(key, None)` 有默认值，安全
- `clear_edits`（:63-65）需调用方显式调用（注释「每轮生成前调用」）——遗漏则编辑记录跨轮累积

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | SB1：评估主路径是否应回退 simple 模式或传 memory 接 full 能力 | 控制主路径成本/启用记忆 | specialist_base.py:26/:258 | 新增 |
| 2 | P1 | SB2：修复 test_specialist_base.py 的 `_REACT_MODE_BY_COMPLEXITY` 引用 | 主路径基类恢复测试覆盖 | tests/unit/test_specialist_base.py | 新增 |
| 3 | P2 | SB3：`.get("params", {})` 统一下标 | 工具条目契约健壮 | specialist_base.py:101 | #6 |
| 4 | P2 | SB5：编辑记录改为基于写工具返回结构校验 + `_write_tools` 与工具注册同步 | 记录不失效 | specialist_base.py:45/:273 | 新增 |
| 5 | P2 | SB6：保留 task 引用或统一 await | 事件推送可靠 | specialist_base.py:291 | 新增 |
| 6 | P2 | SB7：移除 call_llm 的 stream 参数或改 call_stream | API 语义清晰 | specialist_base.py:88 | 新增 |

## 6. 演化方向关联

- **§13（一个引擎两个入口）**：SB1 确认 specialist_base 走 full 模式——「主路径 vs 修复闭环」的引擎差异需要重新评估（两者都用 full，仅 project_path/LLM 入口不同）
- **统一收敛（§4.2/#12）**：specialist_base 是 Specialist 体系的核心基类，SB1 成本问题影响面最大
- **Backlog 关联**：#6、#12，新增 SB1-SB3
