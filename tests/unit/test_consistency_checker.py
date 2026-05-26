"""
测试简化版一致性检查器
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from app.agent.consistency_checker import ConsistencyChecker, SchemaDrift


class TestConsistencyChecker:
    """测试一致性检查器"""

    @pytest.fixture
    def temp_dirs(self):
        """创建临时目录"""
        original = Path(tempfile.mkdtemp())
        new = Path(tempfile.mkdtemp())
        yield original, new
        shutil.rmtree(original)
        shutil.rmtree(new)

    def test_no_original_dir(self, temp_dirs):
        """测试无原始目录时跳过检查"""
        _, new_dir = temp_dirs
        checker = ConsistencyChecker(new_dir)
        drifts = checker.check_all(original_dir=None)
        assert len(drifts) == 0

    def test_signature_drift_detected(self, temp_dirs):
        """测试函数签名变更检测"""
        original_dir, new_dir = temp_dirs

        # 原始文件
        (original_dir / "app.py").write_text("def foo(a, b): pass")
        # 新文件 - 签名变更
        (new_dir / "app.py").write_text("def foo(a, b, c): pass")

        checker = ConsistencyChecker(new_dir)
        drifts = checker.check_all(original_dir)

        assert len(drifts) > 0
        assert any(d.drift_type == "signature" for d in drifts)

    def test_no_drift(self, temp_dirs):
        """测试无变更"""
        original_dir, new_dir = temp_dirs

        # 相同文件
        content = "def foo(a, b): pass"
        (original_dir / "app.py").write_text(content)
        (new_dir / "app.py").write_text(content)

        checker = ConsistencyChecker(new_dir)
        drifts = checker.check_all(original_dir)

        assert len(drifts) == 0
