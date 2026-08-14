# OrchestratorProgress 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（进度/事件流式推送 + 成本追踪）
> 路径：app/agent/orchestrator_progress.py（568 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

进度上报与成本追踪核心：面向前端流式 UI（`useAgentStreaming.js` 事件订阅）推送 progress/file/file_diff/model_info/thinking/test_results/validation_results/cost_update/warning/file_rejected/step_detail 等事件，附复杂度估算、文件大小/变更统计；`CostTracker` 累计 token 与成本。供整个 orchestrator 生成体系共用的事件出口。

- **核心类**：`ProgressMixin`（:135 事件推送 Mixin）、`CostTracker`（:94 成本追踪）、`GenerationProgress`（:83 dataclass）。
- **事件方法族**：`_report_progress`（:138）、`_report_file_event`（:196 全量 content 事件）、`_report_file_diff_event`（:224）、`_report_model_info`（:248）、`_report_done_event`（:267）、`_report_thinking`（:282）、`_report_test_results`（:301）、`_report_validation_results`（:318）、`_report_cost_update`（:335）、`_report_performance_metrics`（:352）、`_report_warning`（:369）、`_report_file_rejected`（:385）、`_report_step_detail`（:403）。
- **统一出口**：`_emit_event`（:420 后加的共用推送入口，仅 3 个新方法使用）。
- **辅助**：`_update_phase`（:437）、`_report_current_cost`（:440）、`_report_final_metrics`（:448）、`_estimate_complexity`（:472）、`_humanize_size`（:538）、`_calculate_changes`（:547）。
- **模块常量**：`MAX_CONTENT_FOR_CONTEXT`（:14，`CM_MAX_CONTENT_FOR_CONTEXT` 默认 3000）、`PROGRESS_LABELS`（:18，60+ 阶段文案映射）。

## 2. 依赖与被依赖

- **导入依赖**：无第三方（os/time/json/asyncio/logging/dataclasses）。
- **生产使用方**：orchestrator.py（:24 导入，:138 实例化 CostTracker）、orchestrator_files.py、orchestrator_testing.py、orchestrator_generation 全家（spec_first/incremental/traditional/mixin）。`MAX_CONTENT_FOR_CONTEXT` 被 spec_first_generate.py 用（:615/:934/:957/:1171 截断 generated_contents 传验证）。
- **成本链路**：`specialist_base.LLMClient`（llm_client.py:82 注入 cost_tracker）→ `_record_usage`（:289 调 add_usage）→ `CostTracker`。`cost_per_1m_input/output` 键依赖 `dynamic_model_router.get_model_config` 返回的 dict。
- **被依赖**：`build_progress_event`（:172）、`GenerationProgress`（:83）**全库无消费方（死代码）**。
- **测试覆盖**：tests/unit/test_report_dead_methods.py —— 仅覆盖 3 个补丁方法（warning/file_rejected/step_detail）的事件形态；**成本/复杂度/变更统计/其余 10 个事件方法零测试**。

## 3. 已探明 Bug

### OP1 [P2] 成本追踪链路恒零：get_model_config 返回 dict 无成本键

- **Bug 代码**：

```python
# llm_client.py:295-299 - 读 model_config 成本键，缺键恒 0
cost_per_1m_input = self._model_config.get("cost_per_1m_input", 0.0)
cost_per_1m_output = self._model_config.get("cost_per_1m_output", 0.0)
cost_usd = (
    prompt_tokens * cost_per_1m_input + completion_tokens * cost_per_1m_output
) / 1_000_000

# dynamic_model_router.py:1015-1020 - get_model_config 返回的键
return {
    "temperature": ..., "max_tokens": ..., "thinking_budget": ...,
    "context_length": ctx_len, "timeout": ...,
}  # 无 cost_per_1m_input/output
```

