"""
完全免费的 Web 搜索工具 - 无需 API Key

实现方案：
1. 使用 httpx 直接调用公开搜索 API
2. 支持多个搜索引擎（Google PSE, DuckDuckGo HTML）
3. 可选页面摘要（方案 A：LLM 总结，而非自己解析 HTML）

用法:
    from app.utils.web_search import FreeWebSearch

    search = FreeWebSearch()
    results = await search.search("Python 3.12 新特性", count=5)

    # 方案 A：搜索并生成页面摘要
    results = await search.search_with_summaries("FastAPI 教程", count=3)
"""
import logging
import asyncio
import os
from typing import List, Dict, Optional
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

# SSL 验证配置（生产环境应设为 True）
DISABLE_SSL_VERIFY = os.getenv("WEB_SEARCH_DISABLE_SSL_VERIFY", "false").lower() == "true"


class SearchResult:
    """搜索结果项"""

    def __init__(
        self,
        title: str,
        url: str,
        snippet: str,
        source: Optional[str] = None,
        summary: Optional[str] = None
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source = source
        self.summary = summary  # 页面摘要（LLM 生成）

    def to_dict(self) -> Dict:
        result = {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source
        }
        if self.summary:
            result["summary"] = self.summary
        return result

    def to_context(self) -> str:
        """转换为 LLM 上下文格式"""
        context = f"[{self.title}]({self.url})"
        if self.source:
            context += f" | 来源：{self.source}"
        context += f"\n{self.snippet}\n"
        if self.summary:
            context += f"\n[SUMMARY] {self.summary}\n"
        return context


class FreeWebSearch:
    """免费 Web 搜索引擎（无需 API Key）"""

    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.timeout = httpx.Timeout(15.0, connect=5.0)

        # 摘要生成配置
        self.summary_max_length = 200  # 摘要最大长度
        self.summary_timeout = 30.0  # LLM 总结超时
        self.max_concurrent_fetch = 3  # 最大并发抓取数
        self.max_text_length = 5000  # 最多发送给 LLM 的文本长度
    
    async def search(
        self,
        query: str,
        count: int = 5,
        lang: str = "zh-CN"
    ) -> List[SearchResult]:
        """
        Bing 搜索（主要）+ DuckDuckGo（备用）

        Args:
            query: 搜索关键词
            count: 结果数量
            lang: 语言

        Returns:
            搜索结果列表
        """
        try:
            logger.info(f"开始搜索 | query={query[:50]}... | count={count}")

            # 优先使用 Bing 搜索
            results = await self._search_baidu(query, count)
            if results:
                logger.info(f"Bing 搜索成功 | 结果数={len(results)}")
                return results

            # 备用 DuckDuckGo
            logger.warning("Bing 搜索失败，尝试 DuckDuckGo")
            results = await self._search_duckduckgo(query, count)
            if results:
                logger.info(f"DuckDuckGo 搜索成功 | 结果数={len(results)}")
                return results

            logger.warning("所有搜索服务都失败，使用降级结果")
            return self._fallback_results(query)

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"搜索失败 | query={query} | error={str(e)}")
            return self._fallback_results(query)

    async def _search_baidu(self, query: str, count: int) -> List[SearchResult]:
        """Bing 搜索（替代方案）"""
        try:
            url = "https://www.bing.com/search"
            params = {
                "q": query,
                "count": min(count, 10)
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            ) as client:
                resp = await client.get(url, params=params, headers=headers)

                if resp.status_code != 200:
                    logger.warning(f"Bing 返回错误状态 | status={resp.status_code}")
                    return []

                return self._parse_bing_html(resp.text, count)

        except Exception as e:
            logger.error(f"Bing 搜索异常 | error={str(e)}")
            return []

    def _parse_bing_html(self, html: str, count: int) -> List[SearchResult]:
        """解析 Bing 搜索结果 HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            results = []

            # Bing 结果在 li.b_algo 中
            result_blocks = soup.select('li.b_algo')[:count * 2]

            for block in result_blocks:
                # 查找标题和链接
                title_el = block.find('h2')
                link_el = block.find('a')

                if title_el:
                    title = title_el.get_text(strip=True)
                elif link_el:
                    title = link_el.get_text(strip=True)
                else:
                    continue

                if link_el:
                    url = link_el.get('href', '')
                    if not url or url.startswith('/') or not url.startswith('http'):
                        continue
                else:
                    continue

                # 查找摘要
                snippet_el = block.find('p') or block.find(class_=['b_desc', 'b_paractl'])
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)[:300]
                else:
                    snippet = title

                # 跳过无效结果
                if not title or len(title) < 5:
                    continue

                results.append(SearchResult(
                    title=self._clean_text(title),
                    url=url,
                    snippet=self._clean_text(snippet) if snippet else title,
                    source="Bing"
                ))

                if len(results) >= count:
                    break

            return results

        except Exception as e:
            logger.error(f"Bing HTML 解析失败 | error={str(e)}")
            return []

    async def _search_duckduckgo(self, query: str, count: int) -> List[SearchResult]:
        """DuckDuckGo 搜索（备用）"""
        try:
            url = "https://html.duckduckgo.com/html/"
            params = {"q": query}

            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            }

            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=False
            ) as client:
                resp = await client.get(url, params=params, headers=headers)

                if resp.status_code != 200:
                    return []

                return self._parse_duckduckgo_html(resp.text, count)

        except Exception as e:
            logger.error(f"DuckDuckGo 搜索异常 | error={str(e)}")
            return []
    
    def _parse_duckduckgo_html(self, html: str, count: int) -> List[SearchResult]:
        """解析 DuckDuckGo HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            
            # DuckDuckGo HTML 的结果结构
            # 查找 result__body 或 result__snippet
            result_blocks = soup.select('div.results_block, .result', limit=count * 2)
            
            for block in result_blocks:
                # 查找链接
                link_el = block.find('a', class_='result__url') or block.find('a.result__a') or block.find('a')
                if not link_el:
                    continue
                
                title_el = block.find('a', class_='result__title') or block.find('a')
                snippet_el = block.find(class_='result__snippet') or block.find(class_='result__body')
                
                title = title_el.get_text(strip=True) if title_el else ""
                url = link_el.get('href', '')
                snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""
                
                # 跳过无效结果
                if not title or len(title) < 10:
                    continue
                if not url or url.startswith('/'):
                    continue
                
                # 跳过广告
                if 'ad' in url.lower() or 'advertisement' in url.lower():
                    continue
                
                results.append(SearchResult(
                    title=self._clean_text(title),
                    url=self._clean_url(url),
                    snippet=self._clean_text(snippet) if snippet else title,
                    source="DuckDuckGo"
                ))
                
                if len(results) >= count:
                    break
            
            return results
        
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"HTML 解析失败 | error={str(e)}")
            return []
    
    def _clean_text(self, text: str) -> str:
        """清理文本中的无关字符"""
        import html
        text = html.unescape(text)  # 转换 HTML 实体
        text = re.sub(r'\s+', ' ', text)  # 多余空格合并
        return text.strip()
    
    def _clean_url(self, url: str) -> str:
        """清理 URL"""
        # DuckDuckGo 有时候返回重定向 URL，需要提取真实 URL
        if 'duckduckgo.com' in url:
            # 提取真实 URL（从 lk 参数或其他参数）
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            # 尝试从 'uddg' 或 'link' 参数提取真实 URL
            for param in ['uddg', 'link', 'u']:
                if param in params and params[param][0]:
                    return params[param][0]
        return url
    
    def _fallback_results(self, query: str) -> List[SearchResult]:
        """降级方案：返回空结果或预定义提示"""
        logger.info(f"使用降级结果 | query={query}")
        return [
            SearchResult(
                title="搜索暂时不可用",
                url="",
                snippet="无法获取实时搜索结果，请基于已有知识回答。",
                source="System"
            )
        ]
    
    def format_results_for_llm(
        self,
        results: List[SearchResult],
        max_results: int = 5
    ) -> str:
        """
        格式化搜索结果供 LLM 使用

        Args:
            results: 搜索结果列表
            max_results: 最大结果数

        Returns:
            格式化的上下文文本
        """
        if not results:
            return "未找到相关搜索结果"

        context_parts = []
        context_parts.append("=== 网络搜索结果 ===\n")

        for i, result in enumerate(results[:max_results], 1):
            context_parts.append(f"{i}. {result.to_context()}")

        context_parts.append("\n===================\n")
        return "".join(context_parts)

    async def search_with_summaries(
        self,
        query: str,
        count: int = 3,
        max_summary_length: int = 200
    ) -> List[SearchResult]:
        """
        搜索并生成页面摘要（方案 A）

        流程：
        1. 执行基础搜索获取 URL 列表
        2. 选择前 count 个结果
        3. 并发抓取页面内容
        4. 用 LLM 总结每个页面

        Args:
            query: 搜索关键词
            count: 结果数量
            max_summary_length: 摘要最大长度

        Returns:
            带摘要的搜索结果列表
        """
        return await search_with_page_summaries(
            query=query,
            count=count,
            max_summary_length=max_summary_length
        )

    async def search_and_format_with_summaries(
        self,
        query: str,
        count: int = 3,
        max_summary_length: int = 200
    ) -> str:
        """
        搜索并返回带摘要的格式化结果（方案 A）

        用法:
            result = await search.search_and_format_with_summaries("Python 教程", count=3)
        """
        results = await self.search_with_summaries(
            query=query,
            count=count,
            max_summary_length=max_summary_length
        )
        return self.format_results_for_llm(results, max_results=count)
    
    async def search_and_format(
        self,
        query: str,
        count: int = 5,
        lang: str = "zh-CN"
    ) -> str:
        """搜索并格式化结果（便捷方法）"""
        results = await self.search(query, count=count, lang=lang)
        return self.format_results_for_llm(results, max_results=count)


