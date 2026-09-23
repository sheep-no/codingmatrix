"""OutputParser 回归（OP1 / OP2 / OP3）。

OP1: PytestXMLParser 声明解析 XML，原实现只按文本正则 → 真 JUnit XML 全 0。
OP2: JUnitXMLParser 的 passed 未扣除 skipped → 通过数虚高。
OP3: JestJSONParser 只认 jest 顶层字段 → vitest 风格 JSON 全 0。
"""
from app.agent.output_parser import (
    JestJSONParser,
    JUnitXMLParser,
    OutputParser,
    PytestXMLParser,
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
