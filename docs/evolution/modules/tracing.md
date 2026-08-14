# Tracing 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（OpenTelemetry 追踪）
> 路径：app/agent/tracing.py（246 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

OpenTelemetry（Jaeger/OTLP）分布式追踪：为 Agent 调用链提供 span 记录——`traced` 装饰器包装关键函数（架构设计、文件生成、验证、审查、会话管理等），自动创建 span、记录异常/返回值属性；附 trace id 存取、跨服务 header 注入、优雅关闭。默认关闭（OTEL_ENABLED 未设时全程 noop，无第三方依赖）。

- **配置（环境变量）**：OTEL_ENABLED（:38）、OTEL_EXPORTER（:39 jaeger/otlp/none）、OTEL_JAEGER_ENDPOINT（:40）、OTEL_OTLP_ENDPOINT（:41）、OTEL_SERVICE_NAME（:42）、OTEL_SAMPLING_RATE（:43）、OTEL_BATCH_*（:53-55）。
- **模块级初始化**：:64-113 import 时按 OTEL_ENABLED 初始化 TracerProvider + exporter（jaeger/otlp/none/未知 fallback）；:108 捕获 ImportError 降级；:151-152 `tracer = _NoopTracer()` 兜底。
- **核心 API**：`traced`（:155 装饰器，async/sync 双包装）、`_set_result_attrs`（:206）、`get_current_trace_id`（:214）、`set_trace_id`（:225）、`shutdown_tracing`（:229）、`inject_trace_context`（:236）。
- **Noop 替身**：`_NoopSpan`（:116）、`_NoopTracer`（:141）。

## 2. 依赖与被依赖

- **导入依赖**：仅 stdlib（os/functools/asyncio/logging/contextvars）；opentelemetry 包为**可选延迟导入**（启用时）。
- **生产使用方**：**12 处全部只导入 `traced`**——architect、frontend_engineer、backend_engineer、code_reviewer、test_runner、specialist_base、session_manager、orchestrator_requirements/mixin、orchestrator_generation（traditional_generate/mixin/evaluate_mixin）。用法：`@traced("xxx.yyy", attributes={"component": ..., "role": ...})` 静态 span_name + 静态 attributes。
- **半孤儿 API**：`get_current_trace_id`/`set_trace_id` 仅测试用（test_tracing.py），`shutdown_tracing`/`inject_trace_context` **连测试都无消费方**（全库孤儿）。
- **测试覆盖**：tests/unit/test_tracing.py 仅 2 个 noop 冒烟测试（装饰器返回正确值 + trace_id 存取）——**OTel 启用路径零覆盖**。

## 3. 已探明 Bug

### TT1 [P2] 模块级 float() 未校验：非法 OTEL_SAMPLING_RATE 使 12 个消费模块 import 全崩

- **Bug 代码**：

```python
# tracing.py:43 - 模块顶层直接 float()，无 try 无默认兜底
_sampling_rate: float = float(os.environ.get("OTEL_SAMPLING_RATE", "1.0"))
```

- **根因**：`:43` 是唯一非容错的环境变量解析（:38-42 均为 `str`/`in` 安全操作）。`OTEL_SAMPLING_RATE=abc` 或空串时 `float()` 抛 ValueError 在模块级冒泡，**import tracing 本身即崩溃**。
- **影响**：architect/frontend/backend/code_reviewer/test_runner/specialist_base/session_manager 等 12 个消费模块 import 全部失败（实测 `import app.agent.architect` 抛 ValueError）——**单点环境变量误设（如用户顺手填个非数字采样率）导致整个 agent 系统启动失败**。
- **验证方式**：`OTEL_SAMPLING_RATE=abc python3 -c "import app.agent.tracing"` 与空串均 ValueError（实测）。

### TT2 [P2] OTel 启用路径零测试 + 模块级副作用：默认 noop 掩盖启用路径全部风险

- **Bug 代码**：

```python
# tracing.py:64-113 - import 时按 OTEL_ENABLED 初始化，启用路径从未被 CI 执行
if _otel_enabled:
    try:
        from opentelemetry import trace
        ...
        _tracer_provider.add_span_processor(_make_batch_processor(JaegerExporter(...)))
```

- **根因**：测试环境未装 opentelemetry 包 → `_otel_enabled` 恒 False → 测试全在 noop 模式跑；启用路径（exporter 依赖、batch 参数、endpoint 配置、异常记录）零执行。模块 import 即初始化，运行期改 OTEL_ENABLED 无效。
- **影响**：生产首次开启 OTEL_ENABLED=1 时，exporter 包缺失/endpoint 错配/batch 配置错误才会暴露；exporter 包缺失时整个 tracing 静默降级 noop（仅启动日志 warning），**运行期静默失效**，无人察觉 span 根本没上报。
- **验证方式**：`OTEL_ENABLED=1 python3 -c "from app.agent.tracing import tracer"` 走未装包降级路径（实测 warning + _NoopTracer），无任何测试覆盖此路径。

### TT3 [P3] get/set trace_id + inject/shutdown 生产零消费（半孤儿）

- **Bug 代码**：

```python
# tracing.py:214-246 - 仅 traced 被 12 处消费，这四个 API 生产零调用
def get_current_trace_id(self): ...
def set_trace_id(self): ...
def shutdown_tracing(self): ...
def inject_trace_context(headers): ...
```

