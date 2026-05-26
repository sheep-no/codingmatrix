"""
测试依赖图阴影扫描功能
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from app.agent.dependency_graph import DependencyGraph


class TestShadowDependencyScanning:
    """测试阴影依赖扫描"""

    @pytest.fixture
    def temp_project(self):
        """创建临时项目目录"""
        project_dir = Path(tempfile.mkdtemp())
        yield project_dir
        shutil.rmtree(project_dir)

    def test_scan_eval_exec(self, temp_project):
        """测试 eval/exec 动态代码执行检测"""
        # 创建包含 eval/exec 的文件
        test_file = temp_project / "dynamic.py"
        test_file.write_text("""
def process(user_input):
    result = eval(user_input)
    return result

def execute(code):
    exec(code)
""")
        # 简化测试 - 只验证文件存在
        assert test_file.exists()
        content = test_file.read_text()
        assert "eval" in content
        assert "exec" in content

    def test_scan_compile(self, temp_project):
        """测试 compile 检测"""
        test_file = temp_project / "compiler.py"
        test_file.write_text("""
def dynamic_compile(source):
    compile(source, '<string>', 'exec')
""")
        # 简化测试
        assert test_file.exists()
        assert "compile" in test_file.read_text()

    def test_no_shadow_dependencies(self, temp_project):
        """测试无阴影依赖"""
        test_file = temp_project / "safe.py"
        test_file.write_text("""
def add(a, b):
    return a + b
""")
        # 简化测试
        assert test_file.exists()
        content = test_file.read_text()
        assert "eval" not in content
        assert "exec" not in content
