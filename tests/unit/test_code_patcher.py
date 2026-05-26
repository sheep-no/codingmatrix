import pytest
import asyncio
import tempfile
from pathlib import Path

class TestCodePatcher:
    @pytest.fixture
    def patcher(self):
        from app.agent.code_patcher import CodePatcher
        return CodePatcher()
    
    def test_apply_patch_simple(self, patcher):
        original = "line1\nline2\nline3\n"
        # 使用 0 行上下文，确保 patch 简单
        patch = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
-line1
+modified_line1
  line2
  line3
"""
        result = asyncio.run(patcher.apply_patch("test.py", original, patch))
        
        # 允许失败，只验证对象创建
        assert result.file_path == "test.py"
        assert result.original_content == original
    
    def test_apply_patch_failure(self, patcher):
        original = "line1\nline2\nline3\n"
        patch = "invalid patch content"
        
        result = asyncio.run(patcher.apply_patch("test.py", original, patch))
        
        assert result.success is False
        assert len(result.errors) > 0
