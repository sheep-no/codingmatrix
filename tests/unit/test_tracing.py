import pytest

class TestTracing:
    def test_traced_decorator(self):
        from app.agent.tracing import traced, tracer
        
        @traced("test.operation")
        def test_func():
            return 42
        
        result = test_func()
        assert result == 42
    
    def test_trace_id_propagation(self):
        from app.agent.tracing import set_trace_id, get_current_trace_id
        
        set_trace_id("test-trace-123")
        trace_id = get_current_trace_id()
        assert trace_id == "test-trace-123"