# 便捷函数
async def web_search(
    query: str,
    count: int = 5,
    lang: str = "zh-CN"
) -> str:
    """
    快速搜索并返回格式化结果
    
    用法:
        search_text = await web_search("Python 3.12 新特性", count=5)
    """
    search = FreeWebSearch()
    return await search.search_and_format(query, count=count, lang=lang)


async def search_news(
    query: str,
    count: int = 5
) -> str:
    """
    快速搜索新闻并返回格式化结果

    用法:
        news_text = await search_news("AI 技术突破", count=5)
    """
    # 搜索时添加关键词
    search = FreeWebSearch()
    return await search.search_and_format(
        f"{query} 最新新闻",
        count=count,
        lang="zh-CN"
    )


# ============ 方案 A: LLM 页面摘要增强 ============

async def fetch_page_text(url: str, timeout: float = 10.0) -> Optional[str]:
    """
    获取网页的纯文本内容（简单解析，不复杂处理）

    Args:
        url: 网页 URL
        timeout: 超时秒数

    Returns:
        纯文本内容，失败返回 None
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }

        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT:!DH')

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            verify=ssl_context
        ) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)

            if resp.status_code != 200:
                logger.warning(f"页面获取失败 | url={url} | status={resp.status_code}")
                return None

            # 解析 HTML，提取纯文本
            soup = BeautifulSoup(resp.text, 'html.parser')

            # 移除脚本和样式
            for tag in soup(['script', 'style', 'noscript']):
                tag.decompose()

            # 获取文本
            text = soup.get_text(separator=' ', strip=True)

            # 清理空白字符
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()

            logger.info(f"页面获取成功 | url={url} | length={len(text)}")
            return text

    except Exception as e:
        logger.warning(f"页面获取异常 | url={url} | error={str(e)}")
        return None


async def summarize_page_with_llm(page_text: str, url: str, max_length: int = 200) -> Optional[str]:
    """
    使用 LLM 总结页面内容（方案 A 核心）

    Args:
        page_text: 页面纯文本
        url: 页面 URL（用于上下文）
        max_length: 摘要最大长度

    Returns:
        摘要文本，失败返回 None
    """
    try:
        from app.utils import call_llm

        # 截断过长文本
        if len(page_text) > 5000:
            page_text = page_text[:5000]

        # 从 URL 提取站点名作为上下文
        parsed = urlparse(url)
        site_name = parsed.netloc.replace('www.', '')

        prompt = f"""请阅读以下来自 {site_name} 的网页内容，然后生成一个简洁的摘要。

