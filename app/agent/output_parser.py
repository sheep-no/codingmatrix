"""
OutputParser - 统一测试输出解析器

v4.8.0 新增：
- 解析 6 种测试框架输出为统一的 ParsedTestResult
- 支持 pytest XML, Jest JSON, JUnit XML, Go JSON, Rust text, C++ text
- 通用文本解析器作为 fallback
"""

import json
import re
import logging
from typing import List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TestCaseResult:
    """单个测试用例结果"""
    name: str
    passed: bool
    duration: float = 0.0
    error_message: str = ""


@dataclass
class ParsedTestResult:
    """统一测试结果"""
    passed: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    test_cases: List[TestCaseResult] = field(default_factory=list)
    duration: float = 0.0


class OutputParser:
    """统一测试输出解析器"""

    @staticmethod
    def parse(raw_output: str, format: str) -> ParsedTestResult:
        """
        解析测试输出为统一格式

        Args:
            raw_output: 原始测试输出文本
            format: 输出格式标识

        Returns:
            ParsedTestResult 统一结果
        """
        parsers = {
            "pytest_xml": PytestXMLParser,
            "jest_json": JestJSONParser,
            "junit_xml": JUnitXMLParser,
            "go_json": GoTestParser,
            "rust_text": RustTestParser,
            "cpp_text": CppTestParser,
        }

        parser_cls = parsers.get(format, GenericTextParser)
        parser = parser_cls()
        return parser.parse(raw_output)


class GenericTextParser:
    """通用文本解析器 - 从文本中提取 passed/failed/ERROR 信息"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        passed_match = re.search(r"(\d+)\s+passed", raw_output, re.IGNORECASE)
        if passed_match:
            result.passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", raw_output, re.IGNORECASE)
        if failed_match:
            result.failed = int(failed_match.group(1))

        error_matches = re.findall(r"ERROR[:\s]+(.+)", raw_output)
        result.errors = error_matches[:20]

        return result


class PytestXMLParser:
    """pytest XML 输出解析器"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        passed_match = re.search(r"(\d+)\s+passed", raw_output)
        if passed_match:
            result.passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", raw_output)
        if failed_match:
            result.failed = int(failed_match.group(1))

        error_match = re.search(r"(\d+)\s+error", raw_output)
        if error_match:
            result.failed += int(error_match.group(1))

        for line in raw_output.split("\n"):
            if "FAILED" in line:
                result.errors.append(line.strip())

        return result


class JestJSONParser:
    """Jest JSON 输出解析器"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        try:
            data = json.loads(raw_output)
            num_passed = data.get("numPassedTests", 0)
            num_failed = data.get("numFailedTests", 0)

            result.passed = num_passed
            result.failed = num_failed

            test_results = data.get("testResults", [])
            for test_result in test_results:
                assertion_results = test_result.get("assertionResults", [])
                for assertion in assertion_results:
                    failure_msgs = assertion.get("failureMessages", [])
                    result.test_cases.append(TestCaseResult(
                        name=assertion.get("fullName", ""),
                        passed=assertion.get("status") == "passed",
                        duration=assertion.get("duration", 0) / 1000,
                        error_message=failure_msgs[0] if failure_msgs else "",
                    ))

            for test_result in test_results:
                if test_result.get("status") == "failed":
                    message = test_result.get("message", "")
                    if message:
                        result.errors.append(message[:200])
        except json.JSONDecodeError:
            result = GenericTextParser().parse(raw_output)

        return result


class JUnitXMLParser:
    """JUnit XML 输出解析器（简化版 - 从文本中提取）"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        tests_match = re.search(r"tests\s*=\s*['\"](\d+)['\"]", raw_output)
        failures_match = re.search(r"failures\s*=\s*['\"](\d+)['\"]", raw_output)
        errors_match = re.search(r"errors\s*=\s*['\"](\d+)['\"]", raw_output)

        total = int(tests_match.group(1)) if tests_match else 0
        failures = int(failures_match.group(1)) if failures_match else 0
        errors_count = int(errors_match.group(1)) if errors_match else 0

        result.passed = total - failures - errors_count
        result.failed = failures + errors_count

        failure_matches = re.findall(r"<failure[^>]*>(.*?)</failure>", raw_output, re.DOTALL)
        result.errors = [f[:200] for f in failure_matches]

        return result


class GoTestParser:
    """Go test 输出解析器"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        pass_count = len(re.findall(r"--- PASS:", raw_output))
        fail_count = len(re.findall(r"--- FAIL:", raw_output))

        result.passed = pass_count
        result.failed = fail_count

        for line in raw_output.split("\n"):
            if "--- FAIL:" in line:
                result.errors.append(line.strip())

        return result


class RustTestParser:
    """Rust cargo test 输出解析器"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        passed_match = re.search(r"(\d+)\s+passed", raw_output)
        failed_match = re.search(r"(\d+)\s+failed", raw_output)

        if passed_match:
            result.passed = int(passed_match.group(1))
        if failed_match:
            result.failed = int(failed_match.group(1))

        for line in raw_output.split("\n"):
            if "FAILED" in line and "---" not in line:
                result.errors.append(line.strip())

        return result


class CppTestParser:
    """C++ make test 输出解析器"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        return GenericTextParser().parse(raw_output)
