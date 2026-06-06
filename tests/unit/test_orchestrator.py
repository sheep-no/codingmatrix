"""
Orchestrator 核心流程单元测试
测试复杂度分析、依赖图、代码验证、JSON 解析、模型路由、记忆系统、ReAct 引擎
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.complexity import ComplexityAnalyzer, ProjectComplexity
from app.agent.dependency_graph import DependencyGraph
from app.agent.code_validator import CodeValidator
from app.agent.architect_json_parser import ArchitectJsonParser
from app.agent.dynamic_model_router import (
    DynamicModelRouter,
    ModelAssignment,
    _LayeredModelRouterCompat,
    load_agent_model_config,
)
from app.agent.memory import (
    ConversationMemory,
    KnowledgeMemory,
    ReflectionMemory,
    MemoryEntry,
)
from app.agent.react_engine import ReActEngine


class TestComplexityAnalyzer:
    """复杂度分析器测试"""

    def test_simple_complexity(self):
        """简单需求应返回 SIMPLE 级别"""
        result = ComplexityAnalyzer.analyze("写一个 hello world 脚本")
        assert result.level == ProjectComplexity.SIMPLE
        assert result.estimated_files <= 3

    def test_medium_complexity(self):
        """全栈项目需求应返回 MEDIUM 或更高"""
        result = ComplexityAnalyzer.analyze("Vue 3 + FastAPI 全栈项目带用户登录")
        assert result.level in (
            ProjectComplexity.MEDIUM,
            ProjectComplexity.LARGE,
            ProjectComplexity.ENTERPRISE,
        )
        assert result.has_frontend is True
        assert result.has_backend is True

    def test_complexity_with_database(self):
        """含数据库关键词的需求应识别 has_database"""
        result = ComplexityAnalyzer.analyze("创建一个带数据库的博客系统")
        assert result.has_database is True
        assert "需要数据库设计和迁移" in result.risk_factors

    def test_complexity_with_auth(self):
        """含登录关键词的需求应识别 has_auth"""
        result = ComplexityAnalyzer.analyze("实现用户登录注册功能")
        assert result.has_auth is True
        assert "需要用户认证系统" in result.risk_factors


class TestDependencyGraph:
    """依赖图测试"""

    def test_empty_graph(self):
        """空图拓扑排序返回空列表"""
        graph = DependencyGraph()
        order = graph.get_generation_order()
        assert order == []

    def test_simple_dependency(self):
        """A→B 排序后 B 在 A 之后"""
        graph = DependencyGraph()
        graph.add_file("a.py", file_type="config")
        graph.add_file("b.py", file_type="model")
        graph.add_dependency("b.py", "a.py")

        order = graph.get_generation_order()
        assert order.index("a.py") < order.index("b.py")

    def test_circular_dependency(self):
        """循环依赖应能检测并打破"""
        graph = DependencyGraph()
        graph.add_file("a.py", file_type="service")
        graph.add_file("b.py", file_type="service")
        graph.add_dependency("a.py", "b.py")
        graph.add_dependency("b.py", "a.py")

        order = graph.get_generation_order()
        assert len(order) == 2
        assert "a.py" in order
        assert "b.py" in order


class TestCodeValidator:
    """代码验证器测试"""

    @pytest.mark.asyncio
    async def test_valid_python(self, tmp_path):
        """合法 Python 代码验证通过"""
        validator = CodeValidator(project_path=tmp_path)
        code_file = tmp_path / "valid.py"
        code_file.write_text("def hello():\n    return 'world'\n")

        is_valid, errors = await validator.validate_syntax(code_file)
        assert is_valid is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_invalid_python(self, tmp_path):
        """非法 Python 代码应报错"""
        validator = CodeValidator(project_path=tmp_path)
        code_file = tmp_path / "invalid.py"
        code_file.write_text("def hello(\n    return 'world'\n")

        is_valid, errors = await validator.validate_syntax(code_file)
        assert is_valid is False
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_valid_javascript(self, tmp_path):
        """合法 JS 代码验证通过（node 未安装时跳过）"""
        validator = CodeValidator(project_path=tmp_path)
        code_file = tmp_path / "valid.js"
        code_file.write_text("function hello() { return 'world'; }\n")

        is_valid, errors = await validator.validate_js_syntax(code_file)
        assert is_valid is True


class TestArchitectJsonParser:
    """Architect JSON 解析器测试"""

    def test_parse_clean_json(self):
        """直接解析干净的 JSON"""
        parser = ArchitectJsonParser()
        text = '{"key": "value", "number": 42}'
        result = parser.safe_parse_json(text)
        assert result == {"key": "value", "number": 42}

    def test_parse_json_with_thinking_tags(self):
        """包含 think 标签的 JSON"""
        parser = ArchitectJsonParser()
        text = '<think>分析需求</think>\n{"key": "value"}'
        result = parser.safe_parse_json(text)
        assert result == {"key": "value"}

    def test_parse_json_with_code_block(self):
        """包含 ```json 代码块"""
        parser = ArchitectJsonParser()
        text = '```json\n{"key": "value"}\n```'
        result = parser.safe_parse_json(text)
        assert result == {"key": "value"}

    def test_parse_json_with_trailing_comma(self):
        """尾随逗号"""
        parser = ArchitectJsonParser()
        text = '{"key": "value", "list": [1, 2, 3,],}'
        result = parser.safe_parse_json(text)
        assert result == {"key": "value", "list": [1, 2, 3]}

    def test_parse_json_with_single_quotes(self):
        """单引号格式"""
        parser = ArchitectJsonParser()
        text = "{'key': 'value', 'number': 42}"
        result = parser.safe_parse_json(text)
        assert result == {"key": "value", "number": 42}

    def test_parse_json_truncated(self):
        """截断的 JSON（缺闭合括号）"""
        parser = ArchitectJsonParser()
        text = '{"key": "value", "nested": {"a": 1'
        result = parser.safe_parse_json(text)
        assert result["key"] == "value"
        assert result["nested"]["a"] == 1

    def test_parse_invalid_json_raises(self):
        """完全无法解析时抛 ValueError"""
        parser = ArchitectJsonParser()
        with pytest.raises(ValueError):
            parser.safe_parse_json("这不是 JSON 也不是任何结构化文本")


class TestDynamicModelRouter:
    """动态模型路由测试"""

    def test_get_assignment_simple(self):
        """SIMPLE 级别返回正确分配"""
        assignment = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.SIMPLE)
        assert isinstance(assignment, ModelAssignment)
        assert assignment.architect_model == "Qwen/Qwen3.5-4B"
        assert assignment.frontend_model == "Qwen/Qwen3-8B"

    def test_get_assignment_enterprise_falls_back_to_large(self):
        """ENTERPRISE 降级到 LARGE"""
        enterprise = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.ENTERPRISE)
        large = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.LARGE)
        assert enterprise.architect_model == large.architect_model
        assert enterprise.frontend_model == large.frontend_model

    def test_config_loading(self):
        """配置文件加载正常"""
        config = load_agent_model_config()
        # 配置文件可能不存在，返回 None 也是正常行为
        assert config is None or isinstance(config, dict)


class TestMemory:
    """记忆系统测试"""

    def test_conversation_memory_add_and_get(self):
        """添加和获取对话记忆"""
        memory = ConversationMemory()
        entry = MemoryEntry(type="user", content="你好")
        memory.add(entry)

        recent = memory.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].content == "你好"

    def test_conversation_memory_compression(self):
        """超过阈值自动压缩"""
        memory = ConversationMemory()
        for i in range(20):
            memory.add(MemoryEntry(type="user", content=f"消息 {i}"))

        summary = memory.get_summary()
        assert summary["is_compressed"] is True
        # 压缩后：1 条摘要 + COMPRESSED_ENTRIES 条最近条目 + 后续新增条目
        assert summary["total_entries"] <= 20

    def test_knowledge_memory_lru_eviction(self):
        """LRU 淘汰"""
        memory = KnowledgeMemory(max_entries=3)
        memory.add(MemoryEntry(content="知识1", metadata={"key": "k1"}))
        memory.add(MemoryEntry(content="知识2", metadata={"key": "k2"}))
        memory.add(MemoryEntry(content="知识3", metadata={"key": "k3"}))
        memory.add(MemoryEntry(content="知识4", metadata={"key": "k4"}))

        assert memory.get("k1") is None
        assert memory.get("k4") is not None

    def test_reflection_memory_add(self):
        """添加反思记忆"""
        memory = ReflectionMemory()
        memory.add_reflection("这次任务执行顺利")

        recent = memory.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].content == "这次任务执行顺利"
        assert recent[0].type == "reflection"


class TestReActEngine:
    """ReAct 引擎测试"""

    @pytest.mark.asyncio
    async def test_simple_mode_no_tools(self):
        """无工具时直接调用 LLM"""
        mock_llm = AsyncMock(return_value="直接回答")
        engine = ReActEngine(
            tools={},
            call_llm_fn=mock_llm,
        )

        result = await engine.run("测试问题")
        assert result == "直接回答"
        mock_llm.assert_called_once()

    def test_parse_tool_call(self):
        """解析工具调用 JSON"""
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())

        result = engine._parse_tool_call('{"tool": "read_file", "params": {"path": "test.py"}}')
        assert result is not None
        assert result["tool"] == "read_file"
        assert result["params"]["path"] == "test.py"

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """工具执行成功"""
        mock_tool = MagicMock(return_value={"content": "文件内容"})
        tools = {"read_file": {"fn": mock_tool, "description": "读取文件"}}

        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock())
        success, result = await engine._execute_tool("read_file", {"path": "test.py"})

        assert success is True
        assert result == {"content": "文件内容"}

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        """工具不存在返回错误"""
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        success, result = await engine._execute_tool("nonexistent_tool", {})

        assert success is False
        assert "工具不存在" in result["error"]
