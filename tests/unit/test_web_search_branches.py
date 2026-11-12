import asyncio
import base64
from datetime import datetime
from urllib.parse import quote

import pytest

from app.utils import web_search as ws
from app.utils.web_search import FreeWebSearch, SearchResult


def _item(title, url, snippet="snippet", source=None, summary=None):
    return SearchResult(title=title, url=url, snippet=snippet, source=source, summary=summary)


class _FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None, encoding="utf-8", chunks=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data
        self.encoding = encoding
        self._chunks = chunks or []
        self.headers = headers or {}

    def json(self):
        return self._json

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    def __init__(self, response=None, responses=None, stream_response=None):
        self.response = response
        self.responses = list(responses or [])
        self.stream_response = stream_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, *args, **kwargs):
        if self.responses:
            return self.responses.pop(0)
        return self.response

    def stream(self, *args, **kwargs):
        response = self.stream_response

        class _Ctx:
            async def __aenter__(self_inner):
                return response

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()


def _client_factory(client):
    def factory(*_args, **_kwargs):
        return client

    return factory


def test_search_result_to_dict_and_context_include_summary():
    result = _item("t", "https://e.com", "snip", source="Bing", summary="sum")

    assert result.to_dict() == {
        "title": "t",
        "url": "https://e.com",
        "snippet": "snip",
        "source": "Bing",
        "summary": "sum",
    }
    context = result.to_context()
    assert "[SUMMARY] sum" in context
    assert "来源：Bing" in context


def test_split_cjk_run_skips_stopwords_and_handles_odd_length():
    # "的就业数据" -> parts ["就业数据"] -> pairs 就业/数据
    assert ws._split_cjk_run("的就业数据") == ["就业", "数据"]
    assert ws._split_cjk_run("就业") == ["就业"]
    assert ws._split_cjk_run("的") == []


def test_is_entity_name_rejects_short_year_and_generic():
    assert ws._is_entity_name("a") is False
    assert ws._is_entity_name("2025年") is False
    assert ws._is_entity_name("最新") is False
    assert ws._is_entity_name("北京大学") is True


def test_org_labels_variants():
    assert ws._org_labels("www.pku.edu.cn") == ["pku"]
    assert ws._org_labels("example.gov.cn") == ["example"]
    assert ws._org_labels("example.cn") == ["example"]
    assert ws._org_labels("sub.example.com") == ["sub", "example"]
    assert ws._org_labels("") == []


def test_same_org_host_empty_labels():
    assert ws.same_org_host("", "pku.edu.cn") is False
    assert ws.same_org_host("a.cn", "") is False
    assert ws.same_org_host("pku.edu.cn", "pku.edu.cn") is True


def test_decode_openexternallink_valid_and_invalid_base64():
    target = "https://example.edu.cn/job"
    encoded = base64.b64encode(target.encode()).decode()
    assert ws.decode_openexternallink(f"javascript:openexternallink('{encoded}')") == target
    assert ws.decode_openexternallink("javascript:void(0)") == ""


