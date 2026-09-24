"""回归：failure_clusterer FC1/FC2/FC3/FC5。"""

from app.agent.failure_clusterer import FailureClusterer


class TestParseTracebackLocation:
    """FC2: pytest 短格式（file.py:line: in func）位置不再恒空"""

    def test_pytest_short_format_location(self):
        tb = (
            "FAILED tests/test_x.py::test_y - AssertionError: x\n"
            "______________________ test_y ______________________\n\n"
            "    def test_y():\n"
            ">       assert foo\n"
            "E       AssertionError: x\n\n"
            "tests/test_x.py:12: in test_y\n"
        )
        error_type, location, keywords = FailureClusterer()._parse_traceback(tb)
        assert location == "tests/test_x.py:12"
        assert error_type == "AssertionError"
        assert keywords

    def test_pytest_short_format_final_line_only(self):
        tb = "FAILED tests/test_x.py::test_y - Boom\n\ntests/test_x.py:12: BoomError\n"
        error_type, location, _ = FailureClusterer()._parse_traceback(tb)
        assert location == "tests/test_x.py:12"
        assert error_type == "BoomError"

    def test_standard_python_traceback_unchanged(self):
        tb = (
            'Traceback (most recent call last):\n'
            '  File "/proj/app/util.py", line 42, in run\n'
            "    x()\n"
            "ValueError: bad\n"
        )
        error_type, location, _ = FailureClusterer()._parse_traceback(tb)
        assert error_type == "ValueError"
        assert location == "/proj/app/util.py:42"


class TestKeywordExtraction:
    """FC3: traceback 以空行结尾时关键词不再恒空"""

    def test_trailing_blank_line_still_yields_keyword(self):
        tb = "Traceback:\nE   AssertionError: boom\n\n"
        _, _, keywords = FailureClusterer()._parse_traceback(tb)
        assert keywords
        assert any("AssertionError" in k for k in keywords)

    def test_empty_traceback(self):
        assert FailureClusterer()._parse_traceback("") == ("Unknown", "", [])


class TestMissingName:
    """FC5: test_results 项缺 name 字段不再 KeyError"""

    def test_missing_name_does_not_raise(self):
        clusters = FailureClusterer().cluster([
            {"traceback": "ValueError: a\n", "error_message": "a"},
            {"traceback": "ValueError: b\n", "error_message": "b"},
        ])
        assert clusters
        assert clusters[0].tests[0]["name"] == ""


class TestLocationNormalization:
    """FC1: 聚类键位置去行号、去绝对路径前缀"""

    def test_trailing_two_components(self):
        assert FailureClusterer._normalize_location("/proj/app/util.py:42") == "app/util.py"
        assert FailureClusterer._normalize_location("tests/test_x.py:12") == "tests/test_x.py"
        assert FailureClusterer._normalize_location("/a/b/c/d.py:7") == "c/d.py"
        assert FailureClusterer._normalize_location("util.py:1") == "util.py"
        assert FailureClusterer._normalize_location("") == ""
