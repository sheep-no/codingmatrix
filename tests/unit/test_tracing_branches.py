"""Branch coverage for app/agent/tracing.py."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.agent.tracing as tracing


class _Span:
    def __init__(self):
        self.attributes = {}
        self.exceptions = []
        self.ended = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def add_event(self, name, attributes=None):
        pass

    def record_exception(self, exception, attributes=None):
        self.exceptions.append(exception)

    def is_recording(self):
        return True

    def end(self):
        self.ended = True


class _Tracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name, attributes=None, record_exception=True, set_status_on_exception=True):
        span = _Span()
        self.spans.append(span)
        return span

    def start_span(self, name, attributes=None):
        span = _Span()
        self.spans.append(span)
        return span


@pytest.fixture
def fake_tracer(monkeypatch):
    tracer = _Tracer()
    monkeypatch.setattr(tracing, "tracer", tracer)
    return tracer


class TestNoop:
    def test_noop_span_contract(self):
        span = tracing._NoopSpan()
        assert span.__enter__() is span
        assert span.__exit__(None, None, None) is False
        span.set_attribute("a", 1)
        span.add_event("e")
        span.record_exception(ValueError())
        assert span.is_recording() is False
        span.end()

    def test_noop_tracer_returns_spans(self):
        tracer = tracing._NoopTracer()
        assert isinstance(tracer.start_as_current_span("x"), tracing._NoopSpan)
        assert isinstance(tracer.start_span("x"), tracing._NoopSpan)


class TestTracedDecorator:
    def test_sync_success_with_attributes(self, fake_tracer):
        @tracing.traced("op", attributes={"component": "x"})
        def fn():
            return {"success": True, "model_name": "m", "other": 1}

        result = fn()

        assert result["success"] is True
        span = fake_tracer.spans[0]
        assert span.attributes["component"] == "x"
        assert span.attributes["code.function"] == "fn"
        assert span.attributes["result.success"] is True
        assert span.attributes["result.model_name"] == "m"
        assert "result.other" not in span.attributes

    def test_sync_non_dict_result(self, fake_tracer):
        @tracing.traced("op")
        def fn():
            return 5

        assert fn() == 5

    def test_sync_exception_records(self, fake_tracer):
        @tracing.traced("op")
        def fn():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            fn()

        span = fake_tracer.spans[0]
        assert span.attributes["error"] is True
        assert span.attributes["error.type"] == "ValueError"
        assert len(span.exceptions) == 1

    @pytest.mark.asyncio
    async def test_async_success(self, fake_tracer):
        @tracing.traced("op", attributes={"a": 1})
        async def fn():
            return {"file_path": "x.py", "complexity_level": "simple"}

        result = await fn()

        assert result["file_path"] == "x.py"
        span = fake_tracer.spans[0]
        assert span.attributes["result.file_path"] == "x.py"
        assert span.attributes["result.complexity_level"] == "simple"

    @pytest.mark.asyncio
    async def test_async_exception_records(self, fake_tracer):
        @tracing.traced("op")
        async def fn():
            raise RuntimeError("x")

        with pytest.raises(RuntimeError):
            await fn()

        span = fake_tracer.spans[0]
        assert span.attributes["error.type"] == "RuntimeError"


class TestTraceId:
    def test_otel_disabled_uses_context_var(self, monkeypatch):
        monkeypatch.setattr(tracing, "_otel_enabled", False)
        tracing.set_trace_id("abc")
        assert tracing.get_current_trace_id() == "abc"

    def test_otel_enabled_with_trace_id(self, monkeypatch):
        monkeypatch.setattr(tracing, "_otel_enabled", True)
        span = SimpleNamespace(
            get_span_context=lambda: SimpleNamespace(trace_id=5)
        )
        fake_trace = SimpleNamespace(get_current_span=lambda: span)
        monkeypatch.setitem(sys.modules, "opentelemetry", SimpleNamespace(trace=fake_trace))
        monkeypatch.setitem(sys.modules, "opentelemetry.trace", fake_trace)
        monkeypatch.setattr(tracing, "tracer", object())

        assert tracing.get_current_trace_id() == format(5, "032x")

    def test_otel_enabled_zero_trace_id_falls_back(self, monkeypatch):
        monkeypatch.setattr(tracing, "_otel_enabled", True)
        span = SimpleNamespace(get_span_context=lambda: SimpleNamespace(trace_id=0))
        fake_trace = SimpleNamespace(get_current_span=lambda: span)
        monkeypatch.setitem(sys.modules, "opentelemetry", SimpleNamespace(trace=fake_trace))
        monkeypatch.setitem(sys.modules, "opentelemetry.trace", fake_trace)
        monkeypatch.setattr(tracing, "tracer", object())
        tracing.set_trace_id("fallback")

        assert tracing.get_current_trace_id() == "fallback"

    def test_otel_enabled_but_tracer_none(self, monkeypatch):
        monkeypatch.setattr(tracing, "_otel_enabled", True)
        monkeypatch.setattr(tracing, "tracer", None)
        tracing.set_trace_id("ctx")
        assert tracing.get_current_trace_id() == "ctx"


class TestShutdownAndInject:
    def test_shutdown_with_provider(self, monkeypatch):
        provider = MagicMock()
        monkeypatch.setattr(tracing, "_tracer_provider", provider)
        tracing.shutdown_tracing()
        provider.shutdown.assert_called_once()

    def test_shutdown_without_provider(self, monkeypatch):
        monkeypatch.setattr(tracing, "_tracer_provider", None)
        tracing.shutdown_tracing()

    def test_inject_disabled_returns_headers(self, monkeypatch):
        monkeypatch.setattr(tracing, "_otel_enabled", False)
        headers = {"a": "b"}
        assert tracing.inject_trace_context(headers) is headers

    def test_inject_success(self, monkeypatch):
        class _Propagator:
            def inject(self, headers):
                headers["traceparent"] = "t"

        fake = SimpleNamespace(TraceContextPropagator=_Propagator)
        monkeypatch.setitem(sys.modules, "opentelemetry", SimpleNamespace(trace=SimpleNamespace(propagation=fake)))
        monkeypatch.setitem(sys.modules, "opentelemetry.trace", SimpleNamespace(propagation=fake))
        monkeypatch.setitem(sys.modules, "opentelemetry.trace.propagation", fake)
        monkeypatch.setattr(tracing, "_otel_enabled", True)

        headers = tracing.inject_trace_context({})

        assert headers["traceparent"] == "t"

    def test_inject_failure_logs_warning(self, monkeypatch):
        class _Propagator:
            def inject(self, headers):
                raise RuntimeError("boom")

        fake = SimpleNamespace(TraceContextPropagator=_Propagator)
        monkeypatch.setitem(sys.modules, "opentelemetry", SimpleNamespace(trace=SimpleNamespace(propagation=fake)))
        monkeypatch.setitem(sys.modules, "opentelemetry.trace", SimpleNamespace(propagation=fake))
        monkeypatch.setitem(sys.modules, "opentelemetry.trace.propagation", fake)
        monkeypatch.setattr(tracing, "_otel_enabled", True)
        fake_logger = MagicMock()
        monkeypatch.setattr(tracing, "logger", fake_logger)

        headers = tracing.inject_trace_context({"x": "1"})

        assert headers["x"] == "1"
        assert fake_logger.warning.called


class TestBatchProcessor:
    def test_make_batch_processor_uses_env(self, monkeypatch):
        captured = {}

        class _Processor:
            def __init__(self, exporter, **kwargs):
                captured.update(kwargs)

        import opentelemetry.sdk.trace.export as export_module

        monkeypatch.setattr(export_module, "BatchSpanProcessor", _Processor)
        monkeypatch.setenv("OTEL_BATCH_MAX_QUEUE", "100")
        monkeypatch.setenv("OTEL_BATCH_SCHEDULE_DELAY", "1.5")
        monkeypatch.setenv("OTEL_BATCH_MAX_EXPORT", "10")

        tracing._make_batch_processor(object())

        assert captured == {
            "max_queue_size": 100,
            "schedule_delay_millis": 1500,
            "max_export_batch_size": 10,
        }


class TestEnvIntAndSamplingRate:
    def test_env_int_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv("OTEL_TEST_INT_BAD", "x")
        assert tracing._env_int("OTEL_TEST_INT_BAD", 9) == 9

    def test_parse_sampling_rate_non_finite(self, monkeypatch):
        import math

        monkeypatch.setattr(tracing, "_env_float", lambda name, default: math.nan)
        assert tracing._parse_sampling_rate() == 1.0

    def test_parse_sampling_rate_clamps_high(self, monkeypatch):
        monkeypatch.setattr(tracing, "_env_float", lambda name, default: 5.0)
        assert tracing._parse_sampling_rate() == 1.0

    def test_parse_sampling_rate_clamps_low(self, monkeypatch):
        monkeypatch.setattr(tracing, "_env_float", lambda name, default: -3.0)
        assert tracing._parse_sampling_rate() == 0.0


@pytest.fixture
def reload_module():
    import importlib

    yield importlib.reload
    importlib.reload(tracing)


class TestModuleEnablement:
    def _reload(self, monkeypatch, reload_module, exporter):
        monkeypatch.setenv("OTEL_ENABLED", "1")
        monkeypatch.setenv("OTEL_EXPORTER", exporter)
        monkeypatch.setenv("OTEL_SAMPLING_RATE", "0.5")
        return reload_module(tracing)

    def test_enable_jaeger(self, monkeypatch, reload_module):
        mod = self._reload(monkeypatch, reload_module, "jaeger")
        assert mod._otel_enabled is True
        assert mod.tracer is not None
        assert mod._tracer_provider is not None

    def test_enable_otlp(self, monkeypatch, reload_module):
        mod = self._reload(monkeypatch, reload_module, "otlp")
        assert mod._otel_enabled is True
        assert mod.tracer is not None

    def test_enable_none_exporter(self, monkeypatch, reload_module):
        mod = self._reload(monkeypatch, reload_module, "none")
        assert mod._otel_enabled is True
        assert mod._tracer_provider is not None

    def test_enable_unknown_exporter_falls_back(self, monkeypatch, reload_module):
        mod = self._reload(monkeypatch, reload_module, "unknown-exporter")
        assert mod._otel_enabled is True
        assert mod._tracer_provider is not None

    def test_enable_with_import_error(self, monkeypatch, reload_module):
        monkeypatch.setenv("OTEL_ENABLED", "1")
        monkeypatch.setenv("OTEL_EXPORTER", "jaeger")
        monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", None)
        try:
            mod = reload_module(tracing)
            assert mod._otel_enabled is False
            assert isinstance(mod.tracer, mod._NoopTracer)
        finally:
            sys.modules.pop("opentelemetry.sdk.resources", None)