def test_decode_openexternallink_handles_decode_error(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("bad")

    monkeypatch.setattr(ws.base64, "b64decode", boom)
    assert ws.decode_openexternallink("openexternallink('abc')") == ""


def test_parse_official_aspect_links_empty_inputs():
    assert ws.parse_official_aspect_links("", "https://e.com", "x", ["y"], []) == []
    assert ws.parse_official_aspect_links("<html></html>", "https://e.com", "x", [], []) == []


def test_parse_official_aspect_links_skips_irrelevant_and_invalid_anchors():
    html = (
        '<a href="#top">就业</a>'
        '<a href="">就业</a>'
        '<a href="mailto:x@y.com">就业</a>'
        '<a href="/other">无关</a>'
        '<a href="javascript:void(0)">就业</a>'
    )
    results = ws.parse_official_aspect_links(
        html, "https://pku.edu.cn/", "北大", ["就业"], ["pku.edu.cn"]
    )

    assert results == []


def test_parse_official_aspect_links_stops_after_eight():
    anchors = "".join(
        f'<a href="https://pku.edu.cn/job{i}">就业岗位{i}</a>' for i in range(12)
    )
    results = ws.parse_official_aspect_links(
        anchors, "https://pku.edu.cn/", "北大", ["就业"], ["pku.edu.cn"]
    )

    assert len(results) == 8


def test_parse_official_aspect_links_rejects_foreign_host_and_duplicates():
    anchors = (
        '<a href="https://evil.example/x">就业信息</a>'
        '<a href="https://pku.edu.cn/job">就业岗位</a>'
        '<a href="https://pku.edu.cn/job">就业岗位</a>'
    )
    results = ws.parse_official_aspect_links(
        anchors, "https://pku.edu.cn/", "北大", ["就业"], ["pku.edu.cn"]
    )

    assert len(results) == 1
    assert results[0].url == "https://pku.edu.cn/job"


def test_prefer_entity_aspect_results_skips_empty_urls_and_missing_entity():
    results = [
        _item("北大", "", "就业"),
        _item("其他学校", "https://other.edu.cn", "就业"),
        _item("北京大学", "https://pku.edu.cn", "就业"),
    ]

    preferred = ws.prefer_entity_aspect_results(results, "北京大学的就业", "北京大学")

    assert [item.url for item in preferred] == ["https://pku.edu.cn"]


def test_relevance_score_empty_terms_returns_one():
    assert ws.relevance_score(_item("t", "https://e.com"), {}) == 1.0


def test_title_has_core_entity_without_core_tokens():
    assert ws.title_has_core_entity(_item("Anything", "https://e.com"), "hello") is True


@pytest.mark.asyncio
async def test_fetch_html_rejects_invalid_url():
    searcher = FreeWebSearch()

    assert await searcher._fetch_html("file:///etc/passwd") == ""


@pytest.mark.asyncio
async def test_fetch_html_returns_empty_on_bad_status(monkeypatch):
    searcher = FreeWebSearch()
    client = _FakeClient(response=_FakeResponse(status_code=500, text="err"))
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    assert await searcher._fetch_html("https://example.com") == ""


@pytest.mark.asyncio
async def test_fetch_html_returns_body(monkeypatch):
    searcher = FreeWebSearch()
    client = _FakeClient(response=_FakeResponse(status_code=200, text="<html>ok</html>"))
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    assert await searcher._fetch_html("https://example.com") == "<html>ok</html>"


@pytest.mark.asyncio
async def test_fetch_html_swallows_http_errors(monkeypatch):
    searcher = FreeWebSearch()

    class _Boom(_FakeClient):
        async def get(self, *_a, **_k):
            raise ws.httpx.HTTPError("boom")

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Boom()))

    assert await searcher._fetch_html("https://example.com") == ""


@pytest.mark.asyncio
async def test_discover_official_aspect_pages_without_aspect_or_hits():
    searcher = FreeWebSearch()

    assert await searcher._discover_official_aspect_pages([], "q", "entity") == []
    assert await searcher._discover_official_aspect_pages(
        [_item("e", "https://e.com")], "hello", "entity"
    ) == []


@pytest.mark.asyncio
async def test_discover_official_aspect_pages_skips_bad_and_aggregator_hosts(monkeypatch):
    searcher = FreeWebSearch()
    hits = [
        _item("a", "mailto:x@y.com"),
        _item("b", "https://baike.baidu.com/x"),
        _item("c", "https://pku.edu.cn"),
    ]
    fetched = []

    async def fake_fetch(url):
        fetched.append(url)
        return ""

    monkeypatch.setattr(searcher, "_fetch_html", fake_fetch)

    await searcher._discover_official_aspect_pages(hits, "北京大学的就业", "北京大学")

    assert fetched == ["https://pku.edu.cn/"]


@pytest.mark.asyncio
async def test_search_bing_non_200_returns_empty(monkeypatch):
    searcher = FreeWebSearch()
    client = _FakeClient(response=_FakeResponse(status_code=503))
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    assert await searcher._search_bing("q", 5, "en-US") == []


@pytest.mark.asyncio
async def test_search_bing_parses_results(monkeypatch):
    searcher = FreeWebSearch()
    html = (
        '<li class="b_algo"><h2>Title Long Enough</h2>'
        '<a href="https://example.com/a">link</a><p>snippet</p></li>'
    )
    client = _FakeClient(response=_FakeResponse(status_code=200, text=html))
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    results = await searcher._search_bing("q", 5)

    assert results[0].url == "https://example.com/a"


@pytest.mark.asyncio
async def test_search_bing_swallows_exceptions(monkeypatch):
    searcher = FreeWebSearch()

    class _Boom(_FakeClient):
        async def get(self, *_a, **_k):
            raise RuntimeError("boom")

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Boom()))

    assert await searcher._search_bing("q", 5) == []