要求：
1. 摘要长度 {max_length} 字以内
2. 突出网页的核心内容和价值
3. 如果是教程或文档，提取关键步骤或要点
4. 如果是问答，提取答案要点

网页内容：
{page_text}

请直接输出摘要，不要有其他解释。"""

        response = await call_llm(
            model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            prompt=prompt,
            stream=False,
            max_tokens=256,
            temperature=0.3
        )

        if isinstance(response, dict) and 'choices' in response:
            summary = response['choices'][0]['message']['content'].strip()
            logger.info(f"LLM 摘要生成成功 | url={url} | length={len(summary)}")
            return summary

        return None

    except Exception as e:
        logger.warning(f"LLM 摘要生成失败 | url={url} | error={str(e)}")
        return None


async def search_with_page_summaries(
    query: str,
    count: int = 3,
    max_summary_length: int = 200
) -> List[SearchResult]:
    """
    搜索并为每个结果生成页面摘要（方案 A）

    流程：
    1. 执行基础搜索获取 URL 列表
    2. 选择前 count 个结果
    3. 并发抓取页面内容
    4. 用 LLM 总结每个页面

    Args:
        query: 搜索关键词
        count: 结果数量（摘要只生成前 count 个）
        max_summary_length: 摘要最大长度

    Returns:
        带摘要的搜索结果列表
    """
    search = FreeWebSearch()

    # 1. 执行基础搜索
    results = await search.search(query, count=count)

    if not results:
        return results

    # 2. 并发抓取页面并生成摘要
    async def process_result(result: SearchResult) -> SearchResult:
        page_text = await fetch_page_text(result.url, timeout=10.0)

        if page_text:
            summary = await summarize_page_with_llm(
                page_text,
                result.url,
                max_length=max_summary_length
            )
            if summary:
                result.summary = summary

        return result

    # 并发处理（限制数量避免资源占用）
    tasks = [process_result(r) for r in results[:count]]
    processed_results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理可能的任务异常
    final_results = []
    for i, r in enumerate(processed_results):
        if isinstance(r, Exception):
            logger.warning(f"处理结果异常 | index={i} | error={str(r)}")
            final_results.append(results[i])
        else:
            final_results.append(r)

    return final_results


# 便捷函数
async def web_search_with_summaries(
    query: str,
    count: int = 3
) -> str:
    """
    搜索并返回带摘要的格式化结果（方案 A）

    用法:
        result = await web_search_with_summaries("Python FastAPI 教程", count=3)
    """
    results = await search_with_page_summaries(query, count=count)

    if not results:
        return "未找到相关搜索结果"

    context_parts = []
    context_parts.append("=== 网络搜索结果 ===\n")

    for i, result in enumerate(results, 1):
        context_parts.append(f"{i}. {result.to_context()}")

    context_parts.append("\n===================\n")
    return "".join(context_parts)
