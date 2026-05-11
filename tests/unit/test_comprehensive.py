"""
综合单元测试 - 白盒测试（健壮版）
专注于可导入和基本功能的测试
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock


class TestSecurityUtils:
    """安全工具单元测试"""

    def test_create_access_token(self):
        """测试创建访问令牌"""
        from app.utils.security import create_access_token
        token = create_access_token(sub="1", permission_level="normal")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_hash_password(self):
        """测试密码哈希"""
        from app.utils.security import hash_password, verify_password
        password = "TestPassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_verify_password(self):
        """测试密码验证"""
        from app.utils.security import hash_password, verify_password
        password = "TestPassword123!"
        hashed = hash_password(password)
        assert verify_password("WrongPassword", hashed) is False


class TestJsonParserUtils:
    """JSON 解析工具单元测试"""

    def test_robust_json_parser_valid(self):
        """测试有效 JSON 解析"""
        from app.utils.json_parser import RobustJSONParser
        parser = RobustJSONParser()
        result = parser.parse('{"key": "value"}')
        assert result == {"key": "value"}


class TestWebSearchUtils:
    """网页搜索工具单元测试"""

    def test_free_web_search_init(self):
        """测试网页搜索初始化"""
        from app.utils.web_search import FreeWebSearch
        searcher = FreeWebSearch()
        assert searcher is not None


class TestAicloudSensitiveFilter:
    """AI Cloud 敏感信息过滤单元测试"""

    def test_filter_github_token(self):
        """测试 GitHub Token 过滤"""
        from app.utils.aicloud.sensitive_filter import filter_sensitive_content
        content = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        filtered = filter_sensitive_content(content)
        assert "ghp_" not in filtered or "***" in filtered

    def test_empty_content(self):
        """测试空内容"""
        from app.utils.aicloud.sensitive_filter import filter_sensitive_content
        result = filter_sensitive_content("")
        assert result == ""

    def test_safe_content(self):
        """测试安全内容"""
        from app.utils.aicloud.sensitive_filter import filter_sensitive_content
        content = "Hello, this is a normal message."
        filtered = filter_sensitive_content(content)
        assert filtered == content


class TestAicloudContextIsolator:
    """AI Cloud 上下文隔离单元测试"""

    def test_block_protected_path(self):
        """测试阻止受保护路径"""
        from app.utils.aicloud.context_isolator import is_protected_path
        assert is_protected_path("/etc/passwd") is True
        assert is_protected_path("/root/.ssh") is True
        assert is_protected_path("/proc/self") is True

    def test_allow_normal_path(self):
        """测试允许正常路径"""
        from app.utils.aicloud.context_isolator import is_protected_path
        assert is_protected_path("/home/user/document.pdf") is False

    def test_block_protected_file(self):
        """测试阻止受保护文件"""
        from app.utils.aicloud.context_isolator import is_protected_file
        assert is_protected_file(".env") is True
        assert is_protected_file("id_rsa") is True

    def test_allow_normal_file(self):
        """测试允许正常文件"""
        from app.utils.aicloud.context_isolator import is_protected_file
        assert is_protected_file("document.txt") is False


class TestCsrfUtils:
    """CSRF 工具单元测试"""

    def test_csrf_token_manager_init(self):
        """测试 CSRF 令牌管理器初始化"""
        from app.utils.csrf import CSRFTokenManager
        manager = CSRFTokenManager()
        assert manager is not None


# 运行标记
pytestmark = pytest.mark.unit
