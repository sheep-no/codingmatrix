"""
prompt_builder 模块单元测试
"""
import pytest
import json
from app.utils.prompt_builder import (
    PromptBuilder,
    PromptContext,
    get_prompt_builder,
    ordered_json_dumps,
)


class TestPromptContext:
    """PromptContext 测试"""

    def test_default_values(self):
        """测试默认值"""
        ctx = PromptContext()
        assert ctx.system_instructions == ""
        assert ctx.tool_definitions == ""
        assert ctx.spec_cache_content == ""
        assert ctx.project_context == ""
        assert ctx.task_instruction == ""
        assert ctx.conversation_history == []
        assert ctx.session_state == {}

    def test_custom_values(self):
        """测试自定义值"""
        ctx = PromptContext(
            system_instructions="你是 AI 助手",
            task_instruction="写代码",
        )
        assert ctx.system_instructions == "你是 AI 助手"
        assert ctx.task_instruction == "写代码"


class TestPromptBuilder:
    """PromptBuilder 测试"""

    def test_build_messages_basic(self):
        """测试基础消息构建"""
        builder = PromptBuilder()
        context = PromptContext(
            system_instructions="你是 AI 助手",
            task_instruction="写一个快速排序",
        )
        
        messages = builder.build_messages(context)
        
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "你是 AI 助手" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "写一个快速排序" in messages[1]["content"]

    def test_static_prefix_caching(self):
        """测试静态前缀缓存"""
        builder = PromptBuilder()
        context = PromptContext(
            system_instructions="固定指令",
            tool_definitions="工具定义",
            task_instruction="变化任务",
        )
        
        # 第一次构建
        messages1 = builder.build_messages(context)
        prefix1 = messages1[0]["content"]
        
        # 改变任务，但静态前缀相同
        context2 = PromptContext(
            system_instructions="固定指令",
            tool_definitions="工具定义",
            task_instruction="另一个任务",
        )
        
        # 第二次构建
        messages2 = builder.build_messages(context2)
        prefix2 = messages2[0]["content"]
        
        # 静态前缀应该相同
        assert prefix1 == prefix2

    def test_dynamic_variable_cleaning(self):
        """测试动态变量清理"""
        builder = PromptBuilder()
        
        content = "这是一个时间戳：timestamp:1234567890 和 uuid-12345678-1234"
        cleaned = builder._clean_dynamic_variables(content)
        
        assert "1234567890" not in cleaned
        assert "12345678-1234" not in cleaned

    def test_append_history(self):
        """测试追加历史"""
        builder = PromptBuilder()
        context = PromptContext(system_instructions="指令")
        
        builder.append_history(context, "user", "你好")
        builder.append_history(context, "assistant", "你好！")
        
        messages = builder.build_messages(context)
        
        assert len(messages) == 3  # system + 2 history
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "你好"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "你好！"

    def test_history_append_only(self):
        """测试历史仅追加"""
        builder = PromptBuilder()
        context = PromptContext(system_instructions="指令")
        
        builder.append_history(context, "user", "第一条")
        builder.append_history(context, "user", "第二条")
        
        assert len(context.conversation_history) == 2
        assert context.conversation_history[0]["content"] == "第一条"
        assert context.conversation_history[1]["content"] == "第二条"

    def test_json_key_ordering(self):
        """测试 JSON 键顺序固定"""
        obj = {
            "z_key": "z",
            "a_key": "a",
            "m_key": "m",
        }
        
        json1 = ordered_json_dumps(obj)
        json2 = ordered_json_dumps(obj)
        
        assert json1 == json2
        assert json1.index('"a_key"') < json1.index('"m_key"') < json1.index('"z_key"')

    def test_session_state_inclusion(self):
        """测试会话状态包含"""
        builder = PromptBuilder()
        context = PromptContext(
            system_instructions="指令",
            session_state={"step": 3, "files_created": ["a.py", "b.py"]},
        )
        
        messages = builder.build_messages(context)
        
        # 应该至少包含 system 和 user 消息
        assert len(messages) >= 2
        content = messages[-1]["content"]
        assert "当前会话状态" in content
        assert "step" in content

    def test_clear_cache(self):
        """测试清除缓存"""
        builder = PromptBuilder()
        context = PromptContext(system_instructions="指令")
        
        builder.build_messages(context)
        assert builder._static_prefix_cache is not None
        
        builder.clear_cache()
        assert builder._static_prefix_cache is None


class TestGetPromptBuilder:
    """获取 PromptBuilder 测试"""

    def test_singleton(self):
        """测试单例模式"""
        b1 = get_prompt_builder()
        b2 = get_prompt_builder()
        assert b1 is b2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
