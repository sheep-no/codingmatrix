import pytest
from app.utils.web_search import (
    SearchResult,
    extract_query_terms,
    filter_relevant_results,
    merge_results_by_url,
    relevance_score,
)


def _item(title, url, snippet=""):
    return SearchResult(title=title, url=url, snippet=snippet, source="Bing")


def test_extract_query_terms_keeps_version_and_cjk():
    terms = extract_query_terms("Python 3.12 新特性")
    assert terms["versions"] == ["3.12"]
    assert "python" in terms["english"]
    assert "新特性" in terms["cjk"]


def test_filter_drops_generic_python_homepage():
    query = "Python 3.12 新特性"
    results = [
        _item("Welcome to Python.org", "https://www.python.org/", "Python Software Foundation"),
        _item("Download Python", "https://www.python.org/downloads/", "Python 3.11.0 artifacts"),
        _item(
            "What's New In Python 3.12",
            "https://docs.python.org/3/whatsnew/3.12.html",
            "New features in Python 3.12",
        ),
    ]
    kept = filter_relevant_results(results, query)
    assert [item.url for item in kept] == ["https://docs.python.org/3/whatsnew/3.12.html"]


def test_filter_drops_beijing_portal_for_forbidden_city_hours():
    query = "北京故宫开放时间"
    results = [
        _item("北京市_百度百科", "https://baike.baidu.com/item/北京市/126069", "北京市简称京"),
        _item("北京市人民政府", "https://www.beijing.gov.cn/", "第一时间权威发布北京市政策"),
        _item("故宫博物院开放时间", "https://www.dpm.org.cn/visit.html", "故宫博物院参观开放时间"),
    ]
    kept = filter_relevant_results(results, query)
    assert kept[0].url == "https://www.dpm.org.cn/visit.html"
    assert all("故宫" in item.title or "故宫" in item.snippet for item in kept)


def test_filter_returns_empty_when_nothing_matches():
    query = "Python 3.12 新特性"
    results = [
        _item("Welcome to Python.org", "https://www.python.org/", "The Python Software Foundation"),
    ]
    assert filter_relevant_results(results, query) == []


def test_merge_results_by_url_skips_duplicates_and_empty():
    left = [_item("A", "https://example.test/x/"), _item("empty", "")]
    right = [_item("A dup", "https://example.test/x"), _item("B", "https://example.test/y")]
    merged = merge_results_by_url([left, right])
    assert [item.url for item in merged] == ["https://example.test/x/", "https://example.test/y"]


def test_relevance_score_rewards_version_hits():
    terms = extract_query_terms("Python 3.12 新特性")
    weak = relevance_score(_item("Python", "https://www.python.org/", "language"), terms)
    strong = relevance_score(
        _item("Python 3.12 新特性", "https://docs.python.org/zh-cn/3.12/whatsnew/3.12.html", "新特性"),
        terms,
    )
    assert strong > weak
    assert strong >= 0.4
    assert weak < 0.4


def test_generic_time_word_does_not_save_unrelated_portal():
    query = "北京故宫开放时间"
    portal = _item(
        "Beijing -北京市人民政府门户网站",
        "https://www.beijing.gov.cn/",
        "第一时间权威发布北京市政策",
    )
    kept = filter_relevant_results([portal], query)
    assert kept == []


def test_filter_requires_opening_hours_phrase():
    query = "北京故宫开放时间"
    listicle = _item(
        "北京250个游玩景点",
        "https://zhuanlan.zhihu.com/p/348180293",
        "故宫：东城区景山前街4号 门票：20/人 周一闭馆",
    )
    official = _item("故宫博物院开放时间", "https://www.dpm.org.cn/visit.html", "参观开放时间")
    kept = filter_relevant_results([listicle, official], query)
    assert [item.url for item in kept] == ["https://www.dpm.org.cn/visit.html"]


def test_search_query_variants_adds_english_whats_new():
    from app.utils.web_search import search_query_variants
    variants = search_query_variants("Python 3.12 新特性")
    assert variants[0] == "Python 3.12 新特性"
    assert any("what's new" in item for item in variants)


def test_search_query_variants_adds_national_statistical_bulletin():
    from app.utils.web_search import search_query_variants
    variants = search_query_variants("2025中国就业数据")
    assert "2025年国民经济和社会发展统计公报" in variants