- **根因**：12 个使用方只 import `traced`；get/set 仅 test_tracing.py 用，inject/shutdown 全库无调用方。默认 noop 下 `get_current_trace_id` 因 `_otel_enabled=False` 走 `_current_trace_id.get()` 恒 None（实测），且生产无人 set_trace_id。
- **影响**：日志关联 trace id、跨服务传播（inject）、优雅关闭（shutdown）三能力**未接线**；span 已记录但日志里没有 trace id 可查。
- **验证方式**：默认环境 `get_current_trace_id()` 返回 None（实测）；rg 全库仅 test_tracing.py 引用 set/get。

### TT4 [P3] `_set_result_attrs` 不校验类型 + span_name 静态：追踪粒度无法区分文件/模型

- **Bug 代码**：

```python
# tracing.py:206-211 - 固定 4 key，无类型校验
if isinstance(result, dict):
    for key in ("success", "model_name", "file_path", "complexity_level"):
        if key in result:
            span.set_attribute(f"result.{key}", result[key])

# 使用方（如 frontend_engineer.py:86）span_name 静态
@traced("frontend.generate_file", attributes={"component": "specialist", "role": "frontend"})
```

- **根因**：span_name 与 attributes 全静态，跨文件/跨模型的追踪只能靠 `code.function`；`_set_result_attrs` 从 result 取动态值但若 value 为 OTel 非法类型（Path/list[dict] 等）会被 SDK warning 丢弃（不抛，可容忍），且只提取 4 个固定 key。
- **影响**：同一 `generate_file` 的数百次调用 span 完全同名，无 file_path/model 维度区分，追踪只能定位「哪类函数」不能定位「哪个文件」。
- **验证方式**：无 OTel 包时 `_set_result_attrs` 走 noop；启用时非法类型属性静默丢失（SDK `_check_value` warning 路径）。

### TT5 [P3] async 子任务 span context 不传播：并发子任务 span 脱离父链

- **Bug 代码**：

```python
# agent 系统大量 create_task（信号量并发、ProgressMixin._pending_tasks 等）
task = asyncio.create_task(result)  # OTel span context 经 contextvars，默认不继承
```

- **根因**：OTel 的 current span 走 contextvars；`asyncio.create_task` 默认创建新 context，不携带调用方当前 span 上下文（除非 `contextvars.copy_context()` 包装）。
- **影响**：orchestrator 的信号量并发（specialist_base 的 generate 并发）、`_pending_tasks` 回调等子任务 span 脱离父 span 成为独立 root，调用链断裂，分布式追踪的父子层级失真。
- **验证方式**：OTel 启用下对 create_task 包一层 task 的 span 为 root（需 mock 包验证）。

### TT6 [P3] 测试仅 2 个且全在 noop 模式：异常记录/类型丢弃/装饰器语义零验证

- **Bug 代码**：

```python
# tests/unit/test_tracing.py - 仅 2 个 noop 冒烟测试
def test_traced_decorator(self): ...  # 装饰器返回 42
def test_trace_id_propagation(self): ...  # set/get 同一 context
```

- **根因**：未 mock opentelemetry 包，启用路径的异常记录（record_exception + error 属性）、result 类型丢弃、async/sync 双包装、装饰器内 `_set_result_attrs` 抛异常时的语义（成功函数被记录为 error 并 re-raise 的边界）均未验证。
- **影响**：`traced` 装饰器最关键的失败语义（异常→记录→re-raise 链路）无回归保护；OTel 集成回归只能靠人工。
- **验证方式**：rg tests/ 无 OTEL_ENABLED/mock opentelemetry 引用（实测）。

## 4. 修复建议

- **TT1**：:43 加 try/except 兜底默认 1.0（与 :38-42 风格一致），非法值 log warning 不崩。
- **TT2**：测试加 `unittest.mock` 假 opentelemetry 模块覆盖启用路径（exporter 选择、batch 参数、ImportError 降级、异常记录）；或延迟初始化——`ensure_initialized()` 在首次使用时按当前环境初始化，避免模块级副作用。
- **TT3**：决定三 API 去留——接入 session/orchestrator 生命周期（shutdown 于关闭钩子、inject 于 MCP HTTP 调用）或标记孤儿删除。
- **TT4**：`traced` 支持动态 attributes 函数（`lambda result, args` 提取 file_path/model），或在 span_name 中内插关键参数；`_set_result_attrs` 对非法类型 try/except 降级。
- **TT5**：并发点用 `contextvars.copy_context()` + `run_in_executor`/`create_task` 包装，或依赖 OTel 的 context 传播扩展。
- **TT6**：补启用路径单测（mock 包），覆盖异常记录、类型丢弃、async 包装语义。

## 5. 待实测项

- TT1 已实测确认（OTEL_SAMPLING_RATE=abc/空串均 ValueError，architect import 链崩溃）。
- TT2 已实测确认（OTEL_ENABLED=1 未装包降级 noop 路径）。
- TT3 默认 noop 下 get_current_trace_id 恒 None 已实测。
- TT4/TT5/TT6 为代码级结论，启用路径需 mock 包后实测。