- **根因**：成本金额键 `cost_per_1m_input`/`cost_per_1m_output` 在 `get_model_config` 返回 dict 中不存在（实测仅 temperature/max_tokens/thinking_budget/context_length/timeout 5 键），`.get(..., 0.0)` 恒返回 0。model_registry.py 的 `ln`（每百万输入 token 成本，元）字段存在但从未接入 llm_client。
- **影响**：token 数正确累计，但 `CostTracker.total_cost_usd` 恒 0（实测 1000+2000 token → 0.0）→ 前端成本展示、`_report_cost_update`、`_report_final_metrics`、完成总结里的成本全为 0，成本预估/追踪形同虚设。
- **验证方式**：实测 `get_model_config("Qwen/Qwen3.5-4B")` keys 无成本键；`CostTracker().add_usage(...,0.0)` 后 get_summary 恒 0.0。

### OP2 [P2] `_report_file_event` 推全量 content，MAX_CONTENT_FOR_CONTEXT 截断只用在 spec_first

- **Bug 代码**：

```python
# orchestrator_progress.py:196-213 - 本模块定义截断常量却在此不截断
event = {"type": "file", "path": file_path, "content": content, ...}  # :204 全量
file_size = len(content.encode('utf-8'))

# spec_first_generate.py:615 - 反而在验证通道截断
generated_contents[file_path] = content[:MAX_CONTENT_FOR_CONTEXT]
```

- **根因**：`MAX_CONTENT_FOR_CONTEXT`（3000 字符）定义在本模块，但唯一的 content 事件出口 `_report_file_event` 不应用它，全量 JSON 序列化推送；截断只发生在 spec_first 的验证上下文。
- **影响**：大文件（数千行）progress 事件单条可达数 MB，前端订阅 `content` 通道内存/带宽放大；截断语义不一致——进度通道全量 vs 验证通道截断。
- **验证方式**：10000 行文件 → `_report_file_event` 推送的 json 含完整 10000 行 content（实测可证）。

### OP3 [P3] `_pending_tasks` 类属性跨实例共享 + task 异常无人 retrieve

- **Bug 代码**：

```python
# orchestrator_progress.py:136 - 类属性，非实例属性
class ProgressMixin:
    _pending_tasks: set = set()
    ...
    task.add_done_callback(self._pending_tasks.discard)  # 只移除，不取异常
```

- **根因**：`_pending_tasks` 定义在类体（类属性），所有 ProgressMixin 实例共享同一 set（实测 `a1._pending_tasks is a2._pending_tasks → True`）。测试 `_CapturingReporter.__init__` 已手动 `self._pending_tasks = set()` 覆盖规避，生产未修。异步 task 仅 `discard` 回调，异常无人 retrieve → asyncio「Task exception was never retrieved」告警泄漏。
- **影响**：多 orchestrator 实例并发时不同事件循环的 task 混入同一 set；callback 异步抛异常时日志告警且异常信息丢失。
- **验证方式**：实测两实例共享同一 set 对象（见上）。

### OP4 [P3] `build_progress_event` 与 `GenerationProgress` 死代码（DRY 复制）

- **Bug 代码**：

```python
# orchestrator_progress.py:172 - 与 _report_progress:138-170 完全相同 dict+ETA 构建
def build_progress_event(self, step, current, total, **kwargs) -> Dict: ...
# :83 - dataclass，全库无引用
@dataclass
class GenerationProgress: ...
```

- **根因**：`build_progress_event`（:172-194）把 `_report_progress` 的 percentage/elapsed/eta 计算逻辑整体复制一遍，但全库无调用方；`GenerationProgress` dataclass 无实例化点。
- **影响**：死代码 + 进度计算逻辑两处维护（改动需同步两处）。
- **验证方式**：rg 全库 `build_progress_event`/`GenerationProgress` 仅本文件定义行命中。

### OP5 [P3] `_emit_event` 统一出口只被 3 个新方法用，其余 10 个 `_report_*` 各复制 callback 逻辑

- **Bug 代码**：

```python
# :420-435 _emit_event 统一 callback+asyncio 管理；但 :214-222/:238-246/:257-265/... 各方法仍各自 try/except 复制
result = cb(json.dumps(event, ensure_ascii=False))
if asyncio.iscoroutine(result): task = asyncio.create_task(...)
```