def test_parse_bing_html_missing_title_and_link():
    searcher = FreeWebSearch()
    html = (
        '<li class="b_algo"><div>no title</div></li>'
        '<li class="b_algo"><h2>Valid Title Here</h2></li>'
        '<li class="b_algo"><h2>Rel Link Title</h2><a href="/rel">x</a></li>'
    )

    assert searcher._parse_bing_html(html, 5) == []


def test_parse_bing_html_uses_link_title_and_missing_snippet():
    searcher = FreeWebSearch()
    html = (
        '<li class="b_algo"><a href="https://example.com/a">Fallback Title</a></li>'
    )

    results = searcher._parse_bing_html(html, 5)

    assert results[0].title == "Fallback Title"
    assert results[0].snippet == "Fallback Title"


def test_parse_bing_html_skips_short_titles():
    searcher = FreeWebSearch()
    html = '<li class="b_algo"><h2>abc</h2><a href="https://e.com">x</a></li>'

    assert searcher._parse_bing_html(html, 5) == []


def test_parse_bing_html_handles_exception(monkeypatch):
    searcher = FreeWebSearch()

    class _SoupBoom:
        def __init__(self, *_a, **_k):
            raise ValueError("bad html")

    monkeypatch.setattr(ws, "BeautifulSoup", _SoupBoom)

    assert searcher._parse_bing_html("<html>", 5) == []


@pytest.mark.asyncio
async def test_search_duckduckgo_non_200(monkeypatch):
    searcher = FreeWebSearch()
    client = _FakeClient(response=_FakeResponse(status_code=500))
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    assert await searcher._search_duckduckgo("q", 5) == []


@pytest.mark.asyncio
async def test_search_duckduckgo_swallows_exceptions(monkeypatch):
    searcher = FreeWebSearch()

    class _Boom(_FakeClient):
        async def get(self, *_a, **_k):
            raise RuntimeError("boom")

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Boom()))

    assert await searcher._search_duckduckgo("q", 5) == []


@pytest.mark.asyncio
async def test_search_duckduckgo_parses_successful_response(monkeypatch):
    searcher = FreeWebSearch()
    html = (
        '<div class="result"><a class="result__url" href="https://example.com/page">'
        "A Long Enough Title</a></div>"
    )
    client = _FakeClient(response=_FakeResponse(status_code=200, text=html))
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    results = await searcher._search_duckduckgo("q", 5)

    assert results[0].url == "https://example.com/page"


def test_parse_duckduckgo_html_skips_invalid_entries():
    searcher = FreeWebSearch()
    html = (
        '<div class="result"><span>no link</span></div>'
        '<div class="result"><a class="result__url" href="/rel">Short</a></div>'
        '<div class="result"><a class="result__url" href="https://e.com/ad">Advertisement long title</a></div>'
        '<div class="result"><a class="result__url" href="javascript:void(0)">Another long title</a></div>'
    )

    assert searcher._parse_duckduckgo_html(html, 5) == []


def test_parse_duckduckgo_html_skips_relative_url_with_long_title():
    searcher = FreeWebSearch()
    html = (
        '<div class="result"><a class="result__url" href="/relative">'
        "A Long Enough Title</a></div>"
    )

    assert searcher._parse_duckduckgo_html(html, 5) == []


def test_parse_duckduckgo_html_parses_valid_result():
    searcher = FreeWebSearch()
    html = (
        '<div class="result"><a class="result__url" href="https://example.com/page">'
        "A Long Enough Title</a><div class=\"result__snippet\">snippet</div></div>"
    )

    results = searcher._parse_duckduckgo_html(html, 5)

    assert results[0].url == "https://example.com/page"
    assert results[0].snippet == "snippet"


def test_parse_duckduckgo_html_handles_exception(monkeypatch):
    searcher = FreeWebSearch()

    class _SoupBoom:
        def __init__(self, *_a, **_k):
            raise ValueError("bad")

    monkeypatch.setattr(ws, "BeautifulSoup", _SoupBoom)

    assert searcher._parse_duckduckgo_html("<html>", 5) == []


@pytest.mark.asyncio
async def test_search_wikipedia_uses_chinese_first_and_breaks(monkeypatch):
    searcher = FreeWebSearch()
    payload = {"query": {"search": [{"title": "故宫", "snippet": "x"}]}}
    client = _FakeClient(responses=[_FakeResponse(json_data=payload)])
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    results = await searcher._search_wikipedia("故宫", 1)

    assert results[0].source == "Wikipedia"


