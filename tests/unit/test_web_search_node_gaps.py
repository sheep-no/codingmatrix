"""补齐 WebSearchNode 的参数校验、详情抓取与异常降级。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.workflow.node_types import web_search as module
from app.utils.workflow.node_types.web_search import WebSearchNode


def _result(index=1, url="https://example.com"):
    return SimpleNamespace(
        title=f"t{index}", url=url, snippet=f"s{index}", source="bing"
    )


class TestValidateParams:
    def test_all_valid_optional_params_short_circuit(self):
        node = WebSearchNode(
            "n",
            {
                "query": "q",
                "count": 5,
                "lang": "zh-CN",
                "with_summary": False,
                "fetch_details": True,
                "detail_count": 3,
            },
        )

        assert node.validate_params() == []

    @pytest.mark.parametrize(
        ("params", "keyword"),
        [
            ({"query": 1}, "must be a string"),
            ({"query": "   "}, "cannot be empty"),
            ({"query": "q", "count": "5"}, "count"),
            ({"query": "q", "count": 0}, "between 1 and 20"),
            ({"query": "q", "count": 21}, "between 1 and 20"),
            ({"query": "q", "lang": 1}, "lang"),
            ({"query": "q", "with_summary": 1}, "with_summary"),
            ({"query": "q", "fetch_details": 1}, "fetch_details"),
            ({"query": "q", "detail_count": "3"}, "detail_count"),
            ({"query": "q", "detail_count": 0}, "between 1 and 10"),
            ({"query": "q", "detail_count": 11}, "between 1 and 10"),
        ],
    )
    def test_invalid(self, params, keyword):
        assert any(keyword in e for e in WebSearchNode("n", params).validate_params())


class TestExecute:
    @pytest.mark.asyncio
    async def test_fetch_details_enabled_attaches_details(self, monkeypatch):
        node = WebSearchNode("n", {"query": "q"})
        node.searcher.search = AsyncMock(return_value=[_result()])
        fetch = AsyncMock(return_value=[{"url": "https://example.com", "page_fetched": True}])
        monkeypatch.setattr(node, "_fetch_details", fetch)

        result = await node.execute({})

        fetch.assert_awaited_once()
        assert result.data["details"][0]["page_fetched"] is True
        assert result.metadata["has_details"] is True

    @pytest.mark.asyncio
    async def test_formats_results_and_top_result(self):
        node = WebSearchNode("n", {"query": "q", "count": 2, "fetch_details": False})
        node.searcher.search = AsyncMock(return_value=[_result(1), _result(2)])

        result = await node.execute({})

        assert result.success is True
        assert result.data["count"] == 2
        assert result.data["results"][0] == {
            "index": 1,
            "title": "t1",
            "url": "https://example.com",
            "snippet": "s1",
            "source": "bing",
        }
        assert result.data["top_result"]["index"] == 1
        assert result.metadata["has_details"] is False

    @pytest.mark.asyncio
    async def test_fetch_details_disabled(self):
        node = WebSearchNode("n", {"query": "q", "fetch_details": False})
        node.searcher.search = AsyncMock(return_value=[_result()])

        result = await node.execute({})

        assert "details" not in result.data
        assert result.metadata["has_details"] is False

    @pytest.mark.asyncio
    async def test_search_error_returns_error_result(self):
        node = WebSearchNode("n", {"query": "q"})
        node.searcher.search = AsyncMock(side_effect=RuntimeError("network"))

        result = await node.execute({})

        assert result.success is False
        assert "network" in result.error
        assert result.metadata["node_type"] == "web_search"


class TestFetchDetails:
    @pytest.mark.asyncio
    async def test_skips_result_without_url(self):
        node = WebSearchNode("n", {"query": "q"})
        results = [{"url": ""}]

        assert await node._fetch_details(results, 3) == [{"url": ""}]

    @pytest.mark.asyncio
    async def test_adds_summary_and_preview(self, monkeypatch):
        node = WebSearchNode("n", {"query": "q"})
        monkeypatch.setattr(
            module, "fetch_page_text", AsyncMock(return_value="x" * 600)
        )
        monkeypatch.setattr(
            module, "summarize_page_with_llm", AsyncMock(return_value="summary")
        )

        detailed = await node._fetch_details([{"url": "https://a"}], 3)

        assert detailed[0]["page_summary"] == "summary"
        assert detailed[0]["page_text_preview"].endswith("...")
        assert detailed[0]["page_fetched"] is True

    @pytest.mark.asyncio
    async def test_short_page_text_has_no_ellipsis(self, monkeypatch):
        node = WebSearchNode("n", {"query": "q"})
        monkeypatch.setattr(module, "fetch_page_text", AsyncMock(return_value="short"))
        monkeypatch.setattr(
            module, "summarize_page_with_llm", AsyncMock(return_value="")
        )

        detailed = await node._fetch_details([{"url": "https://a"}], 3)

        assert "page_summary" not in detailed[0]
        assert detailed[0]["page_text_preview"] == "short"

    @pytest.mark.asyncio
    async def test_empty_page_text_marks_not_fetched(self, monkeypatch):
        node = WebSearchNode("n", {"query": "q"})
        monkeypatch.setattr(module, "fetch_page_text", AsyncMock(return_value=""))

        detailed = await node._fetch_details([{"url": "https://a"}], 3)

        assert detailed[0]["page_fetched"] is False

    @pytest.mark.asyncio
    async def test_fetch_exception_marks_not_fetched(self, monkeypatch):
        node = WebSearchNode("n", {"query": "q"})
        monkeypatch.setattr(
            module, "fetch_page_text", AsyncMock(side_effect=RuntimeError("timeout"))
        )

        detailed = await node._fetch_details([{"url": "https://a"}], 3)

        assert detailed[0]["page_fetched"] is False

    @pytest.mark.asyncio
    async def test_gather_exception_falls_back_to_original(self, monkeypatch):
        node = WebSearchNode("n", {"query": "q"})

        async def fake_gather(*tasks, **kwargs):
            for task in tasks:
                task.close()
            return [RuntimeError("x")]

        monkeypatch.setattr(module.asyncio, "gather", fake_gather)

        detailed = await node._fetch_details([{"url": "https://a"}], 3)

        assert detailed == [{"url": "https://a"}]
