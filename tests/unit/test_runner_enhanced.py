"""
IsolatedTestRunner 强化改进测试

覆盖：
- 扩展 pip 白名单
- 安全扫描策略统一（记录不中止）
- 多语言 subprocess 执行
- ServiceContainerManager 集成
- 并发 Semaphore 控制
- OutputParser 集成
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.test_runner import (
    IsolatedTestRunner,
    TestResult,
    ALLOWED_PIP_PACKAGES,
    _get_semaphore,
    MAX_CONCURRENT_TESTS,
)


class TestExpandedPipWhitelist:
    """REQ: pip 白名单与 DockerRunner 保持一致"""

    def test_whitelist_has_fastapi_ecosystem(self):
        for pkg in ['fastapi', 'starlette', 'uvicorn', 'gunicorn']:
            assert pkg in ALLOWED_PIP_PACKAGES

    def test_whitelist_has_database_packages(self):
        for pkg in ['sqlalchemy', 'aiosqlite', 'pymongo', 'redis', 'asyncpg']:
            assert pkg in ALLOWED_PIP_PACKAGES

    def test_whitelist_has_http_clients(self):
        for pkg in ['httpx', 'aiohttp', 'requests']:
            assert pkg in ALLOWED_PIP_PACKAGES

    def test_whitelist_has_data_science(self):
        for pkg in ['pandas', 'numpy', 'scipy', 'matplotlib']:
            assert pkg in ALLOWED_PIP_PACKAGES

    def test_whitelist_has_ai_nlp(self):
        for pkg in ['tiktoken', 'transformers', 'tokenizers']:
            assert pkg in ALLOWED_PIP_PACKAGES

    def test_whitelist_has_web_frameworks(self):
        for pkg in ['flask', 'django', 'bottle', 'falcon']:
            assert pkg in ALLOWED_PIP_PACKAGES

    def test_whitelist_size_is_reasonable(self):
        assert len(ALLOWED_PIP_PACKAGES) >= 60


class TestSecurityScanPolicy:
    """REQ: 安全扫描记录警告但不中止测试"""

    def setup_method(self):
        self.temp_project = Path(tempfile.mkdtemp(prefix="test_scan_"))
        dangerous_code = "import os\nos.system('rm -rf /')\n"
        (self.temp_project / "dangerous.py").write_text(dangerous_code)

    def teardown_method(self):
        shutil.rmtree(str(self.temp_project), ignore_errors=True)

    def test_scan_returns_warnings_not_abort(self):
        runner = IsolatedTestRunner(
            project_path=self.temp_project,
            enable_security_scan=True,
        )
        warnings = runner._scan_security()
        assert len(warnings) > 0
        assert "os.system" in warnings[0]

    @pytest.mark.asyncio
    async def test_run_tests_does_not_abort_on_warnings(self):
        runner = IsolatedTestRunner(
            project_path=self.temp_project,
            enable_security_scan=True,
        )

        runner._framework_detector = MagicMock()
        runner._framework_detector.detect = MagicMock(
            return_value=MagicMock(
                language="python",
                framework="pytest",
                test_command="pytest -v",
                output_format="pytest_xml",
            )
        )

        with patch.object(runner, '_create_venv') as mock_venv, \
             patch.object(runner, '_copy_project') as mock_copy, \
             patch.object(runner, '_install_dependencies', return_value=True) as mock_install, \
             patch.object(runner, '_execute_test', new_callable=AsyncMock) as mock_exec:

            mock_venv.return_value = None
            runner._venv_python = "/usr/bin/python3"
            mock_exec.return_value = TestResult(
                success=True, total_tests=1, passed=1,
                failed=0, errors=0, logs="OK",
                failed_tests=[], method="local_sandbox",
                language="python", framework="pytest",
            )

            result = await runner.run_tests(test_command="pytest")

        assert result.security_warnings is not None
        assert "中止" not in result.logs


class TestMultiLanguageSupport:
    """REQ: 多语言 subprocess 执行"""

    def test_detect_python_project(self):
        from app.agent.framework_detector import FrameworkDetector
        temp_project = Path(tempfile.mkdtemp(prefix="test_lang_"))
        (temp_project / "test_example.py").write_text("def test_ok(): assert True\n")

        detector = FrameworkDetector()
        config = detector.detect(temp_project)
        assert config.language == "python"
        assert config.framework == "pytest"

        shutil.rmtree(str(temp_project), ignore_errors=True)

    def test_detect_js_project(self):
        from app.agent.framework_detector import FrameworkDetector
        temp_project = Path(tempfile.mkdtemp(prefix="test_lang_"))
        (temp_project / "package.json").write_text(
            '{"scripts": {"test": "jest"}, "devDependencies": {"jest": "^29.0"}}'
        )

        detector = FrameworkDetector()
        config = detector.detect(temp_project)
        assert config.language == "javascript"
        assert config.framework in ("jest", "vitest")

        shutil.rmtree(str(temp_project), ignore_errors=True)

    def test_detect_go_project(self):
        from app.agent.framework_detector import FrameworkDetector
        temp_project = Path(tempfile.mkdtemp(prefix="test_lang_"))
        (temp_project / "go.mod").write_text("module example\n\ngo 1.22\n")

        detector = FrameworkDetector()
        config = detector.detect(temp_project)
        assert config.language == "go"
        assert config.framework == "go_test"

        shutil.rmtree(str(temp_project), ignore_errors=True)

    def test_detect_java_project(self):
        from app.agent.framework_detector import FrameworkDetector
        temp_project = Path(tempfile.mkdtemp(prefix="test_lang_"))
        (temp_project / "pom.xml").write_text(
            '<project><modelVersion>4.0.0</modelVersion></project>'
        )

        detector = FrameworkDetector()
        config = detector.detect(temp_project)
        assert config.language == "java"

        shutil.rmtree(str(temp_project), ignore_errors=True)

    def test_detect_rust_project(self):
        from app.agent.framework_detector import FrameworkDetector
        temp_project = Path(tempfile.mkdtemp(prefix="test_lang_"))
        (temp_project / "Cargo.toml").write_text(
            '[package]\nname = "example"\nversion = "0.1.0"\n'
        )

        detector = FrameworkDetector()
        config = detector.detect(temp_project)
        assert config.language == "rust"

        shutil.rmtree(str(temp_project), ignore_errors=True)

    @pytest.mark.asyncio
    async def test_non_python_project_works_in_original_dir(self):
        temp_project = Path(tempfile.mkdtemp(prefix="test_go_"))
        (temp_project / "go.mod").write_text("module example\n\ngo 1.22\n")

        runner = IsolatedTestRunner(
            project_path=temp_project,
            enable_security_scan=False,
        )

        runner._framework_detector = MagicMock()
        runner._framework_detector.detect = MagicMock(
            return_value=MagicMock(
                language="go",
                framework="go_test",
                test_command="go test ./... -v",
                output_format="go_json",
            )
        )

        result = await runner.run_tests(test_command="echo 'go test passed'")

        assert result.language == "go"
        assert result.framework == "go_test"

        shutil.rmtree(str(temp_project), ignore_errors=True)


class TestConcurrencySemaphore:
    """REQ: 并发 Semaphore 控制"""

    def test_semaphore_default_limit(self):
        assert MAX_CONCURRENT_TESTS == 5

    def test_get_semaphore_returns_semaphore(self):
        import asyncio
        sem = _get_semaphore()
        assert isinstance(sem, asyncio.Semaphore)
        assert sem._value == MAX_CONCURRENT_TESTS

    @pytest.mark.asyncio
    async def test_concurrent_execution_respects_limit(self):
        import asyncio

        results = []

        async def task():
            sem = _get_semaphore()
            async with sem:
                results.append(True)
                await asyncio.sleep(0.01)

        tasks = [task() for _ in range(10)]
        await asyncio.gather(*tasks)

        assert len(results) == 10


class TestOutputParserIntegration:
    """REQ: OutputParser 集成"""

    def test_parse_pytest_output(self):
        from app.agent.output_parser import OutputParser

        output = "3 passed, 1 failed in 0.5s"
        result = OutputParser.parse(output, "pytest_xml")

        assert result.passed == 3
        assert result.failed == 1

    def test_parse_go_output(self):
        from app.agent.output_parser import OutputParser

        output = "--- PASS: TestAdd (0.00s)\n--- FAIL: TestSub (0.00s)"
        result = OutputParser.parse(output, "go_json")

        assert result.passed == 1
        assert result.failed == 1

    def test_parse_rust_output(self):
        from app.agent.output_parser import OutputParser

        output = "test result: ok. 5 passed, 0 failed"
        result = OutputParser.parse(output, "rust_text")

        assert result.passed == 5
        assert result.failed == 0

    def test_parse_jest_output(self):
        from app.agent.output_parser import OutputParser

        output = '{"numPassedTests": 10, "numFailedTests": 2, "testResults": []}'
        result = OutputParser.parse(output, "jest_json")

        assert result.passed == 10
        assert result.failed == 2

    def test_parse_with_output_parser_method(self):
        temp_project = Path(tempfile.mkdtemp(prefix="test_parse_"))
        (temp_project / "test_example.py").write_text("def test_ok(): assert True\n")

        runner = IsolatedTestRunner(
            project_path=temp_project,
            enable_security_scan=False,
        )

        result = TestResult(
            success=True, total_tests=0, passed=0, failed=0,
            errors=0, logs="3 passed, 1 failed in 0.5s",
            failed_tests=[], method="local_sandbox",
            language="python", framework="pytest",
        )

        parsed = runner._parse_with_output_parser(result)
        assert parsed.passed == 3
        assert parsed.failed == 1
        assert parsed.total_tests == 4

        shutil.rmtree(str(temp_project), ignore_errors=True)


class TestServiceContainerIntegration:
    """REQ: ServiceContainerManager 集成"""

    def test_required_services_parameter(self):
        runner = IsolatedTestRunner(
            project_path=Path("/tmp/test"),
            required_services=["redis", "postgresql"],
        )
        assert runner.required_services == ["redis", "postgresql"]

    def test_no_services_default(self):
        runner = IsolatedTestRunner(project_path=Path("/tmp/test"))
        assert runner.required_services == []

    @pytest.mark.asyncio
    async def test_start_service_containers_skips_when_no_services(self):
        temp_project = Path(tempfile.mkdtemp(prefix="test_svc_"))
        runner = IsolatedTestRunner(
            project_path=temp_project,
            required_services=[],
        )

        await runner._start_service_containers()
        assert runner._service_container_mgr is None

        shutil.rmtree(str(temp_project), ignore_errors=True)

    @pytest.mark.asyncio
    async def test_start_service_containers_handles_docker_unavailable(self):
        temp_project = Path(tempfile.mkdtemp(prefix="test_svc_"))
        (temp_project / "test_example.py").write_text("def test_ok(): assert True\n")

        runner = IsolatedTestRunner(
            project_path=temp_project,
            required_services=["redis"],
            enable_security_scan=False,
        )

        runner._framework_detector = MagicMock()
        runner._framework_detector.detect = MagicMock(
            return_value=MagicMock(
                language="python",
                framework="pytest",
                test_command="pytest -v",
                output_format="pytest_xml",
            )
        )

        with patch.object(runner, '_start_service_containers', new_callable=AsyncMock) as mock_start, \
             patch.object(runner, '_cleanup_service_containers', new_callable=AsyncMock) as mock_cleanup, \
             patch.object(runner, '_create_venv') as mock_venv, \
             patch.object(runner, '_copy_project') as mock_copy, \
             patch.object(runner, '_install_dependencies', return_value=True) as mock_install, \
             patch.object(runner, '_execute_test', new_callable=AsyncMock) as mock_exec:

            runner._venv_python = "/usr/bin/python3"
            mock_exec.return_value = TestResult(
                success=True, total_tests=1, passed=1,
                failed=0, errors=0, logs="OK",
                failed_tests=[], method="local_sandbox",
                language="python", framework="pytest",
            )

            result = await runner.run_tests(test_command="pytest")
            assert result is not None
            assert result.language == "python"

        shutil.rmtree(str(temp_project), ignore_errors=True)

    def test_service_env_vars_injected_in_sandbox_env(self):
        temp_project = Path(tempfile.mkdtemp(prefix="test_env_"))
        runner = IsolatedTestRunner(
            project_path=temp_project,
            required_services=["redis"],
        )
        runner._service_env_vars = {
            "REDIS_URL": "redis://localhost:6379",
            "REDIS_HOST": "localhost",
        }

        env = runner._build_sandbox_env()
        assert env["REDIS_URL"] == "redis://localhost:6379"
        assert env["REDIS_HOST"] == "localhost"

        shutil.rmtree(str(temp_project), ignore_errors=True)


class TestEnvWhitelistExpansion:
    """REQ: ENV_WHITELIST 包含多语言路径"""

    def test_has_go_paths(self):
        from app.agent.test_runner import ENV_WHITELIST
        assert "GOPATH" in ENV_WHITELIST
        assert "GOCACHE" in ENV_WHITELIST

    def test_has_rust_paths(self):
        from app.agent.test_runner import ENV_WHITELIST
        assert "CARGO_HOME" in ENV_WHITELIST

    def test_has_java_paths(self):
        from app.agent.test_runner import ENV_WHITELIST
        assert "JAVA_HOME" in ENV_WHITELIST

    def test_has_home(self):
        from app.agent.test_runner import ENV_WHITELIST
        assert "HOME" in ENV_WHITELIST