@pytest.mark.asyncio
async def test_search_wikipedia_skips_non_200(monkeypatch):
    searcher = FreeWebSearch()
    client = _FakeClient(
        responses=[
            _FakeResponse(status_code=500),
            _FakeResponse(status_code=500),
        ]
    )
    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(client))

    assert await searcher._search_wikipedia("q", 5) == []


@pytest.mark.asyncio
async def test_search_wikipedia_swallows_exceptions(monkeypatch):
    searcher = FreeWebSearch()

    class _Boom(_FakeClient):
        async def get(self, *_a, **_k):
            raise RuntimeError("boom")

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Boom()))

    assert await searcher._search_wikipedia("q", 5) == []


def test_clean_text_unescapes_and_collapses_whitespace():
    searcher = FreeWebSearch()

    assert searcher._clean_text("  a &amp;   b  ") == "a & b"


def test_clean_url_extracts_link_and_u_params():
    searcher = FreeWebSearch()

    assert searcher._clean_url(
        "https://duckduckgo.com/l/?link=https%3A%2F%2Fa.com"
    ) == "https://a.com"
    assert searcher._clean_url(
        "https://duckduckgo.com/l/?u=https%3A%2F%2Fb.com"
    ) == "https://b.com"


def test_fallback_results_returns_system_hint():
    searcher = FreeWebSearch()

    results = searcher._fallback_results("q")

    assert results[0].source == "System"


def test_format_results_for_llm_empty_and_populated():
    searcher = FreeWebSearch()

    assert searcher.format_results_for_llm([]) == "未找到相关搜索结果"
    formatted = searcher.format_results_for_llm([_item("t", "https://e.com")], max_results=1)
    assert "网络搜索结果" in formatted
    assert "1. [t](https://e.com)" in formatted


def test_read_limited_stops_exactly_at_limit():
    async def run():
        response = _FakeResponse(chunks=[b"abcdef", b"ghij"])
        return await ws._read_limited(response, 3)

    assert asyncio.run(run()) == b"abc"


def test_split_cjk_run_skips_parts_in_stop_set(monkeypatch):
    monkeypatch.setattr(ws, "_CJK_STOP", {"就业"})

    assert ws._split_cjk_run("就业") == []


def test_extract_named_entity_no_separator_returns_empty():
    assert ws.extract_named_entity("how to learn python") == ""


def test_search_query_variants_skips_short_topical_after_year():
    variants = ws.search_query_variants("2025年 a")

    assert "a" not in variants


def test_relevance_score_generic_token_fallback_and_phrase():
    terms = {
        "versions": [],
        "english": [],
        "cjk": ["时间"],
        "phrase": "",
        "require_phrase": False,
    }
    result = _item("时间", "https://e.com")

    # generic token becomes scored token; time token present -> score 1.0
    assert ws.relevance_score(result, terms) == 1.0


def test_unique_filters_empty_values():
    assert ws._unique(["", "a", "a", "b"]) == ["a", "b"]


@pytest.mark.asyncio
async def test_search_merges_duckduckgo_results(monkeypatch):
    searcher = FreeWebSearch()
    ddg_hit = _item("Python 3.12 新特性", "https://example.com/feature", "新特性")

    async def q_bing(*_a, **_k):
        return []

    async def q_ddg(*_a, **_k):
        return [ddg_hit]

    async def q_wiki(*_a, **_k):
        return []

    monkeypatch.setattr(searcher, "_search_bing", q_bing)
    monkeypatch.setattr(searcher, "_search_duckduckgo", q_ddg)
    monkeypatch.setattr(searcher, "_search_wikipedia", q_wiki)

    results = await searcher.search("Python 3.12 新特性", count=3)

    assert results[0].url == ddg_hit.url


@pytest.mark.asyncio
async def test_search_returns_fallback_when_all_sources_empty(monkeypatch):
    searcher = FreeWebSearch()

    async def empty(*_a, **_k):
        return []

    monkeypatch.setattr(searcher, "_search_bing", empty)
    monkeypatch.setattr(searcher, "_search_duckduckgo", empty)
    monkeypatch.setattr(searcher, "_search_wikipedia", empty)

    results = await searcher.search("普通查询", count=3)

    assert results[0].source == "System"


