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
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import quote, urlparse, urljoin, unquote
import httpx
from bs4 import BeautifulSoup
import re
from app.agent.models import DEFAULT_REASONING_MODEL

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



_EN_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "what", "how",
    "are", "was", "new", "into", "about",
}
_CJK_STOP = {
    "的", "了", "是", "在", "和", "与", "或", "吗", "呢", "吧",
    "什么", "怎么", "如何", "一下", "这个", "那个",
    "年", "月", "日",
}
_GENERIC_CJK = {
    "时间", "开放", "今天", "最新", "查询", "介绍", "网站", "信息",
    "内容", "相关", "使用", "可以", "问题", "方法", "官方",
    "今年", "去年", "明年", "本月", "本周", "昨天", "明天", "现在", "目前",
    "中国", "全国", "我国", "国内", "数据",
}
_CJK_STOP_CHARS = set("的了是在和与或吗呢吧年月")


def extract_query_terms(query: str) -> Dict[str, List[str]]:
    """Split a query into versions, English tokens, and CJK pieces."""
    text = (query or "").strip()
    versions = re.findall(r"\d+(?:\.\d+)+", text)
    english = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{1,}", text)
        if word.lower() not in _EN_STOP
    ]
    cjk: List[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        cjk.extend(_split_cjk_run(run))
    return {
        "versions": _unique(versions),
        "english": _unique(english),
        "cjk": _unique([piece for piece in cjk if piece not in _CJK_STOP]),
    }


def _split_cjk_run(run: str) -> List[str]:
    """Break a CJK run on stop characters before taking 2-char pieces."""
    parts: List[str] = []
    buf: List[str] = []
    for char in run:
        if char in _CJK_STOP_CHARS:
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(char)
    if buf:
        parts.append("".join(buf))

    pieces: List[str] = []
    for part in parts:
        if not part or part in _CJK_STOP:
            continue
        if len(part) <= 3:
            pieces.append(part)
            continue
        for index in range(0, len(part) - 1, 2):
            pieces.append(part[index:index + 2])
        if len(part) % 2 == 1:
            pieces.append(part[-2:])
    return pieces


def expand_relative_time(text: str, now: datetime | None = None) -> str:
    """Replace 今年/今天/本月 with concrete calendar values for search queries."""
    current = now or datetime.now()
    monday = current - timedelta(days=current.weekday())
    sunday = monday + timedelta(days=6)
    replacements = (
        ("最近五年", f"{current.year - 4}年至{current.year}年"),
        ("最近三年", f"{current.year - 2}年至{current.year}年"),
        ("最近两年", f"{current.year - 1}年至{current.year}年"),
        ("过去五年", f"{current.year - 4}年至{current.year}年"),
        ("过去三年", f"{current.year - 2}年至{current.year}年"),
        ("近五年", f"{current.year - 4}年至{current.year}年"),
        ("近三年", f"{current.year - 2}年至{current.year}年"),
        ("近两年", f"{current.year - 1}年至{current.year}年"),
        ("这个月", f"{current.year}年{current.month}月"),
        ("本月", f"{current.year}年{current.month}月"),
        ("本周", f"{monday.strftime('%Y年%m月%d日')}至{sunday.strftime('%Y年%m月%d日')}"),
        ("今天", current.strftime("%Y年%m月%d日")),
        ("昨天", (current - timedelta(days=1)).strftime("%Y年%m月%d日")),
        ("明天", (current + timedelta(days=1)).strftime("%Y年%m月%d日")),
        ("前几年", f"{current.year - 3}年至{current.year - 1}年"),
        ("近几年", f"{current.year - 3}年至{current.year}年"),
        ("今年", f"{current.year}年"),
        ("去年", f"{current.year - 1}年"),
        ("明年", f"{current.year + 1}年"),
    )
    expanded = text or ""
    for source, dest in replacements:
        if source in expanded:
            expanded = expanded.replace(source, dest)
    return expanded


def extract_named_entity(query: str) -> str:
    """Split a Chinese topic from its aspect using 的/之, not org-type suffixes."""
    expanded = expand_relative_time(query or "")
    compact = re.sub(r"\s+", "", expanded)
    for sep in ("的", "之"):
        if sep not in compact:
            continue
        left, right = compact.split(sep, 1)
        left = _strip_time_marks(left)
        right = _strip_time_marks(right)
        if _is_entity_name(left) and right:
            return left
    parts = [part for part in re.split(r"\s+", expanded) if part]
    if len(parts) >= 2:
        head = _strip_time_marks(parts[0])
        rest = "".join(parts[1:])
        if (
            _is_entity_name(head)
            and re.search(r"[\u4e00-\u9fff]", head)
            and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", rest)
        ):
            return head
    return ""


def _strip_time_marks(text: str) -> str:
    cleaned = expand_relative_time(text or "")
    cleaned = re.sub(r"\d{4}年?", "", cleaned)
    return re.sub(r"[至\s]+", "", cleaned)


def _is_entity_name(text: str) -> bool:
    name = (text or "").strip()
    if not 2 <= len(name) <= 24:
        return False
    if re.fullmatch(r"\d{4}年?", name):
        return False
    if name in _GENERIC_CJK:
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", name))


def aspect_tokens(query: str, entity: str) -> List[str]:
    """CJK tokens that remain after removing the named entity and calendar spans."""
    rest = (query or "").replace(entity or "", " ")
    rest = expand_relative_time(rest)
    rest = re.sub(r"\d{4}年?", " ", rest)
    rest = re.sub(r"[至的了和与]", " ", rest)
    tokens = [
        token
        for token in extract_query_terms(rest).get("cjk") or []
        if token not in _GENERIC_CJK
    ]
    return _unique(tokens)


def is_aggregator_host(host: str) -> bool:
    """Search/encyclopedia hosts are not treated as the entity's own site."""
    normalized = (host or "").lower().removeprefix("www.")
    suffixes = (
        "baike.baidu.com",
        "baidu.com",
        "zhihu.com",
        "wikipedia.org",
        "bing.com",
        "google.com",
        "google.com.hk",
        "sogou.com",
        "so.com",
        "duckduckgo.com",
        "microsoft.com",
    )
    return any(normalized == item or normalized.endswith("." + item) for item in suffixes)


def _org_labels(host: str) -> List[str]:
    host = (host or "").lower().removeprefix("www.")
    for suffix in (".edu.cn", ".gov.cn", ".org.cn", ".com.cn"):
        if host.endswith(suffix):
            return host[: -len(suffix)].split(".")
    if host.endswith(".cn"):
        return host[:-3].split(".")
    if "." in host:
        return host.rsplit(".", 1)[0].split(".")
    return [host] if host else []


def same_org_host(candidate: str, official: str) -> bool:
    """True when a link host belongs to the same org as an official search hit."""
    cand = _org_labels(candidate)
    off = _org_labels(official)
    if not cand or not off:
        return False
    key = off[-1]
    return len(key) >= 3 and key == cand[-1]


def decode_openexternallink(href: str) -> str:
    """Decode school-site javascript:openexternallink('base64') targets."""
    match = re.search(r"openexternallink\('([^']+)'\)", href or "", re.I)
    if not match:
        return ""
    try:
        decoded = base64.b64decode(match.group(1)).decode("utf-8", "ignore")
        return unquote(decoded).strip()
    except (ValueError, TypeError, OSError):
        return ""


def parse_official_aspect_links(
    html: str,
    page_url: str,
    entity: str,
    aspect: List[str],
    official_hosts: List[str],
) -> List[SearchResult]:
    """Turn homepage anchors that match the question aspect into search hits."""
    if not html or not aspect:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: List[SearchResult] = []
    seen = set()
    page_host = (urlparse(page_url).netloc or "").lower()
    allowed = [host.lower() for host in official_hosts if host] + ([page_host] if page_host else [])
    for anchor in soup.find_all("a"):
        text = re.sub(r"\s+", "", anchor.get_text(" ", strip=True) or "")
        href = (anchor.get("href") or "").strip()
        if href.lower().startswith("javascript:"):
            href = decode_openexternallink(href)
        if not href or href.startswith("#"):
            continue
        blob = f"{text} {href}"
        if not any(token in blob for token in aspect):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        host = parsed.netloc.lower()
        if not any(host == item or same_org_host(host, item) for item in allowed):
            continue
        key = absolute.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        title = text or absolute
        results.append(SearchResult(
            title=title[:200],
            url=absolute,
            snippet=f"{entity} {title}"[:300],
            source=host,
        ))
        if len(results) >= 8:
            break
    return results


def prefer_entity_aspect_results(
    results: List[SearchResult],
    query: str,
    entity: str,
) -> List[SearchResult]:
    """Prefer official pages that mention the entity and the remaining aspect."""
    aspect = aspect_tokens(query, entity)
    with_aspect: List[SearchResult] = []
    entity_only: List[SearchResult] = []
    for item in results:
        if not item.url:
            continue
        blob = f"{item.title} {item.snippet} {item.url}"
        if entity not in blob:
            continue
        if aspect and any(token in blob for token in aspect):
            with_aspect.append(item)
        else:
            entity_only.append(item)
    return with_aspect or entity_only


def _unique(items: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def relevance_score(result: SearchResult, terms: Dict[str, List[str]]) -> float:
    """Score how many distinctive query terms appear in a result."""
    blob = f"{result.title} {result.snippet} {result.url}".lower()
    versions = terms.get("versions") or []
    tokens = (terms.get("english") or []) + (terms.get("cjk") or [])
    if not versions and not tokens:
        return 1.0
    version_hits = sum(1 for version in versions if version.lower() in blob)
    core_tokens = (terms.get("english") or []) + [
        token for token in (terms.get("cjk") or []) if token not in _GENERIC_CJK
    ]
    scored_tokens = core_tokens or tokens
    token_hits = sum(1 for token in scored_tokens if token.lower() in blob)
    version_part = 1.0 if not versions else version_hits / len(versions)
    token_part = 1.0 if not scored_tokens else token_hits / len(scored_tokens)
    if versions:
        score = 0.6 * version_part + 0.4 * token_part
    else:
        score = token_part
    core_cjk = [token for token in (terms.get("cjk") or []) if token not in _GENERIC_CJK]
    if core_cjk:
        version_ok = bool(versions) and version_hits == len(versions)
        if not version_ok and core_cjk[-1].lower() not in blob:
            return min(score, 0.2)
        if terms.get("require_phrase", True):
            cjk_terms = terms.get("cjk") or []
            if not version_ok and len(cjk_terms) >= 2:
                phrase = cjk_terms[-2] + cjk_terms[-1]
                if phrase.lower() not in blob:
                    return min(score, 0.2)
    return score


def filter_relevant_results(
    results: List[SearchResult],
    query: str,
    min_score: float = 0.4,
    require_phrase: bool = True,
) -> List[SearchResult]:
    """Drop results that only match a generic first keyword."""
    terms = extract_query_terms(query)
    terms["require_phrase"] = require_phrase
    ranked = sorted(
        ((item, relevance_score(item, terms)) for item in results if item.url),
        key=lambda pair: pair[1],
        reverse=True,
    )
    kept = [item for item, score in ranked if score >= min_score]
    if kept:
        return kept
    return []


def merge_results_by_url(groups: List[List[SearchResult]]) -> List[SearchResult]:
    """Keep first occurrence of each normalized URL."""
    merged: List[SearchResult] = []
    seen = set()
    for group in groups:
        for item in group:
            key = (item.url or "").rstrip("/").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def search_query_variants(query: str) -> List[str]:
    """Add English what's-new queries when the user asks for a version changelog."""
    variants = []
    expanded = expand_relative_time(query)
    entity = extract_named_entity(expanded)
    if entity:
        variants.append(entity)
    variants.append(query)
    if expanded != query:
        variants.append(expanded)
    terms = extract_query_terms(query)
    if (
        terms["versions"]
        and terms["english"]
        and any(marker in (query or "") for marker in ("新特性", "新功能", "更新说明", "发布说明"))
    ):
        head = " ".join(terms["english"][:2])
        version = terms["versions"][0]
        variants.append(f"{head} {version} what's new")
        variants.append(f"{head} {version} release notes")
    years = re.findall(r"20\d{2}", expanded)
    stat_marks = ("就业", "失业", "人口", "物价", "经济", "gdp", "GDP", "工资")
    if (
        years
        and any(scope in expanded for scope in ("中国", "全国"))
        and any(mark in expanded for mark in stat_marks)
    ):
        variants.append(f"{years[-1]}年国民经济和社会发展统计公报")
    return _unique(variants)


def official_reference_results(query: str) -> List[SearchResult]:
    """Stable official docs for queries Bing HTML often misses."""
    terms = extract_query_terms(query)
    english = [token.lower() for token in (terms.get("english") or [])]
    versions = terms.get("versions") or []
    results: List[SearchResult] = []
    changelog_marks = ("新特性", "新功能", "更新说明", "发布说明", "what's new", "whats new", "release notes")
    if "python" in english and versions and any(mark in (query or "").lower() for mark in changelog_marks):
        version = versions[0]
        results.append(SearchResult(
            title=f"What's New In Python {version}",
            url=f"https://docs.python.org/{version}/whatsnew/{version}.html",
            snippet=f"Official Python {version} changelog covering new features and incompatibilities.",
            source="Python Docs",
        ))
        results.append(SearchResult(
            title=f"Python {version} 新特性",
            url=f"https://docs.python.org/zh-cn/{version}/whatsnew/{version}.html",
            snippet=f"Python {version} 官方中文「新特性」文档。",
            source="Python Docs",
        ))
    return results


def title_has_core_entity(result: SearchResult, query: str) -> bool:
    """Keep encyclopedia hits whose title names the main CJK entity."""
    core = [token for token in (extract_query_terms(query).get("cjk") or []) if token not in _GENERIC_CJK]
    if not core:
        return True
    return core[-1] in (result.title or "")


def parse_wikipedia_search(payload: Dict, lang: str) -> List[SearchResult]:
    """Convert MediaWiki search JSON into SearchResult items."""
    hits = ((payload or {}).get("query") or {}).get("search") or []
    results: List[SearchResult] = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        snippet = re.sub(r"<[^>]+>", " ", hit.get("snippet") or "")
        snippet = re.sub(r"\s+", " ", snippet).strip()
        results.append(SearchResult(
            title=title,
            url=f"https://{lang}.wikipedia.org/wiki/{quote(title)}",
            snippet=snippet[:300] or title,
            source="Wikipedia",
        ))
    return results


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
            fetch_count = max(count * 2, 8)
            bing_raw = []
            for variant in search_query_variants(query):
                variant_hits = await self._search_baidu(variant, fetch_count, lang)
                bing_raw.extend(filter_relevant_results(variant_hits, variant))
            merged_bing = merge_results_by_url([bing_raw])
            bing_results = merged_bing
            entity = extract_named_entity(query)
            if entity:
                entity_hits = [
                    item for item in merged_bing
                    if entity in f"{item.title} {item.snippet}"
                ]
                discovered = await self._discover_official_aspect_pages(
                    entity_hits, query, entity
                )
                wiki_raw = await self._search_wikipedia(entity, fetch_count)
                wiki_hits = [item for item in wiki_raw if entity in (item.title or "")]
                preferred = prefer_entity_aspect_results(
                    merge_results_by_url([discovered, bing_results, entity_hits, wiki_hits]),
                    query,
                    entity,
                )
                if preferred:
                    logger.info(f"实体/官网检索成功 | 结果数={len(preferred)}")
                    return preferred[:count]
            if bing_results:
                logger.info(f"Bing 搜索成功 | 结果数={len(bing_results)}")
                return bing_results[:count]

            # 备用 DuckDuckGo
            logger.warning("Bing 结果不足或相关性低，尝试 DuckDuckGo")
            ddg_results = filter_relevant_results(
                await self._search_duckduckgo(query, max(count * 2, 8)),
                query,
            )
            merged = filter_relevant_results(
                merge_results_by_url([bing_results, ddg_results]),
                query,
            )
            if merged:
                logger.info(f"合并搜索成功 | 结果数={len(merged)}")
                return merged[:count]

            refs = official_reference_results(query)
            wiki_raw = await self._search_wikipedia(query, fetch_count)
            wiki_results = filter_relevant_results(
                [item for item in wiki_raw if title_has_core_entity(item, query)],
                query,
                require_phrase=False,
            )
            extra = filter_relevant_results(
                merge_results_by_url([refs, wiki_results]),
                query,
                require_phrase=False,
            )
            if extra:
                logger.info(f"百科/官方文档补全 | 结果数={len(extra)}")
                return extra[:count]

            logger.warning("所有搜索服务都失败，使用降级结果")
            return self._fallback_results(query)

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"搜索失败 | query={query} | error={str(e)}")
            return self._fallback_results(query)

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML for official-site link discovery."""
        import ssl
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ""
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT:!DH")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                verify=ssl_context,
            ) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return ""
            return resp.text
        except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
            logger.warning(f"官网页面抓取失败 | url={url} | error={exc}")
            return ""

    async def _discover_official_aspect_pages(
        self,
        entity_hits: List[SearchResult],
        query: str,
        entity: str,
    ) -> List[SearchResult]:
        """Fetch official homepages and keep in-site links that match the aspect."""
        aspect = aspect_tokens(query, entity)
        if not aspect or not entity_hits:
            return []
        entries: List[str] = []
        official_hosts: List[str] = []
        seen_org = set()
        for item in entity_hits:
            parsed = urlparse(item.url or "")
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
            host = parsed.netloc.lower()
            if is_aggregator_host(host):
                continue
            labels = tuple(_org_labels(host)[-1:])
            if labels in seen_org:
                continue
            seen_org.add(labels)
            official_hosts.append(host)
            entries.append(f"{parsed.scheme}://{parsed.netloc}/")
            if len(entries) >= 2:
                break
        discovered: List[SearchResult] = []
        for entry in entries:
            html = await self._fetch_html(entry)
            discovered.extend(
                parse_official_aspect_links(html, entry, entity, aspect, official_hosts)
            )
        return merge_results_by_url([discovered])

    async def _search_baidu(self, query: str, count: int, lang: str = "zh-CN") -> List[SearchResult]:
        """Bing 搜索（替代方案）"""
        try:
            url = "https://www.bing.com/search"
            use_zh = (lang or "zh-CN").lower().startswith("zh")
            params = {
                "q": query,
                "count": min(count, 20),
                "mkt": "zh-CN" if use_zh else "en-US",
                "setlang": "zh-hans" if use_zh else "en",
                "cc": "CN" if use_zh else "US",
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
    
    async def _search_wikipedia(self, query: str, count: int) -> List[SearchResult]:
        """MediaWiki search API (zh first, then en)."""
        headers = {
            "User-Agent": "AicodeWebSearch/1.0 (chat grounding; +https://github.com/)",
            "Accept": "application/json",
        }
        langs = ("zh", "en") if (query and re.search(r"[\u4e00-\u9fff]", query)) else ("en", "zh")
        collected: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                for lang in langs:
                    resp = await client.get(
                        f"https://{lang}.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "list": "search",
                            "srsearch": query,
                            "srlimit": min(count, 8),
                            "format": "json",
                            "utf8": 1,
                        },
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        continue
                    collected.extend(parse_wikipedia_search(resp.json(), lang))
                    if len(collected) >= count:
                        break
        except Exception as e:
            logger.warning(f"Wikipedia 搜索异常 | error={str(e)}")
        return collected[:count]

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

    async def search_with_sources(self, query: str, count: int = 5, lang: str = "zh-CN") -> tuple[str, list[dict]]:
        """Return bounded model context and displayable source metadata together."""
        results = await self.search(query, count=count, lang=lang)
        sources = [
            {"title": item.title[:200], "url": item.url, "snippet": item.snippet[:500]}
            for item in results[:count] if item.url
        ]
        return self.format_results_for_llm(results, max_results=count), sources


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
            model=DEFAULT_REASONING_MODEL,
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
