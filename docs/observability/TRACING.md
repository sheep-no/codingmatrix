# OpenTelemetry 追踪指南

> 最后更新：2026-09-03

项目在 `app/agent/tracing.py` 中提供可选的 OpenTelemetry Agent Span。追踪默认关闭，并以显式 `@traced` 装饰器覆盖部分编排、工程师、会话和测试操作。

## 实现边界

- 配置在模块导入时从环境变量读取，因此应在启动 Python 进程前设置。
- 启用后创建全局 `TracerProvider`、概率采样器和 `BatchSpanProcessor`。
- 支持 Jaeger Thrift HTTP、OTLP HTTP 和仅记录不导出的 `none` 模式。
- OpenTelemetry 包缺失时记录告警并回退到 no-op tracer。
- 追踪关闭时装饰器和手动 Span 调用仍可执行，所有操作由 no-op 对象吸收。
- 当前没有 FastAPI、HTTP 客户端、SQLAlchemy、Redis 或 Celery 自动插桩。
- `inject_trace_context()` 已实现 W3C Trace Context Header 注入，但当前代码没有调用它。
- `shutdown_tracing()` 已实现 provider shutdown 与 pending Span flush，但当前应用生命周期没有调用它。

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `OTEL_ENABLED` | 空 | `1`、`true` 或 `True` 时启用 |
| `OTEL_EXPORTER` | `jaeger` | `jaeger`、`otlp` 或 `none`；未知值回退 Jaeger |
| `OTEL_JAEGER_ENDPOINT` | `http://jaeger:14268/api/traces` | Jaeger Thrift HTTP collector |
| `OTEL_OTLP_ENDPOINT` | `http://otel-collector:4318` | 传给 OTLP HTTP exporter 的 endpoint |
| `OTEL_SERVICE_NAME` | `ai-agent` | `service.name` 与 tracer 名称 |
| `OTEL_SAMPLING_RATE` | `1.0` | `ProbabilitySampler` 采样率 |
| `OTEL_BATCH_MAX_QUEUE` | `2048` | BatchSpanProcessor 最大队列 |
| `OTEL_BATCH_SCHEDULE_DELAY` | `5.0` | 批量导出间隔，单位秒 |
| `OTEL_BATCH_MAX_EXPORT` | `512` | 每批最大 Span 数 |

`OTEL_SAMPLING_RATE` 和三个批处理参数在模块导入时直接转为数字；非法值会使模块导入失败。部署配置应限制采样率在 `0.0` 到 `1.0` 之间，并保证 `OTEL_BATCH_MAX_EXPORT <= OTEL_BATCH_MAX_QUEUE`。

OTLP collector 通常接收 `/v1/traces`，部署时应将 `OTEL_OTLP_ENDPOINT` 设置为 collector 实际接受的完整 URL，例如 `http://otel-collector:4318/v1/traces`。

## 启用 Jaeger 导出

```bash
export OTEL_ENABLED=1
export OTEL_EXPORTER=jaeger
export OTEL_JAEGER_ENDPOINT=http://localhost:14268/api/traces
export OTEL_SERVICE_NAME=ai-agent
export OTEL_SAMPLING_RATE=1.0

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`configs/requirements.txt` 已声明 OpenTelemetry API、SDK、Jaeger Thrift exporter 和 OTLP exporter 依赖。

仓库根目录 `docker-compose.yml` 当前把 Jaeger 定义缩进在顶层 `networks` 块内，未形成可由 Compose 启动的 `services.jaeger`。使用 `docker compose up jaeger` 前应先修复 Compose 结构，或使用部署环境已有的 collector。

## 实际 Span

| Span 名称 | 代码范围 |
|-----------|----------|
| `orchestrator.initialize_components` | 初始化编排组件 |
| `orchestrator.generate` | 生成流程入口 |
| `orchestrator.traditional` | 传统生成流程 |
| `orchestrator.evaluate` | 评估流程 |
| `orchestrator.requirement_association` | 需求关联 |
| `specialist.call_llm` | Specialist LLM 调用 |
| `specialist.call_llm_with_tools` | Specialist 带工具 LLM 调用 |
| `architect.design` | 架构设计 |
| `frontend.generate_file` | 前端文件生成 |
| `frontend.analyze` | 前端分析 |
| `backend.generate_file` | 后端文件生成 |
| `backend.analyze` | 后端分析 |
| `reviewer.review_code` | 代码审查 |
| `test.run` | 测试执行 |
| `session.create` | 会话创建 |
| `session.resume` | 会话恢复 |
| `session.cleanup` | 会话清理 |
| `session.save` | 会话保存 |

Span 的父子关系取决于这些方法调用时是否存在当前 OpenTelemetry Context。当前实现没有为每个 HTTP 请求或 Celery 任务显式创建统一根 Span。

## 自动属性

`@traced` 自动写入：

- 装饰器声明的静态属性，例如 `component`、`role`、`mode`。
- `code.function`：被装饰函数名。
- 返回值为字典时，从 `success`、`model_name`、`file_path`、`complexity_level` 中提取已有字段，并写为 `result.<key>`。
- 异常时调用 `record_exception()`，并设置 `error=true` 和 `error.type` 后重新抛出异常。

敏感数据、提示词、模型完整响应和用户 API Key 不应写入 Span attributes 或 events。

## 代码用法

### 装饰器

```python
from app.agent.tracing import traced


@traced("example.process", attributes={"component": "example"})
async def process():
    return {"success": True}
```

### 手动 Span

```python
from app.agent.tracing import tracer


with tracer.start_as_current_span("example.validate") as span:
    span.set_attribute("validation.kind", "schema")
```

### 日志关联

```python
from app.agent.tracing import get_current_trace_id


trace_id = get_current_trace_id()
logger.info("validation started trace_id=%s", trace_id)
```

启用 OpenTelemetry 且当前存在有效 Span 时，函数返回 32 位十六进制 Trace ID。其他情况下返回 `set_trace_id()` 写入的 ContextVar 值或 `None`。

### HTTP 上下文注入

```python
from app.agent.tracing import inject_trace_context


headers = inject_trace_context({"Content-Type": "application/json"})
```

该函数只注入出站 W3C Trace Context。接收端还需配置上下文提取与 server Span，当前仓库没有对应接入。

## 运维核验

1. 启动日志出现 `OpenTelemetry enabled`，并显示 service、exporter 和 sampling rate。
2. collector 接口可从 API 容器网络访问。
3. 执行一个带 `@traced` 的 Agent 操作后查询 `service.name=ai-agent`。
4. 检查 BatchSpanProcessor 导出错误、队列堆积和 collector 拒绝日志。
5. 进程优雅关闭前调用 `shutdown_tracing()`，以降低批量 Span 丢失风险。

## 当前加固项

- 将 `shutdown_tracing()` 接入 FastAPI lifespan 的关闭阶段。
- 为 HTTP 与 Celery 入口建立根 Span，并在出站请求中调用 `inject_trace_context()`。
- 对采样率与批处理配置增加边界校验和错误回退。
- 修复 Compose 的 Jaeger 服务结构，再将 Jaeger UI 纳入本地观测拓扑。
- 按数据分类规则审核新增属性，避免采集凭据和用户内容。

## 相关文档

- [服务与端口](../guides/SERVICES.md)
- [安全概览](../security/SECURITY-OVERVIEW.md)
- [生产部署](../guides/PRODUCTION.md)
