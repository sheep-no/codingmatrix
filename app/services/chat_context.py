"""Model-aware context budgeting for the main chat pipeline."""

from dataclasses import dataclass

from app.agent.dynamic_model_router import get_context_length, get_max_output_tokens


_DEFAULT_CONTEXT_LENGTH = 32768
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ContextBudget:
    context_length: int
    max_output_tokens: int
    input_budget_tokens: int
    input_tokens: int
    truncated: bool


def _estimate_tokens(text: str) -> int:
    return max(0, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def fit_context(prompt: str, context: str, model: str, api_key_token: str = None):
    """Keep the user prompt intact and trim context to the model input budget."""
    context_length = get_context_length(model, api_key_token) or _DEFAULT_CONTEXT_LENGTH
    max_output = get_max_output_tokens(model, api_key_token=api_key_token)
    input_budget = max(256, context_length - max_output)
    prompt_tokens = _estimate_tokens(prompt)
    available_tokens = max(0, input_budget - prompt_tokens)
    available_chars = available_tokens * _CHARS_PER_TOKEN
    trimmed = len(context) > available_chars
    if trimmed:
        context = context[-available_chars:] if available_chars else ""
    return context, ContextBudget(
        context_length=context_length,
        max_output_tokens=max_output,
        input_budget_tokens=input_budget,
        input_tokens=_estimate_tokens(prompt + context),
        truncated=trimmed,
    )


def is_context_length_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in (
        "context length", "context_length", "maximum context", "too many tokens",
        "prompt is too long", "input token limit", "max_tokens",
    ))