@pytest.mark.asyncio
async def test_search_catches_unexpected_exception(monkeypatch):
    searcher = FreeWebSearch()

    def boom(_query):
        raise ValueError("bad query")

    monkeypatch.setattr(ws, "search_query_variants", boom)

    results = await searcher.search("q", count=3)

    assert results[0].source == "System"


@pytest.mark.asyncio
async def test_search_uses_wiki_and_official_refs_when_merged_empty(monkeypatch):
    searcher = FreeWebSearch()
    wiki_hit = _item("Python", "https://en.wikipedia.org/wiki/Python", "Python language")

    async def empty(*_a, **_k):
        return []

    async def wiki(*_a, **_k):
        return [wiki_hit]

    monkeypatch.setattr(searcher, "_search_bing", empty)
    monkeypatch.setattr(searcher, "_search_duckduckgo", empty)
    monkeypatch.setattr(searcher, "_search_wikipedia", wiki)

    results = await searcher.search("Python", count=3)

    assert results[0].url == wiki_hit.url


@pytest.mark.asyncio
async def test_discover_official_aspect_pages_deduplicates_org(monkeypatch):
    searcher = FreeWebSearch()
    hits = [
        _item("e", "https://pku.edu.cn/a"),
        _item("e2", "https://www.pku.edu.cn/b"),
    ]
    fetched = []

    async def fake_fetch(url):
        fetched.append(url)
        return ""

    monkeypatch.setattr(searcher, "_fetch_html", fake_fetch)

    await searcher._discover_official_aspect_pages(hits, "北京大学的就业", "北京大学")

    assert fetched == ["https://pku.edu.cn/"]


@pytest.mark.asyncio
async def test_discover_official_aspect_pages_limits_two_entries(monkeypatch):
    searcher = FreeWebSearch()
    hits = [
        _item("e", "https://a.edu.cn/x"),
        _item("e", "https://b.edu.cn/x"),
        _item("e", "https://c.edu.cn/x"),
    ]
    fetched = []

    async def fake_fetch(url):
        fetched.append(url)
        return ""

    monkeypatch.setattr(searcher, "_fetch_html", fake_fetch)

    await searcher._discover_official_aspect_pages(hits, "大学的就业", "大学")

    assert len(fetched) == 2


def test_parse_bing_html_stops_at_count():
    searcher = FreeWebSearch()
    html = "".join(
        f'<li class="b_algo"><h2>Title Number {i}</h2>'
        f'<a href="https://e.com/{i}">x</a></li>'
        for i in range(5)
    )

    assert len(searcher._parse_bing_html(html, 2)) == 2


def test_parse_duckduckgo_html_stops_at_count():
    searcher = FreeWebSearch()
    html = "".join(
        f'<div class="result"><a class="result__url" href="https://e.com/{i}">'
        f"A Long Enough Title {i}</a></div>"
        for i in range(5)
    )

    assert len(searcher._parse_duckduckgo_html(html, 2)) == 2


@pytest.mark.asyncio
async def test_search_with_summaries_delegates(monkeypatch):
    searcher = FreeWebSearch()
    captured = {}

    async def fake_summaries(**kwargs):
        captured.update(kwargs)
        return [_item("t", "https://e.com", summary="s")]

    monkeypatch.setattr(ws, "search_with_page_summaries", fake_summaries)

    results = await searcher.search_with_summaries("q", count=2, max_summary_length=50)

    assert captured["count"] == 2
    assert results[0].summary == "s"


@pytest.mark.asyncio
async def test_search_and_format_with_summaries_formats(monkeypatch):
    searcher = FreeWebSearch()

    async def fake_summaries(**_kwargs):
        return [_item("t", "https://e.com")]

    monkeypatch.setattr(searcher, "search_with_summaries", fake_summaries)

    text = await searcher.search_and_format_with_summaries("q", count=1)

    assert "网络搜索结果" in text


@pytest.mark.asyncio
async def test_search_and_format_uses_search(monkeypatch):
    searcher = FreeWebSearch()

    async def fake_search(*_args, **_kwargs):
        return [_item("t", "https://e.com")]

    monkeypatch.setattr(searcher, "search", fake_search)

    text = await searcher.search_and_format("q", count=1, lang="en-US")

    assert "[t](https://e.com)" in text


