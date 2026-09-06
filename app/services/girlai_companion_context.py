"""Context assembly for the GirlAI companion pipeline."""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.services.chat_context import _estimate_tokens


@dataclass(frozen=True)
class CompanionContext:
    """Budgeted context with explicit source groups for observability."""

    prompt: str
    messages: list[dict[str, str]]
    memories: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    sources: list[str]
    estimated_tokens: int
    truncated: bool


def build_companion_context(
    *,
    character: Mapping[str, Any],
    user_prompt: str,
    recent_messages: Sequence[Mapping[str, str]] = (),
    history_summary: str | None = None,
    memories: Sequence[Mapping[str, Any]] = (),
    tasks: Sequence[Mapping[str, Any]] = (),
    allowed_memory_visibility: set[str] | None = None,
    max_input_tokens: int = 6000,
) -> CompanionContext:
    """Build context in priority order while preserving the user prompt."""
    allowed = allowed_memory_visibility or {"conversation_only", "companion_allowed"}
    selected_memories = [
        dict(memory)
        for memory in memories
        if memory.get("status", "confirmed") == "confirmed"
        and memory.get("visibility", "companion_allowed") in allowed
    ]
    selected_tasks = [dict(task) for task in tasks]
    selected_messages = [
        {"role": str(message.get("role", "user")), "content": str(message.get("content", ""))}
        for message in recent_messages
        if message.get("content")
    ]

    sections = [
        f"你是{character.get('name', '虚拟姬')}，{character.get('description', '')}",
        f"性格：{character.get('personality', '')}",
        f"说话风格：{character.get('speaking_style', '')}",
    ]
    if history_summary:
        sections.extend(["【较早对话摘要】", history_summary])
    if selected_memories:
        sections.append("【已授权记忆】")
        sections.extend(f"- {m.get('key', '')}：{m.get('value', '')}" for m in selected_memories)
    if selected_tasks:
        sections.append("【活动任务】")
        sections.extend(f"- {t.get('title', t.get('name', '未命名任务'))}：{t.get('status', 'unknown')}" for t in selected_tasks)
    if selected_messages:
        sections.append("【近期对话】")
        sections.extend(f"{m['role']}：{m['content']}" for m in selected_messages)
    sections.extend(["【当前输入】", user_prompt])

    full_text = "\n".join(sections)
    truncated = False
    budget_chars = max_input_tokens * 4
    if len(full_text) > budget_chars:
        truncated = True
        # Keep role instructions and the current input intact, trim history first.
        preserved = "\n".join(sections[:3] + sections[-2:])
        remaining = max(0, budget_chars - len(preserved) - 1)
        history_text = "\n".join(sections[3:-2])[-remaining:]
        full_text = "\n".join([*sections[:3], history_text, *sections[-2:]])

    sources = ["character", "prompt"]
    if history_summary:
        sources.append("summary")
    if selected_memories:
        sources.append("memories")
    if selected_tasks:
        sources.append("tasks")
    if selected_messages:
        sources.append("messages")
    return CompanionContext(
        prompt=full_text,
        messages=selected_messages,
        memories=selected_memories,
        tasks=selected_tasks,
        sources=sources,
        estimated_tokens=_estimate_tokens(full_text),
        truncated=truncated,
    )


__all__ = ["CompanionContext", "build_companion_context"]