def test_official_reference_results_for_python_changelog():
    from app.utils.web_search import official_reference_results
    urls = [item.url for item in official_reference_results("Python 3.12 新特性")]
    assert "https://docs.python.org/3.12/whatsnew/3.12.html" in urls
    assert "https://docs.python.org/zh-cn/3.12/whatsnew/3.12.html" in urls
    assert official_reference_results("今天天气怎么样") == []


def test_parse_wikipedia_search_builds_wiki_urls():
    from app.utils.web_search import parse_wikipedia_search
    payload = {
        "query": {
            "search": [
                {"title": "故宫博物院", "snippet": "<span>故宫</span>博物院位于北京"},
                {"title": "", "snippet": "skip"},
            ]
        }
    }
    items = parse_wikipedia_search(payload, "zh")
    assert len(items) == 1
    assert items[0].url.endswith("/wiki/%E6%95%85%E5%AE%AB%E5%8D%9A%E7%89%A9%E9%99%A2")
    assert "故宫" in items[0].snippet
    assert "<span>" not in items[0].snippet


def test_wiki_fallback_keeps_entity_without_hours_phrase():
    query = "北京故宫开放时间"
    wiki = _item("故宫博物院", "https://zh.wikipedia.org/wiki/故宫博物院", "明清两代的皇家宫殿")
    kept = filter_relevant_results([wiki], query, require_phrase=False)
    assert [item.url for item in kept] == ["https://zh.wikipedia.org/wiki/故宫博物院"]


def test_title_has_core_entity_drops_side_pages():
    from app.utils.web_search import title_has_core_entity
    query = "北京故宫开放时间"
    assert title_has_core_entity(_item("故宫博物院", "https://zh.wikipedia.org/wiki/x"), query)
    assert not title_has_core_entity(_item("神武門", "https://zh.wikipedia.org/wiki/y"), query)

@pytest.mark.asyncio
async def test_search_uses_official_docs_when_serp_empty(monkeypatch):
    from app.utils.web_search import FreeWebSearch

    searcher = FreeWebSearch()

    async def empty(*_args, **_kwargs):
        return []

    monkeypatch.setattr(searcher, "_search_baidu", empty)
    monkeypatch.setattr(searcher, "_search_duckduckgo", empty)
    monkeypatch.setattr(searcher, "_search_wikipedia", empty)
    results = await searcher.search("Python 3.12 新特性", count=3)
    assert any("whatsnew/3.12.html" in item.url for item in results)


@pytest.mark.asyncio
async def test_search_discovers_school_employment_pages(monkeypatch):
    from app.utils.web_search import FreeWebSearch

    searcher = FreeWebSearch()
    query = "广州铁路职业技术学院的近三年就业数据"

    async def fake_bing(q, *_args, **_kwargs):
        if q == "广州铁路职业技术学院":
            return [_item("广州铁路职业技术学院", "https://www.gtxy.edu.cn/", "学校官网")]
        return [_item("广州市人民政府门户网站", "https://www.gz.gov.cn/", "广州旅游")]

    async def empty(*_args, **_kwargs):
        return []

    async def fake_fetch(url):
        assert url.startswith("https://www.gtxy.edu.cn")
        return (
            "<html><a href=\"javascript:openexternallink("
            "'aHR0cCUzYSUyZiUyZnNmenkuZ3R4eS5jbiUyZnpqYyUyZg==')\">招生就业</a></html>"
        )

    monkeypatch.setattr(searcher, "_search_baidu", fake_bing)
    monkeypatch.setattr(searcher, "_search_duckduckgo", empty)
    monkeypatch.setattr(searcher, "_search_wikipedia", empty)
    monkeypatch.setattr(searcher, "_fetch_html", fake_fetch)
    results = await searcher.search(query, count=5)
    assert [item.url for item in results] == ["http://sfzy.gtxy.cn/zjc/"]


@pytest.mark.asyncio
async def test_search_keeps_bulletin_from_query_variant(monkeypatch):
    from app.utils.web_search import FreeWebSearch

    searcher = FreeWebSearch()
    bulletin = _item(
        "中华人民共和国2025年国民经济和社会发展统计公报",
        "https://www.stats.gov.cn/sj/zxfb/bulletin.html",
        "全年城镇新增就业1267万人",
    )

    async def fake_bing(q, *_args, **_kwargs):
        if "统计公报" in q:
            return [bulletin]
        return []

    async def empty(*_args, **_kwargs):
        return []

    monkeypatch.setattr(searcher, "_search_baidu", fake_bing)
    monkeypatch.setattr(searcher, "_search_duckduckgo", empty)
    monkeypatch.setattr(searcher, "_search_wikipedia", empty)
    results = await searcher.search("2025中国就业数据", count=5)
    assert [item.url for item in results] == [bulletin.url]


