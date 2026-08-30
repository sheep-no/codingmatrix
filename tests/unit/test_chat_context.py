from app.services.chat_context import fit_context, is_context_length_error


def test_fit_context_preserves_prompt_and_trims_context(monkeypatch):
    monkeypatch.setattr("app.services.chat_context.get_context_length", lambda *_: 1024)
    monkeypatch.setattr("app.services.chat_context.get_max_output_tokens", lambda *_args, **_kwargs: 256)

    context, budget = fit_context("用户问题", "x" * 5000, "test-model")

    assert len(context) <= (1024 - 256 - 1) * 4
    assert budget.truncated is True
    assert budget.input_tokens <= budget.input_budget_tokens


def test_context_length_error_detection():
    assert is_context_length_error(RuntimeError("maximum context length exceeded"))
    assert not is_context_length_error(RuntimeError("provider unavailable"))
