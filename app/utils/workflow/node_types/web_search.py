"""
Web Search Node - 网络搜索节点

使用现有的 FreeWebSearch 实现网络搜索功能
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional

from app.schema.workflow import TaskType
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult
from app.utils.web_search import FreeWebSearch, fetch_page_text, summarize_page_with_llm

logger = logging.getLogger(__name__)


class WebSearchNode(TaskNodeBase):
    """
    网络搜索节点

    支持 Bing/DuckDuckGo 搜索，并可抓取页面详情

    参数:
        query: 搜索关键词
        count: 结果数量（默认 5）
        lang: 语言（默认 zh-CN）
        with_summary: 是否生成摘要（默认 False）
        fetch_details: 是否抓取页面详情（默认 True）
        detail_count: 抓取详情页面的数量（默认 3）
    """

    task_type = TaskType.WEB_SEARCH

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)
        self.searcher = FreeWebSearch()

    def get_required_params(self) -> List[str]:
        return ["query"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "count": 5,
            "lang": "zh-CN",
            "with_summary": False,
            "fetch_details": True,
            "detail_count": 3,
        }

    def validate_params(self) -> List[str]:
        errors = []

        if "query" not in self.params:
            errors.append("Missing required parameter: query")
        elif not isinstance(self.params["query"], str):
            errors.append("Parameter 'query' must be a string")
        elif len(self.params["query"].strip()) == 0:
            errors.append("Parameter 'query' cannot be empty")

        if "count" in self.params:
            if not isinstance(self.params["count"], int):
                errors.append("Parameter 'count' must be an integer")
            elif self.params["count"] < 1 or self.params["count"] > 20:
                errors.append("Parameter 'count' must be between 1 and 20")

        if "lang" in self.params:
            if not isinstance(self.params["lang"], str):
                errors.append("Parameter 'lang' must be a string")

        if "with_summary" in self.params:
            if not isinstance(self.params["with_summary"], bool):
                errors.append("Parameter 'with_summary' must be a boolean")

        if "fetch_details" in self.params:
            if not isinstance(self.params["fetch_details"], bool):
                errors.append("Parameter 'fetch_details' must be a boolean")

        if "detail_count" in self.params:
            if not isinstance(self.params["detail_count"], int):
                errors.append("Parameter 'detail_count' must be an integer")
            elif self.params["detail_count"] < 1 or self.params["detail_count"] > 10:
                errors.append("Parameter 'detail_count' must be between 1 and 10")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行网络搜索

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 搜索结果
        """
        try:
            query = self.params["query"]
            count = self.params.get("count", 5)
            lang = self.params.get("lang", "zh-CN")
            fetch_details = self.params.get("fetch_details", True)
            detail_count = self.params.get("detail_count", 3)

            logger.info(f"[{self.node_id}] 执行搜索: query={query}, count={count}, fetch_details={fetch_details}")

            results = await self.searcher.search(query, count=count, lang=lang)

            formatted_results = []
            for i, r in enumerate(results, 1):
                formatted_results.append({
                    "index": i,
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source": r.source,
                })

            result_data = {
                "query": query,
                "count": len(formatted_results),
                "results": formatted_results,
            }

            if formatted_results:
                result_data["top_result"] = formatted_results[0]

            if fetch_details and formatted_results:
                logger.info(f"[{self.node_id}] 抓取页面详情: count={min(detail_count, len(formatted_results))}")
                details = await self._fetch_details(formatted_results, detail_count)
                result_data["details"] = details

            logger.info(f"[{self.node_id}] 搜索完成: {len(formatted_results)} 条结果")

            return NodeResult.success_result(
                data=result_data,
                metadata={
                    "node_type": self.task_type.value,
                    "query": query,
                    "result_count": len(formatted_results),
                    "has_details": "details" in result_data,
                }
            )

        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(
                error=error_msg,
                metadata={"node_type": self.task_type.value}
            )

    async def _fetch_details(self, results: List[Dict], detail_count: int) -> List[Dict]:
        """并发抓取页面详情"""

        async def fetch_one(result: Dict) -> Dict:
            url = result.get("url", "")
            if not url:
                return result

            try:
                page_text = await fetch_page_text(url, timeout=10.0)
                if page_text:
                    summary = await summarize_page_with_llm(page_text, url, max_length=300)
                    if summary:
                        result["page_summary"] = summary
                    result["page_text_preview"] = page_text[:500] + "..." if len(page_text) > 500 else page_text
                    result["page_fetched"] = True
                else:
                    result["page_fetched"] = False
            except Exception as e:
                logger.warning(f"抓取页面失败: {url} | error={str(e)}")
                result["page_fetched"] = False

            return result

        tasks = [fetch_one(r) for r in results[:detail_count]]
        detailed = await asyncio.gather(*tasks, return_exceptions=True)

        detailed_results = []
        for i, r in enumerate(detailed):
            if isinstance(r, Exception):
                logger.warning(f"处理结果异常: index={i} | error={str(r)}")
                detailed_results.append(results[i])
            else:
                detailed_results.append(r)

        return detailed_results
