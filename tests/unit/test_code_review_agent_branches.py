"""CodeReviewAgent 文件分派、各语言规则与项目报告测试。"""

from pathlib import Path

import pytest

import app.utils.review.code_review_agent as cra
from app.utils.review.code_review_agent import (
    CodeReviewAgent,
    ReviewCategory,
    SeverityLevel,
    review_project,
)


def _messages(issues):
    return [issue.message for issue in issues]


class TestReviewFileDispatch:
    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        warnings = []
        monkeypatch.setattr(cra.logger, "warning", lambda message: warnings.append(message))
        agent = CodeReviewAgent()

        assert agent.review_file(tmp_path / "absent.py") == []
        assert warnings == [f"文件不存在：{tmp_path / 'absent.py'}"]

    def test_python_extension_uses_python_rules(self, tmp_path):
        path = tmp_path / "bad.py"
        path.write_text("def f():\n    eval('1')\n", encoding="utf-8")

        issues = CodeReviewAgent().review_file(path, "py")

        assert any(i.category is ReviewCategory.SECURITY for i in issues)

    @pytest.mark.parametrize("lang", ["python", "PYTHON"])
    def test_python_language_case_insensitive(self, tmp_path, lang):
        path = tmp_path / "x.py"
        path.write_text("print(1)\n", encoding="utf-8")

        assert any("logging" in m for m in _messages(CodeReviewAgent().review_file(path, lang)))

    @pytest.mark.parametrize("lang", ["javascript", "js", "ts", "tsx", "jsx"])
    def test_javascript_family_uses_js_rules(self, tmp_path, lang):
        path = tmp_path / "x.js"
        path.write_text("var a = 1;\n", encoding="utf-8")

        issues = CodeReviewAgent().review_file(path, lang)

        assert any("let/const" in m for m in _messages(issues))

    def test_unknown_language_uses_generic(self, tmp_path):
        path = tmp_path / "x.go"
        path.write_text("x" * 160 + "\n", encoding="utf-8")

        issues = CodeReviewAgent().review_file(path, "go")

        assert any("行过长" in m for m in _messages(issues))


class TestPythonRules:
    def test_syntax_error_reports_style_error(self):
        issues = CodeReviewAgent().review_python_code("def f(:\n", "bad.py")

        assert issues[0].category is ReviewCategory.STYLE
        assert issues[0].severity is SeverityLevel.ERROR
        assert "语法错误" in issues[0].message

    def test_syntax_error_without_line_uses_empty_snippet(self, monkeypatch):
        def raise_without_line(_code):
            raise SyntaxError("bad", ("bad.py", None, None, None))

        monkeypatch.setattr(cra.ast, "parse", raise_without_line)

        issues = CodeReviewAgent().review_python_code("anything", "bad.py")

        assert issues[0].line == 0
        assert issues[0].column == 0
        assert issues[0].code_snippet == ""

    def test_long_function_and_missing_docstring(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(52))
        code = f"def long_func():\n{body}\n"

        issues = CodeReviewAgent().review_python_code(code, "m.py")

        messages = _messages(issues)
        assert any("函数过长" in m for m in messages)
        assert any("文档字符串" in m for m in messages)

    def test_function_with_docstring_skips_doc_issue(self):
        issues = CodeReviewAgent().review_python_code(
            'def f():\n    """doc"""\n    return 1\n', "m.py"
        )

        assert all("文档字符串" not in m for m in _messages(issues))

    def test_exception_handler_rule(self):
        issues = CodeReviewAgent().review_python_code(
            "try:\n    x = 1\nexcept Exception:\n    pass\n", "m.py"
        )

        assert any("裸 except" in m for m in _messages(issues))

    def test_specific_exception_is_allowed(self):
        issues = CodeReviewAgent().review_python_code(
            "try:\n    x = 1\nexcept ValueError:\n    pass\n", "m.py"
        )

        assert all("裸 except" not in m for m in _messages(issues))

    def test_eval_and_exec_are_critical(self):
        issues = CodeReviewAgent().review_python_code(
            "eval('1')\nexec('x=1')\n", "m.py"
        )

        calls = [i for i in issues if "存在安全风险" in i.message]
        assert len(calls) == 2
        assert all(i.severity is SeverityLevel.CRITICAL for i in calls)

    def test_print_rule_skips_comments(self):
        issues = CodeReviewAgent().review_python_code(
            "# print(debug)\nprint('real')\n", "m.py"
        )

        prints = [i for i in issues if "logging" in i.message]
        assert len(prints) == 1
        assert prints[0].line == 2

    def test_todo_and_hardcoded_password(self):
        code = "# TODO: rotate\npassword = 'hunter2'\n"

        issues = CodeReviewAgent().review_python_code(code, "m.py")

        messages = _messages(issues)
        assert any("待处理标记" in m for m in messages)
        assert any("硬编码密码" in m for m in messages)

    def test_security_skill_flags_sql_concatenation(self):
        agent = CodeReviewAgent(skills=["security"])

        issues = agent.review_python_code(
            "cursor.execute('select * from t where id=' + uid)\n", "m.py"
        )

        assert any("注入风险" in m for m in _messages(issues))

    def test_security_skill_disabled_skips_sql_rule(self):
        agent = CodeReviewAgent(skills=["production"])

        issues = agent.review_python_code(
            "cursor.execute('select * from t where id=' + uid)\n", "m.py"
        )

        assert all("注入风险" not in m for m in _messages(issues))

    def test_production_skill_flags_relative_import_escape(self):
        agent = CodeReviewAgent(skills=["production"])

        issues = agent.review_python_code("from .. import thing\n", "m.py")

        assert any("相对导入" in m for m in _messages(issues))

    def test_production_skill_disabled_skips_relative_import(self):
        agent = CodeReviewAgent(skills=["security"])

        issues = agent.review_python_code("from .. import thing\n", "m.py")

        assert all("相对导入" not in m for m in _messages(issues))