def test_extract_query_terms_splits_employment_query():
    terms = extract_query_terms("今年的就业数据")
    assert "就业" in terms["cjk"]
    assert "数据" in terms["cjk"]
    assert "业数" not in terms["cjk"]


def test_expand_relative_time_resolves_this_and_recent_years():
    from datetime import datetime
    from app.utils.web_search import expand_relative_time

    now = datetime(2026, 9, 11, 12, 0, 0)
    assert expand_relative_time("今年的就业数据", now=now) == "2026年的就业数据"
    assert expand_relative_time("前几年的就业数据", now=now) == "2023年至2025年的就业数据"
    assert expand_relative_time("近三年的就业数据", now=now) == "2024年至2026年的就业数据"
    assert expand_relative_time("最近三年就业质量报告", now=now) == "2024年至2026年就业质量报告"


def test_extract_named_entity_keeps_school_name():
    from app.utils.web_search import extract_named_entity

    assert extract_named_entity("广州铁路职业技术学院的近三年就业数据") == "广州铁路职业技术学院"
    assert extract_named_entity("清华大学的招生简章") == "清华大学"
    assert extract_named_entity("华为的近三年营收") == "华为"
    assert extract_named_entity("广州铁路职业技术学院 就业质量报告 2024") == "广州铁路职业技术学院"
    assert extract_named_entity("华为 营收 2024") == "华为"
    assert extract_named_entity("中国 就业数据 2025") == ""
    assert extract_named_entity("Python 3.12 新特性") == ""


def test_search_query_variants_puts_school_name_first():
    from app.utils.web_search import search_query_variants

    variants = search_query_variants("广州铁路职业技术学院的近三年就业数据")
    assert variants[0] == "广州铁路职业技术学院"
    assert any("2024年至2026年" in item for item in variants)


def test_parse_official_aspect_links_keeps_employment_anchors():
    from app.utils.web_search import parse_official_aspect_links

    html = """
    <html><body>
      <a href="/zlb/gdzyjyzlbg/xxnb">高等职业教育质量报告（2025年度）</a>
      <a href="javascript:openexternallink('aHR0cCUzYSUyZiUyZnNmenkuZ3R4eS5jbiUyZnpqYyUyZg==')">招生就业</a>
      <a href="https://www.gz.gov.cn/">广州市人民政府</a>
    </body></html>
    """
    items = parse_official_aspect_links(
        html,
        "https://www.gtxy.edu.cn/",
        "广州铁路职业技术学院",
        ["就业", "毕业生", "就业率", "就业质量"],
        ["www.gtxy.edu.cn"],
    )
    urls = [item.url for item in items]
    assert "http://sfzy.gtxy.cn/zjc/" in urls
    assert all("gz.gov.cn" not in url for url in urls)
    assert all("广州铁路职业技术学院" in item.snippet for item in items)


def test_prefer_entity_aspect_results_drops_city_portals():
    from app.utils.web_search import prefer_entity_aspect_results

    query = "广州铁路职业技术学院的近三年就业数据"
    portal = _item("广州市人民政府门户网站", "https://www.gz.gov.cn/", "广州旅游")
    home = _item("广州铁路职业技术学院", "https://www.gtxy.edu.cn/", "学校党委开会")
    job = _item("招生就业", "http://sfzy.gtxy.cn/zjc/", "广州铁路职业技术学院 招生就业")
    kept = prefer_entity_aspect_results([portal, home, job], query, "广州铁路职业技术学院")
    assert [item.url for item in kept] == ["http://sfzy.gtxy.cn/zjc/"]


def test_employment_result_survives_relevance_filter():
    query = "2026年的就业数据"
    official = _item(
        "2026年城镇调查失业率与就业数据",
        "https://www.stats.gov.cn/employment",
        "国家统计局发布就业数据",
    )
    kept = filter_relevant_results([official], query)
    assert kept and kept[0].url.endswith("/employment")
