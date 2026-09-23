"""OutputParser 回归（OP1-OP8）。

OP1: PytestXMLParser 声明解析 XML，原实现只按文本正则 → 真 JUnit XML 全 0。
OP2: JUnitXMLParser 的 passed 未扣除 skipped → 通过数虚高。
OP3: JestJSONParser 只认 jest 顶层字段 → vitest 风格 JSON 全 0。
OP4: GoTestParser 漏掉包级 FAIL（编译错误/panic）→ failed 恒 0。
OP5: RustTestParser 把 `test result:` 摘要行当作 error 噪声。
OP6: GenericTextParser 正则过窄 / errors 大小写敏感。
OP7: CppTestParser 纯委托 GenericTextParser，gtest/catch2 计数失真。
OP8: `parse` 参数名 `format` 遮蔽内置。
"""
from app.agent.output_parser import (
    CppTestParser,
    GenericTextParser,
    GoTestParser,
    JestJSONParser,
    JUnitXMLParser,
    OutputParser,
    PytestXMLParser,
    RustTestParser,
)


class TestPytestXMLParser:
    def test_real_junit_xml_is_parsed(self):
        """OP1: 真 XML 输入必须得到真实计数，而非全 0。"""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<testsuites>\n"
            '  <testsuite name="s" tests="3" failures="1" errors="0" skipped="1">\n'
            '    <testcase classname="a" name="t1"/>\n'
            '    <testcase classname="a" name="t2">\n'
            '      <failure message="boom">trace</failure>\n'
            "    </testcase>\n"
            '    <testcase classname="a" name="t3"><skipped/></testcase>\n'
            "  </testsuite>\n"
            "</testsuites>\n"
        )

        result = PytestXMLParser().parse(xml)

        assert result.passed == 1
        assert result.failed == 1
        assert any("boom" in e for e in result.errors)

    def test_text_output_falls_back_to_regex(self):
        result = PytestXMLParser().parse("3 passed, 1 failed in 0.5s")

        assert result.passed == 3
        assert result.failed == 1

    def test_namespaced_xml_testcases_are_counted(self):
        xml = (
            '<testsuite xmlns="urn:junit" tests="2" failures="0">'
            '<testcase name="t1"/><testcase name="t2"/>'
            "</testsuite>"
        )

        result = PytestXMLParser().parse(xml)

        assert result.passed == 2

    def test_non_xml_markup_falls_back(self):
        """以 < 开头但非 JUnit 结构时不崩溃，回退文本解析。"""
        result = PytestXMLParser().parse("<html>2 passed</html>")

        assert result.passed == 2


class TestJUnitXMLParser:
    def test_xml_path_excludes_skipped_from_passed(self):
        xml = (
            '<testsuite tests="10" failures="2" errors="1" skipped="3">'
            + "".join(
                f'<testcase name="t{i}"/>' for i in range(4)
            )
            + '<testcase name="f1"><failure message="f1"/></testcase>'
            + '<testcase name="f2"><failure message="f2"/></testcase>'
            + '<testcase name="e1"><error message="e1"/></testcase>'
            + '<testcase name="s1"><skipped/></testcase>'
            + '<testcase name="s2"><skipped/></testcase>'
            + '<testcase name="s3"><skipped/></testcase>'
            + "</testsuite>"
        )

        result = JUnitXMLParser().parse(xml)

        assert result.passed == 4
        assert result.failed == 3

    def test_regex_fallback_subtracts_skipped(self):
        """OP2: 非 XML 文本属性形式也必须扣除 skipped。"""
        text = 'tests="10" failures="2" errors="1" skipped="3"'

        result = JUnitXMLParser().parse(text)

        assert result.passed == 4
        assert result.failed == 3

    def test_regex_fallback_without_skipped_unchanged(self):
        result = JUnitXMLParser().parse('tests="10" failures="2"')

        assert result.passed == 8
        assert result.failed == 2