class TestJavaScriptRules:
    def test_console_eval_and_var(self):
        code = "console.log('x')\neval('y')\nvar z = 1\n"

        issues = CodeReviewAgent().review_javascript_code(code, "a.js")

        messages = _messages(issues)
        assert any("console.log" in m for m in messages)
        assert any("eval" in m for m in messages)
        assert any("let/const" in m for m in messages)

    def test_accessibility_skill_disabled_skips_images(self):
        agent = CodeReviewAgent(skills=["security"])

        issues = agent.review_javascript_code("<img src='a.png'>", "a.js")

        assert all(i.category is not ReviewCategory.ACCESSIBILITY for i in issues)

    def test_documentation_skill_has_no_js_rules(self):
        agent = CodeReviewAgent(skills=["documentation"])

        assert agent.review_javascript_code("const a = 1\n", "a.js") == []


class TestGenericRules:
    def test_long_file(self):
        code = "\n".join("x" for _ in range(501))

        issues = CodeReviewAgent().review_generic_code(code, "a.go")

        assert any("文件过长" in m for m in _messages(issues))

    def test_long_line_snippet_truncated(self):
        issues = CodeReviewAgent().review_generic_code("y" * 200, "a.go")

        assert issues[0].line == 1
        assert issues[0].column == 150
        assert len(issues[0].code_snippet) == 100

    def test_short_code_passes(self):
        assert CodeReviewAgent().review_generic_code("small\n", "a.go") == []


class TestReport:
    def test_project_report_uses_language_specific_rules(self, tmp_path):
        (tmp_path / "a.py").write_text("def f():\n    eval('1')\n", encoding="utf-8")
        (tmp_path / "b.js").write_text("var a = 1\n", encoding="utf-8")

        report = CodeReviewAgent(skills=["production", "security"]).get_review_report(tmp_path)

        assert report["total_files"] == 2
        assert report["total_issues"] >= 2
        assert report["passed"] is False
        assert report["by_severity"]["critical"] >= 1
        assert report["by_category"]["style"] >= 1

    def test_clean_project_passes(self, tmp_path):
        (tmp_path / "a.py").write_text('def f():\n    """doc"""\n    return 1\n', encoding="utf-8")

        report = CodeReviewAgent().get_review_report(tmp_path)

        assert report["total_files"] == 1
        assert report["total_issues"] == 0
        assert report["passed"] is True

    def test_repeated_category_is_accumulated(self, tmp_path):
        (tmp_path / "a.js").write_text("var a = 1\n", encoding="utf-8")
        (tmp_path / "b.js").write_text("var b = 2\n", encoding="utf-8")

        report = CodeReviewAgent().get_review_report(tmp_path)

        assert report["by_category"]["style"] == 2

    def test_unknown_skills_are_ignored(self):
        assert CodeReviewAgent(skills=["nope"]).enabled_prompts == {}

    def test_review_project_helper(self, tmp_path):
        (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")

        report = review_project(tmp_path, skills=["production"])

        assert report["total_files"] == 1
        assert report["total_issues"] >= 1

    def test_issue_payload_shape(self, tmp_path):
        (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")

        issue = CodeReviewAgent().get_review_report(tmp_path)["issues"][0]

        assert set(issue) == {
            "file", "line", "category", "severity", "message", "suggestion", "skill_tag"
        }
