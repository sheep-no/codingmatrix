"""ProjectProfiler 风险区/测试目录启发式修复回归（PP5/PP8/PP10）。

- PP8：风险关键字原先按子串匹配，`db` 会命中任意含 db 的文本；改为整词匹配。
- PP10：外部包（flask/requests/numpy）原先被计入 high_dependency；Python 下改为
  「项目内存在对应源文件」判据。
- PP5：`_is_test_dir` 原先按子串匹配，`contest`/`latested` 误判为测试目录；改为整名匹配。
"""

from __future__ import annotations

from app.agent.project_profiler import (
    ProjectProfiler,
    _contains_keyword,
    LANGUAGE_PROFILES,
)


class TestLanguageNormalization:
    def test_typescript_uses_javascript_profile(self, tmp_path):
        profiler = ProjectProfiler(str(tmp_path), language="typescript")
        assert profiler.language == "javascript"
        assert profiler.profile_rules is LANGUAGE_PROFILES["javascript"]

    def test_ts_alias_uses_javascript_profile(self, tmp_path):
        assert ProjectProfiler(str(tmp_path), language="ts").language == "javascript"

    def test_unknown_language_still_falls_back_to_python(self, tmp_path):
        assert ProjectProfiler(str(tmp_path), language="cobol").language == "python"


class TestKeywordMatching:
    def test_short_keyword_not_matched_inside_word(self):
        keywords = ProjectProfiler.DATABASE_KEYWORDS
        assert _contains_keyword("dbserver and mongodb pool", keywords) is False

    def test_standalone_keyword_matches(self):
        keywords = ProjectProfiler.DATABASE_KEYWORDS
        assert _contains_keyword("open the db connection", keywords) is True

    def test_hyphenated_keyword_matches(self):
        keywords = ProjectProfiler.SECURITY_KEYWORDS
        assert _contains_keyword("config for spring-security", keywords) is True

    def test_risk_areas_ignore_substring_false_positive(self, tmp_path):
        (tmp_path / "webapp.py").write_text(
            "value = 'web editor dashboard'\n", encoding="utf-8"
        )
        profiler = ProjectProfiler(str(tmp_path), language="python")
        risks = profiler._analyze_risk_areas(tmp_path)
        assert risks.data_critical == []


class TestExternalPackageFiltering:
    def test_external_packages_excluded_from_high_dependency(self, tmp_path):
        (tmp_path / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
        for i in range(5):
            (tmp_path / f"mod_{i}.py").write_text(
                "import flask\nimport requests\nimport numpy\nimport helpers\n",
                encoding="utf-8",
            )

        profiler = ProjectProfiler(str(tmp_path), language="python")
        risks = profiler._analyze_risk_areas(tmp_path)

        assert "helpers.py" in risks.high_dependency
        assert "flask.py" not in risks.high_dependency
        assert "requests.py" not in risks.high_dependency
        assert "numpy.py" not in risks.high_dependency

    def test_dotted_package_init_is_project_module(self, tmp_path):
        pkg = tmp_path / "app" / "utils"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        profiler = ProjectProfiler(str(tmp_path), language="python")
        assert profiler._is_project_module("app.utils", tmp_path) is True

    def test_missing_module_is_external(self, tmp_path):
        profiler = ProjectProfiler(str(tmp_path), language="python")
        assert profiler._is_project_module("flask", tmp_path) is False


class TestTestDirMatching:
    def test_exact_test_dir_names(self, tmp_path):
        profiler = ProjectProfiler(str(tmp_path), language="python")
        assert profiler._is_test_dir(str(tmp_path / "tests")) is True
        assert profiler._is_test_dir(str(tmp_path / "test")) is True

    def test_substring_names_rejected(self, tmp_path):
        profiler = ProjectProfiler(str(tmp_path), language="python")
        assert profiler._is_test_dir(str(tmp_path / "contest")) is False
        assert profiler._is_test_dir(str(tmp_path / "latested")) is False
