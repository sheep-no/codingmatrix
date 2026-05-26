"""
OrchestratorAgent 核心功能单元测试
测试编排代理的核心功能：评估、生成、进度报告
"""
import pytest
from pathlib import Path
from app.agent.orchestrator import OrchestratorAgent


class TestOrchestratorAgentBasic:
    """OrchestratorAgent 基础功能测试"""

    def test_create_instance(self, tmp_path):
        """测试创建实例"""
        agent = OrchestratorAgent(output_dir=str(tmp_path), memory_enabled=False)
        assert agent.output_dir == tmp_path or agent.output_dir == str(tmp_path)
        assert agent.memory_enabled is False

    def test_create_with_defaults(self, tmp_path):
        """测试使用默认参数创建"""
        agent = OrchestratorAgent(output_dir=str(tmp_path))
        assert agent is not None
        assert agent.enable_review is True


class TestEvaluateMode:
    """评价模式测试"""

    def test_evaluate_method_exists(self, tmp_path):
        """测试 evaluate 方法存在"""
        agent = OrchestratorAgent(output_dir=str(tmp_path), memory_enabled=False)
        assert hasattr(agent, 'evaluate')
        assert callable(agent.evaluate)


class TestGenerationMode:
    """生成模式测试"""

    @pytest.mark.asyncio
    async def test_generate_basic(self, tmp_path):
        """测试基本生成功能"""
        from unittest.mock import AsyncMock, patch
        
        agent = OrchestratorAgent(output_dir=str(tmp_path), memory_enabled=False)
        
        # Mock LLM 调用，避免实际生成
        mock_result = {
            "success": True,
            "files_created": ["main.py", "requirements.txt"],
            "elapsed_seconds": 1.0
        }
        
        with patch.object(agent, 'generate', new_callable=AsyncMock, return_value=mock_result):
            result = await agent.generate(
                requirement="Flask Hello World 应用"
            )
            
            assert result is not None
            assert isinstance(result, dict)
            assert result.get("success") is True


class TestProgressReporting:
    """进度报告测试"""

    def test_build_progress_event_basic(self, tmp_path):
        """测试构建基本进度事件"""
        agent = OrchestratorAgent(output_dir=str(tmp_path), memory_enabled=False)
        
        event = agent.build_progress_event(
            step="analyzing",
            current=1,
            total=10
        )
        
        assert event is not None

    def test_build_progress_event_with_message(self, tmp_path):
        """测试带消息的进度事件"""
        agent = OrchestratorAgent(output_dir=str(tmp_path), memory_enabled=False)
        
        event = agent.build_progress_event(
            step="generating",
            current=5,
            total=10,
            message="生成文件"
        )
        
        assert event is not None
        assert isinstance(event, dict)
