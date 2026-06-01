"""
测试架构师 JSON 解析器的鲁棒性

模拟 LLM 模型可能产生的各种非标准 JSON 输出格式，
验证并增强 _safe_parse_json 的解析能力。
"""

import pytest
from app.agent.specialists import Architect


@pytest.fixture
def architect():
    """创建架构师实例"""
    return Architect(
        role_name="Architect",
        model_name="Qwen/Qwen3-8B",
        task_type="generate"
    )


class TestJsonParsingRobustness:
    """JSON 解析鲁棒性测试"""

    def test_standard_json(self, architect):
        """测试标准 JSON"""
        result = architect._safe_parse_json('{"project_type": "full-stack", "file_plan": []}')
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_json_with_thinking_tags(self, architect):
        """测试带 thinking tags 的 JSON"""
        text = '<think>这是思考过程</think>\n{"project_type": "full-stack", "file_plan": []}'
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_json_with_markdown_code_block(self, architect):
        """测试带 markdown 代码块的 JSON"""
        text = '```json\n{"project_type": "full-stack", "file_plan": []}\n```'
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_json_with_text_surrounding(self, architect):
        """测试带文字说明的 JSON"""
        text = '好的，我来设计架构。\n\n{"project_type": "full-stack", "file_plan": []}\n\n以上就是架构设计。'
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_invalid_json_returns_none(self, architect):
        """测试无效 JSON 返回 None"""
        import pytest
        with pytest.raises(ValueError):
            architect._safe_parse_json('not json at all')

    def test_partial_json(self, architect):
        """测试部分 JSON - 解析器现在能自动修复部分 JSON"""
        result = architect._safe_parse_json('{"project_type": "full-stack"')
        assert result is not None
        assert result.get("project_type") == "full-stack"

    def test_json_with_trailing_comma(self, architect):
        """测试带尾随逗号的 JSON"""
        text = '{"project_type": "full-stack", "file_plan": [],}'
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_json_with_single_quotes(self, architect):
        """测试带单引号的 JSON"""
        text = "{'project_type': 'full-stack', 'file_plan': []}"
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_json_with_comments(self, architect):
        """测试带注释的 JSON"""
        text = '''{
            // 这是注释
            "project_type": "full-stack",
            "file_plan": []
        }'''
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project_type"] == "full-stack"

    def test_nested_json(self, architect):
        """测试嵌套 JSON"""
        text = '{"project": {"type": "full-stack", "files": []}}'
        result = architect._safe_parse_json(text)
        assert result is not None
        assert result["project"]["type"] == "full-stack"
