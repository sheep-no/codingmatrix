"""回归：OT25 测试结果事件 skipped 语义错位、OT24 参数化失败聚类正则注入。"""

from app.agent.output_parser import OutputParser
from app.agent.orchestrator_testing import TestingMixin
from app.agent.test_runner import IsolatedTestRunner, TestResult


class _FakeRunner:
    def __init__(self, result):
        self._result = result

    async def run_tests(self):
        return self._result


class _Host(TestingMixin):
    def __init__(self, result):
        self.output_dir = None
        self.warnings = []
        self.events = []
        self.progress = []

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))

    def _update_phase(self, *args, **kwargs):
        pass

    def _report_warning(self, **kwargs):
        pass

    def _report_test_results(self, test_results):
        self.events.append(test_results)


def _result(**kwargs):
    base = dict(
        success=True,
        total_tests=0,
        passed=0,
        failed=0,
        errors=0,
        logs="",
        failed_tests=[],
    )
    base.update(kwargs)
    return TestResult(**base)


class TestSkippedEvent:
    """OT25: skipped 必须来自真实 skipped 计数，不得填 errors"""

    async def test_event_reports_skipped_not_errors(self):
        result = _result(passed=3, failed=0, errors=2, skipped=5, total_tests=3)
        host = _Host(result)

        await host._run_dynamic_tests(_FakeRunner(result))

        summary = host.events[0]["summary"]
        assert summary["skipped"] == 5
        assert summary["skipped"] != result.errors

    async def test_default_skipped_is_zero(self):
        result = _result(passed=1, failed=0, errors=1, total_tests=1)
        host = _Host(result)

        await host._run_dynamic_tests(_FakeRunner(result))

        assert host.events[0]["summary"]["skipped"] == 0


class TestOutputParserSkipped:
    """skipped 计数从各类解析器透出"""

    def test_pytest_text(self):
        parsed = OutputParser.parse("3 passed, 1 failed, 2 skipped in 0.5s", "pytest_xml")
        assert parsed.skipped == 2

    def test_junit_text_attributes(self):
        raw = '<testsuite tests="10" failures="2" errors="1" skipped="3">'
        parsed = OutputParser.parse(raw, "junit_xml")
        assert parsed.skipped == 3
        assert parsed.passed == 4

    def test_junit_xml_elements(self):
        raw = (
            '<testsuite name="s">'
            '<testcase name="a"/><testcase name="b"><skipped/></testcase>'
            '<testcase name="c"><failure message="boom"/></testcase>'
            "</testsuite>"
        )
        parsed = OutputParser.parse(raw, "junit_xml")
        assert parsed.skipped == 1
        assert parsed.passed == 1
        assert parsed.failed == 1

    def test_jest_pending(self):
        import json

        raw = json.dumps({
            "numPassedTests": 4,
            "numFailedTests": 1,
            "numPendingTests": 2,
        })
        parsed = OutputParser.parse(raw, "jest_json")
        assert parsed.skipped == 2
        assert parsed.passed == 4

    def test_vitest_status_recount(self):
        import json

        raw = json.dumps({
            "testResults": [{
                "assertionResults": [
                    {"status": "passed"}, {"status": "failed"},
                    {"status": "pending"}, {"status": "skipped"},
                ]
            }]
        })
        parsed = OutputParser.parse(raw, "jest_json")
        assert (parsed.passed, parsed.failed, parsed.skipped) == (1, 1, 2)

    def test_go_skip(self):
        raw = "--- PASS: TestA\n--- SKIP: TestB\nok  pkg 0.1s\n"
        parsed = OutputParser.parse(raw, "go_json")
        assert parsed.skipped == 1

    def test_rust_ignored(self):
        raw = "test result: ok. 2 passed; 0 failed; 1 ignored; 0 measured"
        parsed = OutputParser.parse(raw, "rust_text")
        assert parsed.skipped == 1


class TestTestRunnerSkipped:
    """TestResult.skipped 由 OutputParser 结果透传"""

    def test_parse_with_output_parser_sets_skipped(self):
        runner = IsolatedTestRunner.__new__(IsolatedTestRunner)
        runner._detected_config = None
        result = _result(logs="3 passed, 1 skipped in 0.4s")

        runner._parse_with_output_parser(result)

        assert result.skipped == 1
        assert result.passed == 3


class TestFailureClusterRegex:
    """OT24: 参数化测试名含正则元字符 + 单行日志取错行"""

    async def test_parameterized_name_keeps_error_message(self):
        host = TestingMixin()
        logs = "FAILED tests/test_x.py::test_y[1-2] - AssertionError: nope\n"

        clusters = await host._cluster_test_failures(
            ["tests/test_x.py::test_y[1-2]"], logs
        )

        # 未转义时 re.search 匹配失败，error 为空；转义后保留真实错误信息
        assert clusters[0].tests[0]["error"]
        assert "AssertionError" in clusters[0].tests[0]["error"]

    async def test_single_line_log_does_not_abort_clustering(self):
        host = TestingMixin()
        logs = "FAILED tests/test_x.py::test_plain - AssertionError: boom\n"

        clusters = await host._cluster_test_failures(
            ["tests/test_x.py::test_plain"], logs
        )

        # 原实现 traceback.split('\n')[-2] 对单行日志抛 IndexError，回退 []
        assert clusters
        assert clusters[0].tests[0]["error"]
