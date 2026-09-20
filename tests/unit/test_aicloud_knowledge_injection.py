"""RAG 知识库上下文注入系统提示词的回归测试。

历史上 `chat` 端点检索出 `knowledge_context` 后从未把它传给 LLM（拼好的
`full_prompt` 被丢弃），知识库功能形同虚设，且因为没有断言模型输入的测试
而长期潜伏。这里锁定注入行为。
"""

from app.api.v1.aicloud import _compose_system_prompt


class TestComposeSystemPrompt:
    """知识库上下文注入"""

    def test_injects_knowledge_before_system_prompt(self):
        result = _compose_system_prompt("你是助手", "**相关知识库内容**:\n答案片段")
        assert result == "**相关知识库内容**:\n答案片段你是助手"
        assert result.endswith("你是助手")

    def test_returns_prompt_unchanged_without_knowledge(self):
        assert _compose_system_prompt("你是助手", "") == "你是助手"

    def test_handles_none_knowledge_context(self):
        assert _compose_system_prompt("你是助手", None) == "你是助手"
