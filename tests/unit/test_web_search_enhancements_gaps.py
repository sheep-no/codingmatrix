"""补齐 web_search_enhancements 的增强与提取分支。"""

import pytest

from app.utils.web_search import SearchResult
from app.utils.web_search_enhancements import (
    _extract_school_name,
    enhance_query,
    score_search_result,
)


class TestEnhanceQueryBranches:
    def test_disabled_returns_query(self):
        assert enhance_query("python error", enable_enhance=False) == "python error"

    def test_error_with_existing_stackoverflow_site(self):
        query = "python error site:stackoverflow.com"

        assert enhance_query(query) == query

    def test_technical_code_with_existing_github_site(self):
        query = "python code site:github.com"

        assert enhance_query(query) == query

    def test_technical_api_with_official(self):
        query = "python api official"

        assert enhance_query(query) == query

    def test_technical_api_with_github_site(self):
        query = "python api site:github.com"

        assert enhance_query(query) == query

    def test_technical_api_adds_official_docs(self):
        result = enhance_query("python api")

        assert "official documentation" in result

    def test_technical_general_with_github_site(self):
        query = "python site:github.com"

        assert enhance_query(query) == query

    def test_technical_general_with_stackoverflow_site(self):
        query = "python site:stackoverflow.com"

        assert enhance_query(query) == query

    def test_technical_general_adds_tutorial_sites(self):
        result = enhance_query("python")

        assert "tutorial" in result
        assert "site:github.com" in result

    def test_gov_query(self):
        result = enhance_query("政策 规定")

        assert result.endswith("site:gov.cn")

    def test_gov_query_with_existing_site(self):
        query = "政策 site:gov.cn"

        assert enhance_query(query) == query

    def test_company_query(self):
        result = enhance_query("公司 注册资本")

        assert result.endswith("官网")

    def test_company_query_with_existing_official(self):
        query = "公司 官网"

        assert enhance_query(query) == query

    def test_tutorial_query(self):
        result = enhance_query("摄影 教程")

        assert "complete guide" in result

    def test_tutorial_query_with_existing_guide(self):
        query = "摄影 guide"

        assert enhance_query(query) == query

    def test_news_query(self):
        result = enhance_query("最新 新闻")

        assert "site:reuters.com" in result

    def test_news_query_with_existing_site(self):
        query = "news site:reuters.com"

        assert enhance_query(query) == query

    def test_school_extracts_name(self):
        result = enhance_query("清华大学计算机专业")

        assert result == "清华大学 官网"

    def test_school_without_extractable_name(self):
        query = "学院"

        assert enhance_query(query) == query

    def test_plain_query_unchanged(self):
        assert enhance_query("天气") == "天气"


class TestExtractSchoolName:
    def test_college_suffix(self):
        assert _extract_school_name("北京大学计算机") == "北京大学"

    def test_vocational_suffix(self):
        assert _extract_school_name("某某职业技术学院") == "某某职业技术学院"

    def test_too_short_returns_empty(self):
        assert _extract_school_name("学院") == ""

    def test_no_school_suffix(self):
        assert _extract_school_name("清华大学") == "清华大学"


class TestScoreSearchResult:
    def test_high_quality_domain(self):
        assert score_search_result(
            SearchResult(title="x", url="https://github.com/a", snippet="")
        ) == 0.4

    def test_title_tutorial_bonus(self):
        score = score_search_result(
            SearchResult(title="A practical tutorial for everyone", url="https://x.com", snippet="")
        )

        # 标题长度 > 20 得 0.1，含 tutorial 得 0.2
        assert score == pytest.approx(0.3)

    def test_long_snippet_bonus(self):
        snippet = "a" * 120
        score = score_search_result(
            SearchResult(title="x", url="https://x.com", snippet=snippet)
        )

        assert score == pytest.approx(0.2)

    def test_date_in_url(self):
        score = score_search_result(
            SearchResult(title="x", url="https://x.com/2024-01-02/post", snippet="")
        )

        assert score == pytest.approx(0.1)