- **根因**：`_emit_event` 为补丁后加，历史 `_report_file_event/_report_file_diff_event/_report_model_info/_report_done_event/_report_thinking/_report_test_results/_report_validation_results/_report_cost_update/_report_performance_metrics/_report_progress` 未重构到统一入口，callback 调用 + 协程任务管理 + 异常日志 11 处重复。
- **影响**：推送侧改动需同步 11 处；`_emit_event` 新增行为（如超时/节流）不会自动覆盖旧方法。
- **验证方式**：代码比对可见 8 处同构 try/except 块。

### OP6 [P3] `_calculate_changes` 的 removed 按行数差计算，替换场景失真

- **Bug 代码**：

```python
# :552-560
added = len(new_lines) - len(old_lines)
removed = max(0, -added)   # 行数差为 0 时 removed=0
for i in range(min_len):
    if old_lines[i] != new_lines[i]: changed += 1
```

- **根因**：`removed` = 行数差（new 比 old 少几行），不统计实际删除行。删除 10 行同时新增 10 行的纯替换场景 → added=0、removed=0、modified=10，diff 统计误导。
- **影响**：file_diff 事件的 removed 语义失真，前端变更面板不准确。
- **验证方式**：old=10 行 new=10 行全不同 → removed=0 但实际删 10 行（实码可证）。

### OP7 [P3] `_estimate_complexity` 的 `low_comments` factor 不计分 + 注释统计只认 `#` 开头

- **Bug 代码**：

```python
# :513-516 - low_comments 只 append 到 factors，不影响 score/level
if comment_ratio < 0.05:
    complexity_factors.append("low_comments")
```

- **根因**：`low_comments` factor 不进 complexity_score，前端/决策端只按 score 分 level，该因子纯装饰。注释比例仅统计 `#` 开头行，不含 docstring/行尾注释。函数内 `import re`（:505）非模块级。
- **影响**：复杂度等级判定忽略注释健康度；指标与直觉有偏差。
- **验证方式**：注释占比 0% 的 10 行文件 → level=low、factors 含 low_comments 但 score=0（实码可证）。

### OP8 [P3] `_report_final_metrics` 的 `_llm_call_count`/`_retry_count` 恒 0（无维护点）

- **Bug 代码**：

```python
# :459-460 - getattr 默认 0
"llm_calls": getattr(self, '_llm_call_count', 0),
"retry_count": getattr(self, '_retry_count', 0)
```

- **根因**：全库 rg 无任何 `_llm_call_count`/`_retry_count` 赋值点，orchestrator 从不计数 LLM 调用/重试。
- **影响**：`_report_final_metrics` 与完成事件的 llm_calls/retry_count 恒 0，前端指标面板失真。
- **验证方式**：rg `_llm_call_count\s*[+\-]?=` 全库零命中。

## 4. 修复建议

- **OP1**：`get_model_config` 返回 dict 增加 `cost_per_1m_input`/`cost_per_1m_output`（从 model_registry 的 `ln`/输出价映射）；或 `_record_usage` 改用 `model_registry` 取价。
- **OP2**：`_report_file_event` 对 content 应用 `MAX_CONTENT_FOR_CONTEXT` 截断（与 spec_first 一致），或改用 `_report_file_diff_event` 只推变更。
- **OP3**：`_pending_tasks` 改为 `__init__` 中 `self._pending_tasks = set()` 实例属性；done callback 中 `task.exception()` 消费异常。
- **OP4**：删除 `build_progress_event`（或让 `_report_progress` 复用它）；删除 `GenerationProgress`。
- **OP5**：将 11 个 `_report_*` 的推送逻辑收敛到 `_emit_event`。
- **OP6**：`removed` 改为按行内容 diff 统计实际删除行（与 modified 同类算法）。
- **OP7**：`low_comments` 计入 score 或在决策端消费 factors；注释统计纳入 docstring。
- **OP8**：在 LLM 调用点维护 `_llm_call_count`/`_retry_count`（llm_client 或 orchestrator 层），或从 metrics 移除这两个恒 0 字段。

## 5. 待实测项

- OP1 已实测确认（成本恒零）。
- OP3 已实测确认（类属性共享）。
- 其余为代码级确定性结论，可随修复补测。