class TestJestJSONParser:
    def test_jest_top_level_counts(self):
        payload = '{"numPassedTests": 5, "numFailedTests": 2, "testResults": []}'

        result = JestJSONParser().parse(payload)

        assert result.passed == 5
        assert result.failed == 2

    def test_vitest_style_json_counts_assertions(self):
        """OP3: 缺少 jest 顶层字段时按 assertionResults 状态统计。"""
        payload = (
            '{"numTotalTestSuites": 1, "success": false, "testResults": ['
            '{"assertionResults": ['
            '{"status": "passed", "fullName": "a"},'
            '{"status": "failed", "fullName": "b", "failureMessages": ["x"]},'
            '{"status": "pending", "fullName": "c"}'
            "]}]}"
        )

        result = JestJSONParser().parse(payload)

        assert result.passed == 1
        assert result.failed == 1

    def test_non_json_falls_back_to_text(self):
        result = JestJSONParser().parse("2 passed, 1 failed")

        assert result.passed == 2
        assert result.failed == 1


class TestOutputParserDispatch:
    def test_unknown_format_uses_generic(self):
        result = OutputParser.parse("7 passed, 0 failed", "totally_unknown")

        assert result.passed == 7
        assert result.failed == 0

    def test_parse_accepts_output_format_keyword(self):
        """OP8: 参数已改名 output_format，关键字调用可用。"""
        result = OutputParser.parse("1 passed, 0 failed", output_format="rust_text")

        assert result.passed == 1


class TestGoTestParser:
    def test_package_level_fail_is_counted(self):
        """OP4: 编译错误只输出包级 FAIL，failed 不能恒 0。"""
        output = (
            "# example.com/pkg\n"
            "./foo_test.go:5:2: undefined: bar\n"
            "FAIL\texample.com/pkg [build failed]\n"
            "FAIL\n"
        )

        result = GoTestParser().parse(output)

        assert result.failed == 1
        assert any("build failed" in e for e in result.errors)

    def test_panic_fail_is_counted(self):
        output = "panic: boom\nFAIL\texample.com/pkg\t0.01s\n"

        result = GoTestParser().parse(output)

        assert result.failed == 1

    def test_case_and_package_fail_not_double_counted(self):
        output = (
            "--- PASS: TestAdd (0.00s)\n"
            "--- FAIL: TestSub (0.00s)\n"
            "FAIL\n"
        )

        result = GoTestParser().parse(output)

        assert result.passed == 1
        assert result.failed == 1


class TestRustTestParser:
    def test_summary_line_is_not_an_error(self):
        """OP5: `test result:` 摘要是统计行，不是错误明细。"""
        output = (
            "running 2 tests\n"
            "test t1 ... FAILED\n"
            "test result: FAILED. 1 passed; 1 failed; 0 ignored\n"
        )

        result = RustTestParser().parse(output)

        assert not any("test result:" in e for e in result.errors)
        assert any("t1" in e for e in result.errors)


class TestGenericTextParser:
    def test_singular_test_passed_form(self):
        """OP6: 兼容 `1 test passed` 形态。"""
        result = GenericTextParser().parse("1 test passed, 2 tests failed")

        assert result.passed == 1
        assert result.failed == 2

    def test_error_matching_is_case_insensitive(self):
        """OP6: 小写 error 也要收集。"""
        result = GenericTextParser().parse("3 passed, 0 failed\nError: boom")

        assert result.errors


class TestCppTestParser:
    def test_gtest_summary_is_parsed(self):
        """OP7: gtest 摘要行给出真实计数。"""
        output = (
            "[==========] 2 tests from 1 test suite ran. (0 ms total)\n"
            "[  PASSED  ] 1 test.\n"
            "[  FAILED  ] 1 test, listed below:\n"
            "[  FAILED  ] Foo.Baz\n"
        )

        result = CppTestParser().parse(output)

        assert result.passed == 1
        assert result.failed == 1
        assert any("Foo.Baz" in e for e in result.errors)

    def test_catch2_summary_is_parsed(self):
        output = (
            "===============================================================================\n"
            "test cases: 5 | 4 passed | 1 failed\n"
            "assertions: 8 | 7 passed | 1 failed\n"
        )

        result = CppTestParser().parse(output)

        assert result.passed == 4
        assert result.failed == 1

    def test_unknown_cpp_output_falls_back_to_generic(self):
        result = CppTestParser().parse("3 passed, 0 failed")

        assert result.passed == 3