@pytest.mark.asyncio
async def test_search_with_sources_filters_empty_urls(monkeypatch):
    searcher = FreeWebSearch()

    async def fake_search(*_args, **_kwargs):
        return [_item("t", "https://e.com"), _item("u", "")]

    monkeypatch.setattr(searcher, "search", fake_search)

    context, sources = await searcher.search_with_sources("q", count=2)

    assert len(sources) == 1
    assert sources[0]["url"] == "https://e.com"
    assert "网络搜索结果" in context


@pytest.mark.asyncio
async def test_web_search_wrapper_delegates(monkeypatch):
    async def fake_search_and_format(self, query, count=5, lang="zh-CN"):
        return f"{query}:{count}"

    monkeypatch.setattr(FreeWebSearch, "search_and_format", fake_search_and_format)

    assert await ws.web_search("q", count=2) == "q:2"


@pytest.mark.asyncio
async def test_search_news_appends_keyword(monkeypatch):
    captured = {}

    async def fake_search_and_format(self, query, count=5, lang="zh-CN"):
        captured["query"] = query
        return "ok"

    monkeypatch.setattr(FreeWebSearch, "search_and_format", fake_search_and_format)

    assert await ws.search_news("AI", count=2) == "ok"
    assert captured["query"] == "AI 最新新闻"


@pytest.mark.asyncio
async def test_fetch_page_text_rejects_redirect_without_location(monkeypatch):
    monkeypatch.setattr(ws, "check_outbound_url", lambda *_a, **_k: None)
    stream_response = _FakeResponse(status_code=302, headers={})

    class _Client(_FakeClient):
        def stream(self, *_a, **_k):
            response = stream_response

            class _Ctx:
                async def __aenter__(self_inner):
                    return response

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Ctx()

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Client()))

    assert await ws.fetch_page_text("https://example.com") is None


@pytest.mark.asyncio
async def test_fetch_page_text_redirect_limit(monkeypatch):
    monkeypatch.setattr(ws, "check_outbound_url", lambda *_a, **_k: None)

    class _Client(_FakeClient):
        def stream(self, *_a, **_k):
            response = _FakeResponse(
                status_code=302, headers={"location": "https://example.com/next"}
            )

            class _Ctx:
                async def __aenter__(self_inner):
                    return response

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Ctx()

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Client()))

    assert await ws.fetch_page_text("https://example.com") is None


@pytest.mark.asyncio
async def test_fetch_page_text_non_200(monkeypatch):
    monkeypatch.setattr(ws, "check_outbound_url", lambda *_a, **_k: None)

    class _Client(_FakeClient):
        def stream(self, *_a, **_k):
            response = _FakeResponse(status_code=404, headers={})

            class _Ctx:
                async def __aenter__(self_inner):
                    return response

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Ctx()

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Client()))

    assert await ws.fetch_page_text("https://example.com") is None


@pytest.mark.asyncio
async def test_fetch_page_text_extracts_clean_text(monkeypatch):
    monkeypatch.setattr(ws, "check_outbound_url", lambda *_a, **_k: None)
    body = _FakeResponse(
        status_code=200,
        encoding="utf-8",
        chunks=[b"<html><style>x</style><script>y</script><body>Hello   world</body></html>"],
    )

    class _Client(_FakeClient):
        def stream(self, *_a, **_k):
            response = body

            class _Ctx:
                async def __aenter__(self_inner):
                    return response

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Ctx()

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Client()))

    text = await ws.fetch_page_text("https://example.com")

    assert text == "Hello world"


@pytest.mark.asyncio
async def test_fetch_page_text_follows_redirect(monkeypatch):
    monkeypatch.setattr(ws, "check_outbound_url", lambda *_a, **_k: None)
    responses = [
        _FakeResponse(status_code=302, headers={"location": "https://example.com/final"}),
        _FakeResponse(status_code=200, encoding="utf-8", chunks=[b"<html>done</html>"]),
    ]

    class _Client(_FakeClient):
        def stream(self, *_a, **_k):
            response = responses.pop(0)

            class _Ctx:
                async def __aenter__(self_inner):
                    return response

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Ctx()

    monkeypatch.setattr(ws.httpx, "AsyncClient", _client_factory(_Client()))

    assert await ws.fetch_page_text("https://example.com") == "done"


@pytest.mark.asyncio
async def test_summarize_truncates_and_returns_none_for_bad_payload(monkeypatch):
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"no_choices": True}

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

    assert await ws.summarize_page_with_llm("x" * 6000, "https://e.com") is None
    assert len(captured["prompt"]) < 6000 + 1000


