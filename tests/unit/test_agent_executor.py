"""
Agent 执行器单元测试

覆盖：
- AgentExecutor 初始化
- execute_file_operation (read/write/delete/create)
- execute 步骤分发
- execute_analysis（mock LLM）
- ANALYSIS_TOOLS 注册表
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.agent_executor import AgentExecutor, ANALYSIS_TOOLS


class TestAnalysisToolsRegistry:
    def test_has_read_file(self):
        assert "read_file" in ANALYSIS_TOOLS

    def test_has_list_files(self):
        assert "list_files" in ANALYSIS_TOOLS

    def test_has_read_symbols(self):
        assert "read_symbols" in ANALYSIS_TOOLS

    def test_has_read_imports(self):
        assert "read_imports" in ANALYSIS_TOOLS

    def test_has_summarize_file(self):
        assert "summarize_file" in ANALYSIS_TOOLS

    def test_has_run_command(self):
        assert "run_command" in ANALYSIS_TOOLS

    def test_all_tools_have_fn(self):
        for name, tool in ANALYSIS_TOOLS.items():
            assert callable(tool["fn"]), f"{name} fn not callable"

    def test_all_tools_have_description(self):
        for name, tool in ANALYSIS_TOOLS.items():
            assert "description" in tool, f"{name} missing description"

    def test_all_tools_have_params(self):
        for name, tool in ANALYSIS_TOOLS.items():
            assert "params" in tool, f"{name} missing params"


class TestAgentExecutorInit:
    def test_init(self):
        mock_op = MagicMock()
        executor = AgentExecutor(file_operator=mock_op)
        assert executor.file_operator is mock_op


class TestExecuteFileOperation:
    @pytest.mark.asyncio
    async def test_read(self):
        mock_op = AsyncMock()
        mock_op.read_async.return_value = {"content": "file content"}
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute_file_operation({"operation": "read", "path": "test.py"})
        mock_op.read_async.assert_called_once_with("test.py")
        assert result == {"content": "file content"}

    @pytest.mark.asyncio
    async def test_write(self):
        mock_op = AsyncMock()
        mock_op.write_async.return_value = {"success": True}
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute_file_operation({
            "operation": "write", "path": "test.py", "content": "x=1"
        })
        mock_op.write_async.assert_called_once_with("test.py", "x=1")
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_delete(self):
        mock_op = MagicMock()
        mock_op.delete.return_value = {"success": True}
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute_file_operation({"operation": "delete", "path": "test.py"})
        mock_op.delete.assert_called_once_with("test.py")

    @pytest.mark.asyncio
    async def test_create_file(self):
        mock_op = MagicMock()
        mock_op.create.return_value = {"success": True}
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute_file_operation({
            "operation": "create", "path": "new.py", "is_directory": False, "content": "x=1"
        })
        mock_op.create.assert_called_once_with("new.py", is_directory=False, content="x=1")

    @pytest.mark.asyncio
    async def test_create_directory(self):
        mock_op = MagicMock()
        mock_op.create.return_value = {"success": True}
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute_file_operation({
            "operation": "create", "path": "src/", "is_directory": True, "content": ""
        })
        mock_op.create.assert_called_once_with("src/", is_directory=True, content="")

    @pytest.mark.asyncio
    async def test_unknown_operation(self):
        mock_op = MagicMock()
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute_file_operation({"operation": "move", "path": "test.py"})
        assert "未知操作" in result["error"]


class TestExecute:
    @pytest.mark.asyncio
    async def test_file_operation_step(self):
        mock_op = AsyncMock()
        mock_op.read_async.return_value = {"content": "data"}
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute({
            "type": "file_operation",
            "params": {"operation": "read", "path": "x.py"},
        })
        assert result == {"content": "data"}

    @pytest.mark.asyncio
    async def test_ai_call_step(self):
        mock_op = MagicMock()
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute({
            "type": "ai_call",
            "params": {"task": "analyze"},
        })
        assert result["status"] == "pending"
        assert result["task"] == "analyze"

    @pytest.mark.asyncio
    async def test_unknown_step_type(self):
        mock_op = MagicMock()
        executor = AgentExecutor(file_operator=mock_op)
        result = await executor.execute({"type": "unknown_type"})
        assert "未知步骤类型" in result["error"]


class TestExecuteAnalysis:
    @pytest.mark.asyncio
    @patch("app.agent.agent_executor.call_llm")
    async def test_analysis_success(self, mock_call_llm):
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": "The code has 3 functions."}}],
        }

        project_path = tempfile_project()
        try:
            executor = AgentExecutor(file_operator=MagicMock())
            result = await executor.execute_analysis(
                task="count functions",
                project_path=project_path,
                max_rounds=1,
            )
            assert result["success"] is True
            assert "analysis" in result
        finally:
            import shutil
            shutil.rmtree(project_path, ignore_errors=True)

    @pytest.mark.asyncio
    @patch("app.agent.agent_executor.call_llm")
    async def test_analysis_empty_response(self, mock_call_llm):
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": ""}}],
        }

        executor = AgentExecutor(file_operator=MagicMock())
        result = await executor.execute_analysis(
            task="test",
            project_path="/tmp/test_nonexistent",
            max_rounds=1,
        )
        # empty or failed analysis returns success=False
        assert result["success"] is False


import tempfile
import os


def tempfile_project():
    """Create a temp directory with a simple Python file for testing."""
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "main.py"), "w") as f:
        f.write("def hello():\n    pass\n\ndef world():\n    pass\n")
    return tmpdir
