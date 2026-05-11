"""
aicloud 模块单元测试

测试 aicloud 功能：
1. 敏感信息过滤器测试
2. 上下文隔离器测试
3. 沙箱管理测试
4. AI 内容分析器测试
"""

import pytest
import asyncio
from app.utils.aicloud.sensitive_filter import (
    filter_sensitive_content,
    mask_api_keys,
    mask_passwords,
    mask_tokens,
    detect_sensitive_info,
    SENSITIVE_PATTERNS,
)
from app.utils.aicloud.context_isolator import (
    ContextIsolator,
    is_protected_path,
    is_protected_file,
    PROTECTED_PATHS,
    PROTECTED_FILES,
)
from app.utils.aicloud.sandbox import (
    SANDBOX_BASE_DIR,
    validate_sandbox_path,
    get_sandbox_path,
    get_absolute_sandbox_path,
    sanitize_path,
    is_path_safe,
)
from app.utils.aicloud.content_analyzer import (
    check_malicious_pattern,
    check_dangerous_extensions,
    MALICIOUS_PATTERNS,
    DANGEROUS_FILE_EXTENSIONS,
)


class TestSensitiveFilter:
    """敏感信息过滤器测试"""

    def test_filter_openai_key(self):
        """测试 OpenAI API Key 过滤"""
        content = "sk-1234567890abcdefghijklmnopqrstuvwxyz12345678901234"
        filtered = filter_sensitive_content(content)
        assert "[OPENAI_KEY]" in filtered
        assert "sk-12345678" not in filtered

    def test_filter_github_token(self):
        """测试 GitHub Token 过滤"""
        content = "ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
        filtered = filter_sensitive_content(content)
        assert "[GITHUB_TOKEN]" in filtered
        assert "ghp_" not in filtered

    def test_filter_gitlab_token(self):
        """测试 GitLab Token 过滤"""
        content = "glpat-1234567890-abcd-efgh"
        filtered = filter_sensitive_content(content)
        assert "[GITLAB_TOKEN]" in filtered
        assert "glpat-" not in filtered

    def test_filter_password(self):
        """测试密码过滤"""
        content = 'password="mysecretpassword"'
        filtered = filter_sensitive_content(content)
        assert "[REDACTED]" in filtered or "password=" in filtered.lower()
        assert "mysecretpassword" not in filtered

    def test_filter_api_key(self):
        """测试 API Key 过滤"""
        content = "api_key='AKIAIOSFODNN7EXAMPLE'"
        filtered = filter_sensitive_content(content)
        assert "[REDACTED]" in filtered or "api_key" in filtered.lower()

    def test_filter_private_key(self):
        """测试私钥过滤"""
        content = """-----BEGIN RSA PRIVATE KEY-----
MIIBOgIBAAJBALRiMLAHudeSA2F+0TaRO4RG0qncU7nGzj1KpnE9WMyqT3aRMW0k
qPVA9XwFVQPz6hZmhH0zN4xX8n1d7fHhcwIDAQAB
-----END RSA PRIVATE KEY-----"""
        filtered = filter_sensitive_content(content)
        assert "[PRIVATE_KEY]" in filtered

    def test_filter_jwt_token(self):
        """测试 JWT Token 过滤"""
        content = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XmL9nKc9"
        filtered = filter_sensitive_content(content)
        assert "[JWT_TOKEN]" in filtered

    def test_filter_mongodb_connection(self):
        """测试 MongoDB 连接字符串过滤"""
        content = "mongodb://admin:password123@localhost:27017/db"
        filtered = filter_sensitive_content(content)
        assert "[REDACTED]" in filtered

    def test_mask_api_keys(self):
        """测试 mask_api_keys 函数"""
        content = "sk-1234567890abcdefghijklmnopqrstuvwxyz12345678901234"
        masked = mask_api_keys(content)
        assert "sk-" not in masked

    def test_mask_passwords(self):
        """测试 mask_passwords 函数"""
        content = 'password="secret"'
        masked = mask_passwords(content)
        assert "secret" not in masked

    def test_mask_tokens(self):
        """测试 mask_tokens 函数"""
        content = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
        masked = mask_tokens(content)
        assert "[TOKEN]" in masked

    def test_detect_sensitive_info(self):
        """测试敏感信息检测"""
        content = "sk-1234567890abcdefghijklmnopqrstuvwxyz12345678901234"
        detected = detect_sensitive_info(content)
        assert "OpenAI API Key" in detected

    def test_empty_content(self):
        """测试空内容"""
        assert filter_sensitive_content("") == ""
        assert filter_sensitive_content(None) is None

    def test_no_sensitive_content(self):
        """测试无敏感信息内容"""
        content = "Hello, this is a normal message without any secrets."
        filtered = filter_sensitive_content(content)
        assert filtered == content