@pytest.mark.asyncio
async def test_summarize_swallows_exceptions(monkeypatch):
    async def boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.utils.call_llm", boom)

    assert await ws.summarize_page_with_llm("text", "https://e.com") is None


@pytest.mark.asyncio
async def test_search_with_page_summaries_empty_results(monkeypatch):
    async def fake_search(self, query, count=5):
        return []

    monkeypatch.setattr(FreeWebSearch, "search", fake_search)

    assert await ws.search_with_page_summaries("q", count=3) == []


@pytest.mark.asyncio
async def test_search_with_page_summaries_marks_summary(monkeypatch):
    results = [_item("t", "https://e.com/1")]

    async def fake_search(self, query, count=5):
        return results

    async def fake_fetch(url, timeout=10.0):
        return "page text"

    async def fake_summary(page_text, url, max_length=200):
        return "short summary"

    monkeypatch.setattr(FreeWebSearch, "search", fake_search)
    monkeypatch.setattr(ws, "fetch_page_text", fake_fetch)
    monkeypatch.setattr(ws, "summarize_page_with_llm", fake_summary)

    final = await ws.search_with_page_summaries("q", count=1)

    assert final[0].summary == "short summary"


@pytest.mark.asyncio
async def test_search_with_page_summaries_handles_unfetchable_pages(monkeypatch):
    results = [_item("t", "https://e.com/1")]

    async def fake_search(self, query, count=5):
        return results

    async def fake_fetch(url, timeout=10.0):
        return None

    async def fake_summary(*_a, **_k):
        raise AssertionError("should not summarize empty page")

    monkeypatch.setattr(FreeWebSearch, "search", fake_search)
    monkeypatch.setattr(ws, "fetch_page_text", fake_fetch)
    monkeypatch.setattr(ws, "summarize_page_with_llm", fake_summary)

    final = await ws.search_with_page_summaries("q", count=1)

    assert final[0].summary is None


@pytest.mark.asyncio
async def test_search_with_page_summaries_skips_empty_summary(monkeypatch):
    results = [_item("t", "https://e.com/1")]

    async def fake_search(self, query, count=5):
        return results

    async def fake_fetch(url, timeout=10.0):
        return "page text"

    async def fake_summary(*_a, **_k):
        return None

    monkeypatch.setattr(FreeWebSearch, "search", fake_search)
    monkeypatch.setattr(ws, "fetch_page_text", fake_fetch)
    monkeypatch.setattr(ws, "summarize_page_with_llm", fake_summary)

    final = await ws.search_with_page_summaries("q", count=1)

    assert final[0].summary is None


@pytest.mark.asyncio
async def test_fetch_page_text_swallows_unexpected_exceptions(monkeypatch):
    monkeypatch.setattr(ws, "check_outbound_url", lambda *_a, **_k: None)

    def boom(*_a, **_k):
        raise RuntimeError("client init failed")

    monkeypatch.setattr(ws.httpx, "AsyncClient", boom)

    assert await ws.fetch_page_text("https://example.com") is None


@pytest.mark.asyncio
async def test_search_with_page_summaries_handles_task_exception(monkeypatch):
    results = [_item("t", "https://e.com/1"), _item("u", "https://e.com/2")]

    async def fake_search(self, query, count=5):
        return results

    async def fake_fetch(url, timeout=10.0):
        if url.endswith("1"):
            raise RuntimeError("fetch failed")
        return None

    monkeypatch.setattr(FreeWebSearch, "search", fake_search)
    monkeypatch.setattr(ws, "fetch_page_text", fake_fetch)

    final = await ws.search_with_page_summaries("q", count=2)

    assert final[0].url == "https://e.com/1"


@pytest.mark.asyncio
async def test_web_search_with_summaries_empty_and_populated(monkeypatch):
    async def empty(*_args, **_kwargs):
        return []

    monkeypatch.setattr(ws, "search_with_page_summaries", empty)
    assert await ws.web_search_with_summaries("q") == "未找到相关搜索结果"

    async def filled(*_args, **_kwargs):
        return [_item("t", "https://e.com")]

    monkeypatch.setattr(ws, "search_with_page_summaries", filled)
    text = await ws.web_search_with_summaries("q")
    assert "网络搜索结果" in text
