"""
OpenTelemetry (Jaeger) 追踪模块

为 Agent 调用链提供分布式追踪能力：
- 每个 generate 任务作为一个 Trace
- 架构设计、文件生成、验证、审查、错误恢复作为子 Span
- 关键属性（模型名、文件路径、耗时）记录到 Span attributes

配置方式（环境变量）：
  OTEL_ENABLED=1              启用追踪（默认关闭）
  OTEL_EXPORTER=jaeger        导出目标（jaeger / otlp / none）
  OTEL_JAEGER_ENDPOINT=http://jaeger:14268/api/traces  Jaeger HTTP 端点
  OTEL_SERVICE_NAME=ai-agent  服务名
  OTEL_SAMPLING_RATE=1.0      采样率（0.0~1.0）

使用方式：
  from app.agent.tracing import tracer, traced

  @traced("generate_file")
  async def generate_file(path, content):
      ...

  # 或手动创建 Span
  with tracer.start_as_current_span("validate") as span:
      span.set_attribute("file.path", path)
      ...
"""

import os
import functools
import asyncio
import logging
from contextvars import ContextVar
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

_otel_enabled: bool = os.environ.get("OTEL_ENABLED", "").strip() in ("1", "true", "True")
_otel_exporter: str = os.environ.get("OTEL_EXPORTER", "jaeger")
_jaeger_endpoint: str = os.environ.get("OTEL_JAEGER_ENDPOINT", "http://jaeger:14268/api/traces")
_otlp_endpoint: str = os.environ.get("OTEL_OTLP_ENDPOINT", "http://otel-collector:4318")
_service_name: str = os.environ.get("OTEL_SERVICE_NAME", "ai-agent")
_sampling_rate: float = float(os.environ.get("OTEL_SAMPLING_RATE", "1.0"))

_current_trace_id: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)

tracer: Any = None
_tracer_provider: Any = None


def _make_batch_processor(exporter):
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    max_queue = int(os.environ.get("OTEL_BATCH_MAX_QUEUE", "2048"))
    schedule_delay = float(os.environ.get("OTEL_BATCH_SCHEDULE_DELAY", "5.0"))
    max_export = int(os.environ.get("OTEL_BATCH_MAX_EXPORT", "512"))
    return BatchSpanProcessor(
        exporter,
        max_queue_size=max_queue,
        schedule_delay_millis=int(schedule_delay * 1000),
        max_export_batch_size=max_export,
    )


if _otel_enabled:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ProbabilitySampler
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": _service_name})
        _tracer_provider = TracerProvider(
            sampler=ProbabilitySampler(rate=_sampling_rate),
            resource=resource,
        )

        if _otel_exporter == "jaeger":
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter
            _tracer_provider.add_span_processor(
                _make_batch_processor(JaegerExporter(
                    collector_endpoint=_jaeger_endpoint,
                ))
            )
            logger.info(f"OTel Jaeger exporter configured: {_jaeger_endpoint}")
        elif _otel_exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            _tracer_provider.add_span_processor(
                _make_batch_processor(OTLPSpanExporter(
                    endpoint=_otlp_endpoint,
                ))
            )
            logger.info(f"OTel OTLP exporter configured: {_otlp_endpoint}")
        elif _otel_exporter == "none":
            logger.info("OTel exporter set to 'none' - spans will be recorded but not exported")
        else:
            logger.warning(f"Unknown OTEL_EXPORTER={_otel_exporter}, falling back to jaeger")
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter
            _tracer_provider.add_span_processor(
                _make_batch_processor(JaegerExporter(
                    collector_endpoint=_jaeger_endpoint,
                ))
            )

        trace.set_tracer_provider(_tracer_provider)
        tracer = trace.get_tracer(_service_name)
        logger.info(f"OpenTelemetry enabled: service={_service_name}, exporter={_otel_exporter}, rate={_sampling_rate}")

    except ImportError:
        logger.warning("OpenTelemetry packages not installed - tracing disabled. Install: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger-thrift")
        _otel_enabled = False
        tracer = None
else:
    logger.info("OpenTelemetry disabled (OTEL_ENABLED not set)")


class _NoopSpan:
    """No-op Span 替身，OTel 未启用时使用"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, key, value):
        pass

    def add_event(self, name, attributes=None):
        pass

    def record_exception(self, exception, attributes=None):
        pass

    def is_recording(self):
        return False

    def end(self):
        pass


class _NoopTracer:
    """No-op Tracer 替身"""

    def start_as_current_span(self, name, attributes=None, record_exception=True, set_status_on_exception=True):
        return _NoopSpan()

    def start_span(self, name, attributes=None):
        return _NoopSpan()


if tracer is None:
    tracer = _NoopTracer()


def traced(span_name: str, attributes: Optional[dict] = None):
    """
    装饰器：为 async/sync 函数自动创建 Span

    用法：
        @traced("generate_file", attributes={"component": "orchestrator"})
        async def generate_file(self, path, content):
            ...
    """
    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                # 记录函数名和调用位置
                span.set_attribute("code.function", func.__name__)
                try:
                    result = await func(*args, **kwargs)
                    _set_result_attrs(span, result)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(exc).__name__)
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                span.set_attribute("code.function", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    _set_result_attrs(span, result)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(exc).__name__)
                    raise

        return async_wrapper if is_async else sync_wrapper
    return decorator


def _set_result_attrs(span, result):
    """从返回值提取常见属性写入 Span"""
    if isinstance(result, dict):
        for key in ("success", "model_name", "file_path", "complexity_level"):
            if key in result:
                span.set_attribute(f"result.{key}", result[key])


def get_current_trace_id() -> Optional[str]:
    """获取当前 Trace ID（用于日志关联）"""
    if _otel_enabled and tracer is not None:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.trace_id != 0:
            return format(ctx.trace_id, "032x")
    return _current_trace_id.get()


def set_trace_id(trace_id: str):
    _current_trace_id.set(trace_id)


def shutdown_tracing():
    """优雅关闭 TracerProvider，flush 所有 pending spans"""
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        logger.info("OpenTelemetry TracerProvider shutdown complete")


def inject_trace_context(headers: dict) -> dict:
    """将当前 trace context 注入 HTTP headers（用于跨服务传播）"""
    if not _otel_enabled:
        return headers
    try:
        from opentelemetry.trace.propagation import TraceContextPropagator
        propagator = TraceContextPropagator()
        propagator.inject(headers)
    except Exception as e:
        logger.warning(f"Failed to inject trace context: {e}")
    return headers
