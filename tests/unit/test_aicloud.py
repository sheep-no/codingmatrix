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
    get_sandbox_path,
    get_sandbox_workspace_path,
)
from app.utils.aicloud.content_analyzer import (
    check_malicious_pattern,
    check_dangerous_extensions,
    MALICIOUS_PATTERNS,
    DANGEROUS_FILE_EXTENSIONS,
)
from app.utils.file_operator import PathSecurityError


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

    def test_filter_password_value_starting_with_s(self):
        """值以 s 开头的密码不能被漏检（旧字符类把字母 s 一起排除了）。"""
        filtered = filter_sensitive_content("password=secret123")
        assert "secret123" not in filtered

    def test_filter_password_quoted_value_with_spaces(self):
        """带空格的引号值必须整体替换，不能残留一半明文。"""
        filtered = filter_sensitive_content('password: "my pass word"')
        assert filtered == "password=[REDACTED]"

    def test_detect_password_value_starting_with_s(self):
        assert "Password" in detect_sensitive_info("password=secret123")

    def test_mask_passwords_quoted_value_with_spaces(self):
        masked = mask_passwords('password: "my pass word"')
        assert "pass word" not in masked

    def test_mask_api_keys_value_starting_with_s(self):
        masked = mask_api_keys("api_key=secret")
        assert "secret" not in masked

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

    def test_get_isolator_is_single_instance_under_concurrency(self, monkeypatch):
        """并发获取隔离器只能构造一次（CI3）。

        用带 sleep 的假类放大竞态窗口：无锁实现下每个线程都会各建一份实例，
        双检锁下只有一个线程真正构造。
        """
        import threading
        import time

        import app.utils.aicloud.context_isolator as isolator_module

        created = []
        created_lock = threading.Lock()

        class SlowIsolator:
            def __init__(self):
                with created_lock:
                    created.append(1)
                time.sleep(0.05)

        monkeypatch.setattr(isolator_module, "ContextIsolator", SlowIsolator)
        monkeypatch.setattr(isolator_module, "_isolator_instance", None)

        results = []
        results_lock = threading.Lock()

        def worker():
            instance = isolator_module.get_isolator()
            with results_lock:
                results.append(instance)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(created) == 1
        assert len(results) == 8
        assert all(instance is results[0] for instance in results)


class TestSandbox:
    """沙箱管理测试"""

    def test_sandbox_base_dir(self):
        """测试沙箱根目录"""
        assert SANDBOX_BASE_DIR == "/sandbox"

    def test_get_sandbox_path(self):
        """测试获取用户沙箱路径"""
        path = get_sandbox_path(123)
        assert path == "/sandbox/123"

    def test_get_sandbox_workspace_path(self):
        """测试获取用户沙箱工作目录"""
        path = get_sandbox_workspace_path(123)
        assert path == "/sandbox/123/workspace"


class TestSandboxFileOperator:
    """SandboxFileOperator 路径归属校验测试（复用 FileOperator 基类实现）"""

    def _operator(self, tmp_path, monkeypatch):
        from app.utils.aicloud.sandbox_operator import SandboxFileOperator

        monkeypatch.setattr(SandboxFileOperator, "SANDBOX_BASE_DIR", str(tmp_path))
        operator = SandboxFileOperator(user_id=1)
        workspace = tmp_path / "1" / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return operator, workspace

    def test_symlink_escape_is_rejected(self, tmp_path, monkeypatch):
        """沙箱内指向外部的符号链接必须被拒绝"""
        operator, workspace = self._operator(tmp_path, monkeypatch)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        (workspace / "escape.txt").symlink_to(outside)

        with pytest.raises(PathSecurityError):
            operator.read("escape.txt")

    def test_paths_outside_sandbox_are_rejected(self, tmp_path, monkeypatch):
        """父目录逃逸与绝对路径越界必须被拒绝"""
        operator, _ = self._operator(tmp_path, monkeypatch)

        with pytest.raises(PathSecurityError):
            operator.read("../outside.txt")
        with pytest.raises(PathSecurityError):
            operator.read("/etc/passwd")

    def test_normal_file_is_readable(self, tmp_path, monkeypatch):
        """沙箱内普通文件正常读取"""
        operator, workspace = self._operator(tmp_path, monkeypatch)
        (workspace / "normal.txt").write_text("ok")

        assert operator.read("normal.txt")["content"] == "ok"


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

    @pytest.mark.parametrize(
        "content",
        [
            "os .system('ls')",
            "os.  system('ls')",
            "os. popen('ls')",
            "subprocess.run(['ls'])",
            "subprocess.Popen('ls', shell=True)",
            "subprocess.check_output(['ls'])",
            "subprocess.check_call(['ls'])",
            "rm -rf ~",
            "rm -rf *",
            "rm -rf $HOME",
            "rm -fr /",
        ],
    )
    def test_check_malicious_pattern_evasion_variants(self, content):
        """点号空白、subprocess 其它入口与 rm 的其它目标都算恶意（CA6）。"""
        has_malicious, found = check_malicious_pattern(content)
        assert has_malicious, content

    @pytest.mark.parametrize(
        "content",
        [
            "data = base64.b64decode(png_b64)  # 正常解码图片",
            "import base64; base64.b64decode(payload)",
            "os.path.join('a', 'b')",
            "rm file.txt",
        ],
    )
    def test_benign_content_is_not_flagged(self, content):
        """正常用途不应被误报为恶意模式（CA6）。"""
        has_malicious, found = check_malicious_pattern(content)
        assert not has_malicious, content

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