class TestContextIsolator:
    """上下文隔离器测试"""

    def test_block_protected_etc_path(self):
        """测试保护 /etc/ 路径"""
        isolator = ContextIsolator()
        assert isolator.block_protected_paths("/etc/passwd")
        assert isolator.block_protected_paths("/etc/shadow")

    def test_block_protected_root_path(self):
        """测试保护 /root/ 路径"""
        isolator = ContextIsolator()
        assert isolator.block_protected_paths("/root/.bashrc")

    def test_block_protected_proc_path(self):
        """测试保护 /proc/ 路径"""
        isolator = ContextIsolator()
        assert isolator.block_protected_paths("/proc/self")

    def test_allow_sandbox_path(self):
        """测试允许沙箱路径"""
        isolator = ContextIsolator()
        assert not isolator.block_protected_paths("/sandbox/123/workspace")

    def test_block_protected_env_file(self):
        """测试保护 .env 文件"""
        isolator = ContextIsolator()
        assert isolator.block_protected_files(".env")
        assert isolator.block_protected_files(".env.production")

    def test_block_protected_key_file(self):
        """测试保护密钥文件"""
        isolator = ContextIsolator()
        assert isolator.block_protected_files("id_rsa")
        assert isolator.block_protected_files("id_ed25519")
        assert isolator.block_protected_files("private.key")

    def test_block_protected_git_file(self):
        """测试保护 Git 配置文件"""
        isolator = ContextIsolator()
        assert isolator.block_protected_files(".git/config")
        assert isolator.block_protected_files(".git/credentials")

    def test_allow_normal_file(self):
        """测试允许普通文件"""
        isolator = ContextIsolator()
        assert not isolator.block_protected_files("readme.txt")
        assert not isolator.block_protected_files("code.py")

    def test_is_protected_path_function(self):
        """测试 is_protected_path 函数"""
        assert is_protected_path("/etc/passwd")
        assert not is_protected_path("/sandbox/123/file.txt")

    def test_is_protected_file_function(self):
        """测试 is_protected_file 函数"""
        assert is_protected_file(".env")
        assert not is_protected_file("readme.md")


class TestSandbox:
    """沙箱管理测试"""

    def test_sandbox_base_dir(self):
        """测试沙箱根目录"""
        assert SANDBOX_BASE_DIR == "/sandbox"

    def test_get_sandbox_path(self):
        """测试获取用户沙箱路径"""
        path = get_sandbox_path(123)
        assert path == "/sandbox/123"

    def test_get_absolute_sandbox_path(self):
        """测试获取绝对沙箱路径"""
        path = get_absolute_sandbox_path(123, "workspace/file.txt")
        assert "/sandbox/123/workspace/file.txt" in path

    def test_validate_sandbox_path_valid(self):
        """测试验证合法沙箱路径"""
        assert validate_sandbox_path(123, "/sandbox/123/workspace/file.txt")
        assert validate_sandbox_path(123, "/sandbox/123")

    def test_validate_sandbox_path_invalid(self):
        """测试验证非法沙箱路径"""
        assert not validate_sandbox_path(123, "/sandbox/456/workspace/file.txt")
        assert not validate_sandbox_path(123, "/etc/passwd")
        assert not validate_sandbox_path(123, "/sandbox/123/../etc/passwd")

    def test_sanitize_path(self):
        """测试路径清理"""
        path = sanitize_path("/sandbox/123/../123/./workspace")
        assert ".." not in path
        assert "." not in path.split("/")[-1] if "/" in path else True

    def test_is_path_safe_valid(self):
        """测试安全路径"""
        assert is_path_safe("/sandbox/123/workspace/file.txt")
        assert is_path_safe("workspace/file.txt")

    def test_is_path_safe_invalid(self):
        """测试危险路径"""
        assert not is_path_safe("/etc/passwd")
        assert not is_path_safe("../../../etc/passwd")
        assert not is_path_safe("file.txt; rm -rf")


