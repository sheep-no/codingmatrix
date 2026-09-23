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
import xml.etree.ElementTree as ET
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
    def parse(raw_output: str, output_format: str) -> ParsedTestResult:
        """
        解析测试输出为统一格式

        Args:
            raw_output: 原始测试输出文本
            output_format: 输出格式标识

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

        parser_cls = parsers.get(output_format, GenericTextParser)
        parser = parser_cls()
        return parser.parse(raw_output)


class GenericTextParser:
    """通用文本解析器 - 从文本中提取 passed/failed/ERROR 信息"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        if not raw_output or not raw_output.strip():
            result.errors.append("测试输出为空")
            return result

        passed_match = re.search(r"(\d+)\s+(?:tests?\s+)?passed", raw_output, re.IGNORECASE)
        if passed_match:
            result.passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+(?:tests?\s+)?failed", raw_output, re.IGNORECASE)
        if failed_match:
            result.failed = int(failed_match.group(1))

        error_matches = re.findall(r"ERROR[:\s]+(.+)", raw_output, re.IGNORECASE)
        result.errors = error_matches[:20]

        return result


def _xml_localname(tag: str) -> str:
    """去掉 XML 命名空间前缀，取标签本地名。"""
    return tag.rsplit("}", 1)[-1]


def _xml_child(element, name: str):
    for child in element:
        if _xml_localname(child.tag) == name:
            return child
    return None


def _parse_junit_xml(raw_output: str) -> "ParsedTestResult | None":
    """用 xml.etree 解析 JUnit XML；输入非 XML 或解析失败返回 None。

    以 ``<testcase>`` 元素为准统计：skipped 不计入 passed，failure/error
    计入 failed。相比正则，能正确处理属性顺序、多行内容与命名空间。
    """
    if not raw_output.lstrip().startswith("<"):
        return None
    try:
        root = ET.fromstring(raw_output)
    except ET.ParseError:
        return None

    if _xml_localname(root.tag) not in ("testsuite", "testsuites"):
        return None

    result = ParsedTestResult()
    passed = failed = 0
    for element in root.iter():
        if _xml_localname(element.tag) != "testcase":
            continue
        name = element.get("name", "") or element.get("classname", "")
        if _xml_child(element, "skipped") is not None:
            continue
        failure = _xml_child(element, "failure")
        error = _xml_child(element, "error")
        if failure is not None or error is not None:
            node = failure if failure is not None else error
            message = (node.get("message") or node.text or "").strip()
            failed += 1
            if message:
                result.errors.append(message[:200])
            result.test_cases.append(
                TestCaseResult(name=name, passed=False, error_message=message)
            )
        else:
            passed += 1
            result.test_cases.append(TestCaseResult(name=name, passed=True))

    result.passed = passed
    result.failed = failed
    return result


class PytestXMLParser:
    """pytest 输出解析器

    python_pytest preset 声明的 output_format 是 pytest_xml，但默认命令
    （``pytest -xvs``）输出的是文本。因此先尝试真正的 JUnit XML（--junitxml
    等场景），不是 XML 时回退到 pytest 文本正则。
    """

    def parse(self, raw_output: str) -> ParsedTestResult:
        xml_result = _parse_junit_xml(raw_output)
        if xml_result is not None:
            return xml_result

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
            num_passed = data.get("numPassedTests")
            num_failed = data.get("numFailedTests")

            if num_passed is None or num_failed is None:
                # vitest 等 JSON reporter 不保证 jest 的顶层计数字段，
                # 按 assertionResults[].status 统计（skipped/pending 不计通过）。
                # 原实现直接 .get(..., 0) → vitest 风格输出恒为 0（OP3）。
                num_passed = num_failed = 0
                for test_result in data.get("testResults", []):
                    for assertion in test_result.get("assertionResults", []):
                        status = assertion.get("status")
                        if status == "passed":
                            num_passed += 1
                        elif status == "failed":
                            num_failed += 1

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
    """JUnit XML 输出解析器（优先 xml.etree，非 XML 时回退文本正则）"""

    def parse(self, raw_output: str) -> ParsedTestResult:
        xml_result = _parse_junit_xml(raw_output)
        if xml_result is not None:
            return xml_result

        result = ParsedTestResult()

        tests_match = re.search(r"tests\s*=\s*['\"](\d+)['\"]", raw_output)
        failures_match = re.search(r"failures\s*=\s*['\"](\d+)['\"]", raw_output)
        errors_match = re.search(r"errors\s*=\s*['\"](\d+)['\"]", raw_output)
        skipped_match = re.search(r"skipped\s*=\s*['\"](\d+)['\"]", raw_output)

        total = int(tests_match.group(1)) if tests_match else 0
        failures = int(failures_match.group(1)) if failures_match else 0
        errors_count = int(errors_match.group(1)) if errors_match else 0
        skipped = int(skipped_match.group(1)) if skipped_match else 0

        # JUnit 的 tests 包含 skipped，必须扣除，否则 passed 虚高（OP2）
        result.passed = max(0, total - failures - errors_count - skipped)
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
        # 包级 FAIL 行（编译错误 / panic 未产生 --- FAIL: 用例）也要计入失败。
        # `FAIL\tpkg ...` 与结尾裸 `FAIL` 是同一包失败的两种写法，只计前者，避免重复。
        package_failures = re.findall(r"(?m)^FAIL\s+\S.*$", raw_output)
        if not package_failures and re.search(r"(?m)^FAIL\s*$", raw_output):
            package_failures = ["FAIL"]

        result.passed = pass_count
        result.failed = max(fail_count, len(package_failures))

        for line in raw_output.split("\n"):
            if "--- FAIL:" in line:
                result.errors.append(line.strip())
        for line in package_failures:
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
            if line.strip().startswith("test result:"):
                continue
            if "FAILED" in line and "---" not in line:
                result.errors.append(line.strip())

        return result


class CppTestParser:
    """C++ gtest / catch2 输出解析器"""

    _CATCH2 = re.compile(
        r"test cases:\s*(\d+)\s*\|\s*(\d+)\s+passed\s*\|\s*(\d+)\s+failed",
        re.IGNORECASE,
    )
    _GTEST_PASSED = re.compile(r"\[\s+PASSED\s+\]\s+(\d+)\s+test", re.IGNORECASE)
    _GTEST_FAILED = re.compile(r"\[\s+FAILED\s+\]\s+(\d+)\s+test", re.IGNORECASE)

    def parse(self, raw_output: str) -> ParsedTestResult:
        result = ParsedTestResult()

        catch2 = self._CATCH2.search(raw_output)
        if catch2:
            _, passed, failed = (int(g) for g in catch2.groups())
            result.passed = passed
            result.failed = failed
            if failed:
                result.errors.append(catch2.group(0).strip())
            return result

        passed_match = self._GTEST_PASSED.search(raw_output)
        failed_match = self._GTEST_FAILED.search(raw_output)
        if passed_match or failed_match:
            if passed_match:
                result.passed = int(passed_match.group(1))
            if failed_match:
                result.failed = int(failed_match.group(1))
            for line in raw_output.split("\n"):
                if re.match(r"^\[\s+FAILED\s+\]\s+\S", line):
                    result.errors.append(line.strip())
            return result

        return GenericTextParser().parse(raw_output)
