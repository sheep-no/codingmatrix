from app.services.girlai_companion_context import build_companion_context


def test_context_filters_unauthorized_and_unconfirmed_memories():
    context = build_companion_context(
        character={"name": "姬", "description": "陪伴", "personality": "稳重"},
        user_prompt="继续计划",
        memories=[
            {"key": "工作", "value": "开发", "status": "confirmed", "visibility": "companion_allowed"},
            {"key": "住址", "value": "某地", "status": "confirmed", "visibility": "private"},
            {"key": "候选", "value": "待确认", "status": "candidate", "visibility": "companion_allowed"},
        ],
        allowed_memory_visibility={"companion_allowed"},
    )

    assert [memory["key"] for memory in context.memories] == ["工作"]
    assert "工作：开发" in context.prompt
    assert "住址：某地" not in context.prompt
    assert "候选：待确认" not in context.prompt


def test_context_preserves_prompt_and_prioritizes_recent_context_when_trimmed():
    context = build_companion_context(
        character={"name": "姬", "description": "陪伴", "personality": "稳重"},
        user_prompt="必须保留的当前输入",
        history_summary="旧摘要" * 100,
        recent_messages=[{"role": "user", "content": "旧消息" * 200}],
        max_input_tokens=20,
    )

    assert context.truncated is True
    assert "必须保留的当前输入" in context.prompt
    assert context.estimated_tokens <= 25
