"""
Agent 系统核心功能单元测试
测试 Agent 的核心能力：执行、验证
"""
import pytest
from pathlib import Path
from app.agent.executor import EnhancedExecutor
from app.agent.code_validator import CodeValidator


class TestEnhancedExecutor:
    """增强执行器测试"""

    def test_create_executor(self):
        """测试创建执行器"""
        executor = EnhancedExecutor()
        assert executor is not None

    @pytest.mark.asyncio
    async def test_execute_write_file(self, tmp_path):
        """测试写文件工具执行"""
        executor = EnhancedExecutor(project_path=str(tmp_path))
        test_file = tmp_path / "test.txt"

        result = await executor.execute_tool("write_file", {
            "path": str(test_file),
            "content": "Hello, World!"
        })
        assert result is not None
        assert result.success
        assert test_file.exists()

    @pytest.mark.asyncio
    async def test_execute_read_file(self, tmp_path):
        """测试读文件工具执行"""
        executor = EnhancedExecutor(project_path=str(tmp_path))
        test_file = tmp_path / "readme.txt"
        test_file.write_text("Test content")

        result = await executor.execute_tool("read_file", {"file_path": str(test_file)})
        assert result is not None
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_list_files(self, tmp_path):
        """测试列文件工具执行"""
        executor = EnhancedExecutor(project_path=str(tmp_path))
        (tmp_path / "file1.py").write_text("# 1")
        (tmp_path / "file2.py").write_text("# 2")

        result = await executor.execute_tool("list_files", {"directory": str(tmp_path)})
        assert result is not None
        assert result.success


class TestCodeValidator:
    """代码验证器测试"""

    def test_create_validator(self, tmp_path):
        """测试创建验证器"""
        validator = CodeValidator(project_path=str(tmp_path))
        assert validator is not None

    @pytest.mark.asyncio
    async def test_validate_syntax(self, tmp_path):
        """测试语法验证"""
        validator = CodeValidator(project_path=str(tmp_path))
        code_file = tmp_path / "test.py"
        code_file.write_text("def hello():\n    print('Hello')\n")

        result = await validator.validate_syntax(code_file)
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_imports(self, tmp_path):
        """测试导入验证"""
        validator = CodeValidator(project_path=str(tmp_path))
        code_file = tmp_path / "imports.py"
        code_file.write_text("import os\nimport sys\n")

        result = await validator.validate_imports(code_file)
        assert result is not None


class TestAgentIntegration:
    """Agent 集成测试"""

    @pytest.mark.asyncio
    async def test_executor_write_and_read(self, tmp_path):
        """测试执行器写入和读取"""
        executor = EnhancedExecutor(project_path=str(tmp_path))

        test_file = tmp_path / "integration.py"
        content = "x = 1 + 1"

        # 写入
        write_result = await executor.execute_tool("write_file", {
            "path": str(test_file),
            "content": content
        })
        assert write_result is not None
        assert write_result.success

        # 读取
        read_result = await executor.execute_tool("read_file", {"file_path": str(test_file)})
        assert read_result is not None
        assert read_result.success


class TestProgressTracking:
    """进度跟踪测试"""

    def test_file_creation_tracking(self, tmp_path):
        """测试文件创建跟踪"""
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()

        for i in range(5):
            (test_dir / f"file_{i}.py").write_text(f"# File {i}")

        created = list(test_dir.glob("*.py"))
        assert len(created) == 5

    def test_nested_directory_creation(self, tmp_path):
        """测试嵌套目录创建"""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        assert nested.exists()