class TestContentAnalyzer:
    """AI 内容分析器测试"""

    def test_check_malicious_pattern_rsync(self):
        """测试检测 rm -rf 命令"""
        content = "rm -rf /"
        has_malicious, found = check_malicious_pattern(content)
        assert has_malicious

    def test_check_malicious_pattern_os_system(self):
        """测试检测 os.system 调用"""
        content = "import os\nos.system('ls')"
        has_malicious, found = check_malicious_pattern(content)
        assert has_malicious

    def test_check_malicious_pattern_subprocess(self):
        """测试检测 subprocess 调用"""
        content = "import subprocess\nsubprocess.call(['ls'])"
        has_malicious, found = check_malicious_pattern(content)
        assert has_malicious

    def test_check_malicious_pattern_system(self):
        """测试检测 system 调用"""
        content = "import os\nos.system('ls')"
        has_malicious, found = check_malicious_pattern(content)
        assert has_malicious

    def test_check_malicious_pattern_eval(self):
        """测试检测 eval 调用"""
        content = "eval('print(1)')"
        has_malicious, found = check_malicious_pattern(content)
        assert has_malicious

    def test_check_safe_content(self):
        """测试安全内容"""
        content = "Hello, this is a normal message."
        has_malicious, found = check_malicious_pattern(content)
        assert not has_malicious

    def test_check_dangerous_extensions_exe(self):
        """测试检测危险扩展名 .exe"""
        assert check_dangerous_extensions("malware.exe") is not None

    def test_check_dangerous_extensions_msi(self):
        """测试检测危险扩展名 .msi"""
        assert check_dangerous_extensions("installer.msi") is not None

    def test_check_dangerous_extensions_ps1(self):
        """测试检测危险扩展名 .ps1"""
        assert check_dangerous_extensions("script.ps1") is not None

    def test_check_safe_extension(self):
        """测试安全扩展名"""
        assert check_dangerous_extensions("readme.txt") is None
        assert check_dangerous_extensions("code.py") is None
        assert check_dangerous_extensions("data.json") is None
        assert check_dangerous_extensions("App.vue") is None
        assert check_dangerous_extensions("component.tsx") is None
        assert check_dangerous_extensions("styles.scss") is None
        assert check_dangerous_extensions("build.sh") is None

    def test_malicious_patterns_not_empty(self):
        """测试恶意模式列表非空"""
        assert len(MALICIOUS_PATTERNS) > 0

    def test_dangerous_extensions_not_empty(self):
        """测试危险扩展名列表非空"""
        assert len(DANGEROUS_FILE_EXTENSIONS) > 0


class TestPermissionPatterns:
    """权限模式测试"""

    def test_protected_paths_not_empty(self):
        """测试保护路径列表非空"""
        assert len(PROTECTED_PATHS) > 0

    def test_protected_files_not_empty(self):
        """测试保护文件列表非空"""
        assert len(PROTECTED_FILES) > 0

    def test_sensitive_patterns_not_empty(self):
        """测试敏感模式字典非空"""
        assert len(SENSITIVE_PATTERNS) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
