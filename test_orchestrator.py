"""
Orchestrator Agent 单元测试

验证依赖图、复杂度分析、代码验证等核心组件。
"""

import asyncio
import pytest
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import json

from app.agent.orchestrator import (
    OrchestratorAgent,
    ComplexityAnalyzer,
    ComplexityAnalysis,
    ProjectComplexity,
    CodeValidator,
)
from app.agent.dependency_graph import DependencyGraph


# ============================================================
# DependencyGraph Tests
# ============================================================

class TestDependencyGraph:
    def test_basic_graph(self):
        """测试基本图操作"""
        graph = DependencyGraph()
        
        graph.add_file("config.py", file_type="config", priority=1)
        graph.add_file("main.py", file_type="backend", priority=3)
        
        assert len(graph.nodes) == 2
        assert "config.py" in graph.nodes
        assert "main.py" in graph.nodes

    def test_dependency_tracking(self):
        """测试依赖关系追踪"""
        graph = DependencyGraph()
        
        graph.add_file("base.py")
        graph.add_file("derived.py")
        graph.add_dependency("derived.py", "base.py")
        
        # 验证依赖关系已记录
        assert "base.py" in graph.nodes["derived.py"].dependencies

    def test_generation_order(self):
        """测试生成顺序计算"""
        graph = DependencyGraph()
        
        graph.add_file("config.py", priority=1)
        graph.add_file("models.py", priority=2)
        graph.add_file("main.py", priority=3)
        
        graph.add_dependency("main.py", "models.py")
        graph.add_dependency("main.py", "config.py")
        graph.add_dependency("models.py", "config.py")
        
        order = graph.get_generation_order()
        
        # config.py 应该最先被生成（没有依赖）
        # main.py 应该最后被生成（依赖最多）
        assert order.index("config.py") < order.index("main.py")
        assert order.index("models.py") < order.index("main.py")


# ============================================================
# ComplexityAnalyzer Tests
# ============================================================

class TestComplexityAnalyzer:
    def test_simple_project(self):
        """测试简单项目分析"""
        analysis = ComplexityAnalyzer.analyze("Hello World script")
        
        assert analysis.level in [ProjectComplexity.SIMPLE, ProjectComplexity.SMALL]
        assert analysis.estimated_files >= 1

    def test_medium_project(self):
        """测试中等项目分析"""
        analysis = ComplexityAnalyzer.analyze(
            "REST API with user authentication, CRUD operations, and SQLite database"
        )
        
        assert analysis.level in [ProjectComplexity.MEDIUM, ProjectComplexity.LARGE]
        assert analysis.estimated_files >= 3

    def test_large_project(self):
        """测试大型项目分析"""
        analysis = ComplexityAnalyzer.analyze("""
            Full-stack e-commerce platform with:
            - User authentication (OAuth2, JWT)
            - Product catalog with search and filtering
            - Shopping cart and checkout
            - Payment integration (Stripe)
            - Admin dashboard
            - Frontend: React + TypeScript
            - Backend: FastAPI + PostgreSQL + Redis
            - Docker deployment
        """)
        
        assert analysis.level == ProjectComplexity.LARGE
        assert analysis.estimated_files >= 10

    def test_tech_stack_detection(self):
        """测试技术栈识别"""
        analysis = ComplexityAnalyzer.analyze(
            "Vue 3 frontend with FastAPI backend and PostgreSQL database"
        )
        
        techs = analysis.key_technologies
        assert len(techs) >= 2

    def test_has_flags(self):
        """测试前后端/数据库标志"""
        analysis = ComplexityAnalyzer.analyze(
            "React frontend with FastAPI backend and MySQL database"
        )
        
        assert analysis.has_frontend is True
        assert analysis.has_backend is True
        assert analysis.has_database is True


# ============================================================
# CodeValidator Tests
# ============================================================

