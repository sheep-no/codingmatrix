# OpenTelemetry 分布式追踪指南

> 最后更新: 2026-05-26 | 版本：v5.9.0

## 概述

CodingMatrix v5.9.0 集成 OpenTelemetry 分布式追踪能力，用于可视化 Agent 调用链、诊断性能瓶颈、分析错误分布。v5.9.0 新增 API Key 使用追踪和 Token 消耗统计。

### 架构组件

```
┌─────────────────┐ ┌──────────────────┐ ┌─────────────────┐
│ Agent 应用 │────>│ OTel SDK │────>│ Jaeger │
│ (Python 3.11) │ │ (tracing.py) │ │ (All-in-One) │
│ │ │ │ │ :16686 UI │
│ @traced() │ │ BatchProcessor │ │ :14268 HTTP │
│ tracer.start() │ │ Sampler │ │ :14250 gRPC │
└─────────────────┘ └──────────────────┘ └─────────────────┘
```

## 快速开始

### 1. 启动 Jaeger

```bash
docker compose up -d jaeger
```

访问 http://localhost:16686 查看 Jaeger UI。

### 2. 启用追踪

```bash
export OTEL_ENABLED=1
export OTEL_EXPORTER=jaeger
export OTEL_JAEGER_ENDPOINT=http://localhost:14268/api/traces
```

### 3. 运行应用

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

触发一次项目生成操作后，在 Jaeger UI 中即可看到完整的调用链。

## 配置项

| 环境变量 | 默认值 | 描述 |
|----------|--------|------|
| `OTEL_ENABLED` | `""` (关闭) | 设为 `1` / `true` 启用追踪 |
| `OTEL_EXPORTER` | `jaeger` | 导出目标: `jaeger` / `otlp` / `none` |
| `OTEL_JAEGER_ENDPOINT` | `http://jaeger:14268/api/traces` | Jaeger HTTP 收集器地址 |
| `OTEL_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP HTTP 端点 |
| `OTEL_SERVICE_NAME` | `ai-agent` | 服务名称 |
| `OTEL_SAMPLING_RATE` | `1.0` | 采样率 (0.0~1.0)，1.0 表示全部采样 |
| `OTEL_BATCH_MAX_QUEUE` | `2048` | 批量处理器最大队列大小 |
| `OTEL_BATCH_SCHEDULE_DELAY` | `5.0` | 批量导出间隔 (秒) |
| `OTEL_BATCH_MAX_EXPORT` | `512` | 每次批量导出的最大 Span 数 |

## 使用方式

### 装饰器方式 (推荐)

```python
from app.agent.tracing import traced

@traced("my_operation", attributes={"component": "my_module"})
async def my_function():
 ...
```

### 手动方式

```python
from app.agent.tracing import tracer

with tracer.start_as_current_span("my_span") as span:
 span.set_attribute("key", "value")
 # 业务逻辑...
```

### 获取当前 Trace ID

用于日志关联：

```python
from app.agent.tracing import get_current_trace_id

trace_id = get_current_trace_id()
logger.info(f"trace_id={trace_id} 开始处理请求")
```

## 已追踪方法

### Orchestrator (orchestrator.py)

| Span 名称 | 描述 |
|-----------|------|
| `orchestrator.generate` | 项目生成主入口 |
| `orchestrator.initialize_components` | 组件初始化 (复杂度分析 + 模型分配 + 角色创建) |
| `orchestrator.traditional` | 传统生成策略 |

### Specialists (specialists.py)

| Span 名称 | 描述 |
|-----------|------|
| `specialist.call_llm` | LLM 调用 (所有角色基类方法) |
| `architect.design` | 架构设计 |
| `frontend.generate_file` | 前端文件生成 |
| `backend.generate_file` | 后端文件生成 |
| `reviewer.review_code` | 代码审查 |

### Session (session_manager.py)

| Span 名称 | 描述 |
|-----------|------|
| `session.create` | 创建会话 |
| `session.resume` | 恢复会话 |
| `session.save` | 保存会话状态 |
| `session.cleanup` | 清理过期会话 |

### Testing (test_runner.py)

| Span 名称 | 描述 |
|-----------|------|
| `test.run` | 执行沙箱测试 |

## Jaeger UI 使用

1. 访问 http://localhost:16686
2. Service 选择 `ai-agent`
3. Operation 选择具体操作名 (如 `orchestrator.generate`)
4. 点击 **Find Traces** 查看追踪结果
5. 点击具体 Trace 查看 Span 树和详细信息

### 可查看的信息

- **Span 耗时**: 每个操作的执行时间
- **Span 属性**: 模型名称、文件路径、复杂度等级等
- **错误信息**: 异常类型和堆栈跟踪
- **Trace 拓扑**: 完整的调用链关系

## 生产部署

### Docker Compose

`docker-compose.yml` 已包含 Jaeger 服务，默认不启动。生产环境可单独部署：

```bash
docker compose up -d jaeger
```

### 独立 Jaeger 集群

生产环境建议使用 Jaeger 集群而非 all-in-one：

```yaml
# docker-compose.prod.yml
services:
 jaeger-collector:
 image: jaegertracing/jaeger-collector:latest
 ports:
 - "14268:14268"
 environment:
 - SPAN_STORAGE_TYPE=elasticsearch
 - ES_SERVER_URLS=http://elasticsearch:9200

 jaeger-query:
 image: jaegertracing/jaeger-query:latest
 ports:
 - "16686:16686"
 environment:
 - SPAN_STORAGE_TYPE=elasticsearch
 - ES_SERVER_URLS=http://elasticsearch:9200
```

### OTLP 导出

如果使用 OpenTelemetry Collector：

```bash
export OTEL_EXPORTER=otlp
export OTEL_OTLP_ENDPOINT=http://otel-collector:4318
```

## 依赖

新增 Python 依赖 (已添加到 `configs/requirements.txt`)：

```
opentelemetry-api==1.29.0
opentelemetry-sdk==1.29.0
opentelemetry-exporter-jaeger-thrift==1.21.0
opentelemetry-exporter-otlp-proto-http==1.29.0
```

## 注意事项

1. **性能影响**: 开启追踪会增加少量开销，生产环境建议设置 `OTEL_SAMPLING_RATE=0.1` (10% 采样)
2. **No-op 降级**: 未安装 OTel 依赖或未启用时，自动降级为 No-op，不影响业务逻辑
3. **优雅关闭**: 应用退出时调用 `shutdown_tracing()` 确保 pending spans 全部导出
4. **敏感信息**: Span 属性中不会记录密钥、密码等敏感内容