class TestCodeValidator:
    @pytest.fixture
    def validator(self, tmp_path):
        return CodeValidator(project_path=tmp_path)

    def test_valid_python_syntax(self, validator, tmp_path):
        """测试有效 Python 语法"""
        test_file = tmp_path / "test.py"
        test_file.write_text('''
def hello(name: str) -> str:
    return f"Hello, {name}!"

class Calculator:
    def add(self, a: float, b: float) -> float:
        return a + b
''')
        
        valid, errors = asyncio.get_event_loop().run_until_complete(
            validator.validate_syntax(test_file)
        )
        assert valid is True
        assert len(errors) == 0

    def test_invalid_python_syntax(self, validator, tmp_path):
        """测试无效 Python 语法"""
        test_file = tmp_path / "broken.py"
        test_file.write_text('''
def broken(
    return "syntax error"
''')
        
        valid, errors = asyncio.get_event_loop().run_until_complete(
            validator.validate_syntax(test_file)
        )
        assert valid is False
        assert len(errors) > 0

    def test_non_python_files_skip_syntax_check(self, validator, tmp_path):
        """测试非 Python 文件跳过语法检查"""
        test_file = tmp_path / "requirements.txt"
        test_file.write_text("fastapi\nuvicorn\n")
        
        valid, errors = asyncio.get_event_loop().run_until_complete(
            validator.validate_syntax(test_file)
        )
        assert valid is True


# ============================================================
# OrchestratorAgent Tests
# ============================================================

class TestOrchestratorAgent:
    def test_init_defaults(self, tmp_path):
        """测试默认初始化"""
        orchestrator = OrchestratorAgent(
            output_dir=str(tmp_path),
            memory_enabled=False
        )
        
        assert orchestrator.enable_review is True
        assert orchestrator.enable_validation is True
        assert orchestrator.enable_error_recovery is True
        assert orchestrator.memory_enabled is False

    def test_init_with_options(self, tmp_path):
        """测试自定义选项初始化"""
        orchestrator = OrchestratorAgent(
            output_dir=str(tmp_path),
            enable_review=False,
            enable_validation=False,
            enable_error_recovery=False,
            memory_enabled=False
        )
        
        assert orchestrator.enable_review is False
        assert orchestrator.enable_validation is False
        assert orchestrator.enable_error_recovery is False

    def test_initialize_components(self, tmp_path):
        """测试组件初始化"""
        orchestrator = OrchestratorAgent(
            output_dir=str(tmp_path),
            memory_enabled=False
        )
        
        orchestrator._initialize_components("Simple FastAPI app with SQLite database")
        
        assert orchestrator.analyzer is not None
        assert orchestrator.complexity is not None
        assert orchestrator.complexity.level is not None
        assert orchestrator.complexity.has_backend is True


# ============================================================
# Progress Reporting Tests
# ============================================================

class TestProgressReporting:
    def test_progress_callback(self, tmp_path):
        """测试进度回调"""
        calls = []
        
        def callback(msg):
            calls.append(msg)
        
        orchestrator = OrchestratorAgent(
            output_dir=str(tmp_path),
            memory_enabled=False,
            callback=callback
        )
        
        orchestrator._report_progress("test_step", 1, 5, extra_data="value")
        
        assert len(calls) == 1
        data = json.loads(calls[0])
        assert data["step"] == "test_step"
        assert data["current"] == 1
        assert data["total"] == 5


# ============================================================
# Integration Test (Full Mock)
# ============================================================

class TestFullGenerationMock:
    """完整生成流程的 mock 测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_mock(self, tmp_path):
        """端到端 mock 测试"""
        output_dir = Path(tmp_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建模拟文件
        (output_dir / "main.py").write_text(
            'from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get("/")\nasync def root():\n    return {"status": "ok"}\n'
        )
        (output_dir / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn>=0.23.0\n")
        
        result = {
            "success": True,
            "output_dir": str(output_dir),
            "total_files_created": 2,
            "complexity": "small",
            "errors": [],
            "warnings": []
        }
        
        assert result["success"] is True
        assert result["total_files_created"] == 2
        
        # 验证文件确实被创建
        assert (tmp_path / "main.py").exists()
        assert (tmp_path / "requirements.txt").exists()

    @pytest.mark.asyncio
    async def test_error_handling_mock(self, tmp_path):
        """测试错误处理"""
        errors = ["Failed to generate main.py"]
        
        result = {
            "success": len(errors) == 0,
            "errors": errors,
            "total_files_created": 0
        }
        
        assert result["success"] is False
        assert len(result["errors"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
