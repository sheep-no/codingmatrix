"""
代码生成 API - 纯问答（不创建文件）

职责：
- 回答用户问题（生活/技术/编程等）
- 生成代码片段（不创建文件）
- 理解图片/文件内容（只读，首次解析缓存）
- 携带会话历史上下文

注意：
- 不创建任何文件
- 不修改工作空间
- 只输出文本/代码给用户
"""
import asyncio
import re
import inspect
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, Tuple, Optional, List, Callable, Awaitable
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schema.codeRequest import CodeRequest
from app.utils import call_llm
from app.utils.web_search import FreeWebSearch, expand_relative_time, fetch_page_text
from app.utils.aicloud.llm_caller import LLMCallError
from app.agent.models import DEFAULT_ARCHITECT_MODEL, DEFAULT_FAST_MODEL, DEFAULT_REASONING_MODEL
from fastapi.responses import StreamingResponse
from app.utils.security import verify_token
from app.db.add_history import invalidate_history_caches, save_history_to_db
from app.utils.vision import analyze_image
from app.models.file import File
from app.models.history import History
from sqlalchemy import select, delete, and_, update
from sqlalchemy.exc import SQLAlchemyError

from app.utils.json_parser import RobustJSONParser
from app.services.chat_context import fit_context, is_context_length_error
from app.models.unified_state import Message, Session, SessionEvent
from app.services.unified_state_service import append_message, create_session
from app.utils.aicloud.knowledge_processor import parse_document

# 初始化日志
logger = logging.getLogger(__name__)
router = APIRouter()
_parser = RobustJSONParser(strict_mode=False)
CHAT_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

# 部分响应缓存 {task_id: {"prompt": ..., "partial_response": ..., "model": ..., "timestamp": ...}}
_partial_response_cache: Dict[str, dict] = {}
_PARTIAL_TTL = 300  # 5 分钟过期


async def _append_shared_chat_messages(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    prompt: str,
    response: str,
) -> None:
    """把旧 History 写入统一会话消息，迁移期间保持双写。"""
    session = await db.scalar(
        select(Session).where(
            Session.user_id == user_id,
            Session.module == "chat",
            Session.external_id == str(conversation_id),
        )
    )
    if session is None:
        session = await create_session(db, user_id, "chat", external_id=str(conversation_id))
    await append_message(db, session.id, user_id, "user", prompt)
    await append_message(db, session.id, user_id, "assistant", response)
    await db.commit()
    await invalidate_history_caches()


async def _delete_shared_chat_data(db: AsyncSession, user_id: int, conversation_ids: Optional[List[int]] = None, delete_all: bool = False) -> int:
    session_query = select(Session.id).where(Session.user_id == user_id, Session.module == "chat")
    if not delete_all:
        session_query = session_query.where(Session.external_id.in_([str(value) for value in conversation_ids or []]))
    session_ids = list((await db.scalars(session_query)).all())

    if session_ids:
        await db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
        await db.execute(delete(SessionEvent).where(SessionEvent.session_id.in_(session_ids)))
        await db.execute(delete(Session).where(Session.id.in_(session_ids)))

    file_query = update(File).where(File.user_id == user_id, File.is_deleted == 0)
    if delete_all:
        file_query = file_query.where(File.conversation_id.is_not(None))
    else:
        file_query = file_query.where(File.conversation_id.in_(conversation_ids or []))
    await db.execute(file_query.values(is_deleted=1))
    return len(session_ids)


def _cleanup_partial_cache():
    """清理过期的部分响应缓存"""
    now = datetime.utcnow()
    expired_keys = []
    for task_id, data in _partial_response_cache.items():
        try:
            cached_time = datetime.fromisoformat(data.get("timestamp", ""))
            if (now - cached_time).total_seconds() > _PARTIAL_TTL:
                expired_keys.append(task_id)
        except Exception:
            expired_keys.append(task_id)
    
    for task_id in expired_keys:
        _partial_response_cache.pop(task_id, None)
    
    return len(expired_keys)

# 通用提示词模板
# -----------------------------
GENERAL_PROMPT = """请回答以下问题：

问题：{prompt}

{context}

请用清晰、准确、有用的方式回答。如果是专业问题（如编程、科学等），请提供详细的解释和示例；如果是生活问题，请提供实用的建议。"""

# 代码专用提示词（当检测到代码需求时使用）
CODE_PROMPT = """请生成代码或解答技术问题：

需求：{prompt}

{context}

要求：
1. 提供完整可运行的代码（如适用）
2. 添加必要的注释
3. 解释关键逻辑
4. 说明使用方法和注意事项"""

# 推理增强提示词（复杂问题使用）
REASONING_PROMPT = """请深入分析以下问题：

问题：{prompt}

{context}

请按以下步骤思考：
1. 理解问题的核心需求
2. 分析相关背景和约束条件
3. 提供详细的解决方案
4. 说明可能的替代方案

请用结构化的方式回答。"""


# 工具函数
# -----------------------------

def current_time_block(now: datetime | None = None) -> str:
    """Give the model an explicit calendar so 今年/今天 can be resolved."""
    current = now or datetime.now()
    weekdays = "一二三四五六日"
    return (
        f"[当前时间] {current.strftime('%Y-%m-%d %H:%M')}，星期{weekdays[current.weekday()]}。"
        "涉及「今年」「今天」「本月」时按该日期理解。"
    )



_GREETINGS = {
    "你好", "您好", "在吗", "嗨", "哈喽", "早上好", "晚上好",
    "hi", "hello", "hey", "yo",
}
_SEARCH_DECISION_PROMPT = """当前时间：{now}

用户问题：
{prompt}

判断回答该问题是否必须检索公开互联网。需要网上的事实、数据、新闻、价格、政策、统计、特定年份或「今年/前几年」资料时 search=true。
编写代码、解释概念、翻译润色、纯数学计算时 search=false。
只输出 JSON，例如 {{"search": true}} 或 {{"search": false}}。"""


def parse_search_decision(text: str) -> Optional[bool]:
    """Parse the classifier JSON; None means the model output was unusable."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        payload = json.loads(raw[start:end + 1] if start >= 0 and end > start else raw)
        if isinstance(payload, dict) and "search" in payload:
            return bool(payload["search"])
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


async def ai_decide_search(prompt: str, api_key_token: Optional[str] = None) -> bool:
    """Ask the fast model whether this question needs live web data."""
    text = (prompt or "").strip()
    if not text or text.lower() in _GREETINGS:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        result = await call_llm(
            model=DEFAULT_FAST_MODEL,
            prompt=_SEARCH_DECISION_PROMPT.format(now=now, prompt=text[:1000]),
            stream=False,
            temperature=0.0,
            max_tokens=64,
            timeout=8.0,
            api_key_token=api_key_token,
        )
        content = (
            ((result or {}).get("choices") or [{}])[0]
            .get("message", {})
            .get("content")
            or ""
        )
        decision = parse_search_decision(content)
        if decision is None:
            logger.info("搜索判断无法解析，默认检索 | raw=%s", str(content)[:80])
            return True
        return decision
    except Exception as exc:
        logger.warning("搜索判断失败，默认检索 | error=%s", exc)
        return True


def build_bounded_search_query(prompt: str, attachment_names: Optional[List[str]] = None) -> str:
    """构造只含问题摘要和附件实体的有限搜索词。"""
    query = " ".join(prompt.split())[:260]
    names = []
    for name in attachment_names or []:
        entity = Path(name).stem.replace("_", " ").replace("-", " ").strip()
        if entity:
            names.append(entity[:80])
    entity_prefix = " ".join(names)[:140].strip()
    combined = " ".join(part for part in (entity_prefix, query) if part)[:400]
    return expand_relative_time(combined)[:400]


_SEARCH_PLAN_PROMPT = """当前时间：{now}

用户问题：
{prompt}

附件关键词：
{attachments}

已检索到的来源：
{sources}

上一轮失败的查询：
{failed}

请规划下一步联网动作，只输出 JSON，不要解释。
可选：
{{"action":"search","queries":["关键词1","关键词2"]}}
{{"action":"fetch","urls":["https://..."]}}
{{"action":"stop"}}

要求：
- search 的 queries 是搜索引擎关键词，不要整句复述用户问题。
- 主体名称写完整，再加方面词（如 就业质量报告、开放时间、价格）。
- 全国/年度就业、GDP、人口、物价等，查询写成「YYYY年国民经济和社会发展统计公报」或「国家统计局 YYYY 就业」。
- 把今年/近三年/前几年展开成具体年份。
- 上一轮失败的查询不要再用，必须换词。
- 每次最多 3 条查询，每条不超过 80 字。
- fetch 的 url 必须来自已有来源。
- 资料足够回答则 stop。
"""


def parse_search_plan(text: str) -> Optional[Dict[str, Any]]:
    """Parse a model search/fetch/stop plan; None means the output was unusable."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        payload = json.loads(raw[start:end + 1] if start >= 0 and end > start else raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip().lower()
    queries = payload.get("queries") or []
    urls = payload.get("urls") or []
    if isinstance(queries, str):
        queries = [queries]
    if isinstance(urls, str):
        urls = [urls]
    if action not in {"search", "fetch", "stop"}:
        action = "search" if queries else ""
    if action not in {"search", "fetch", "stop"}:
        return None
    cleaned_queries = []
    for item in queries:
        query = expand_relative_time(" ".join(str(item).split()))[:80]
        if query:
            cleaned_queries.append(query)
    cleaned_urls = []
    for item in urls:
        url = str(item or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            cleaned_urls.append(url)
    return {
        "action": action,
        "queries": cleaned_queries[:3],
        "urls": cleaned_urls[:3],
    }


def _fallback_search_plan(
    prompt: str,
    attachment_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "action": "search",
        "queries": [build_bounded_search_query(prompt, attachment_names)],
        "urls": [],
    }


async def plan_search_actions(
    prompt: str,
    attachment_names: Optional[List[str]] = None,
    sources: Optional[List[Dict[str, str]]] = None,
    failed_queries: Optional[List[str]] = None,
    api_key_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the fast model to write search queries or pick pages to fetch."""
    fallback = _fallback_search_plan(prompt, attachment_names)
    source_lines = []
    for item in (sources or [])[:8]:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        title = (item.get("title") or "")[:80]
        snippet = (item.get("snippet") or "")[:80]
        source_lines.append(f"- {title} | {url} | {snippet}")
    attachments = ", ".join(
        Path(name).stem for name in (attachment_names or []) if name
    ) or "（无）"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        result = await call_llm(
            model=DEFAULT_FAST_MODEL,
            prompt=_SEARCH_PLAN_PROMPT.format(
                now=now,
                prompt=(prompt or "")[:1000],
                attachments=attachments[:200],
                sources="\n".join(source_lines) if source_lines else "（无）",
                failed="\n".join(f"- {item}" for item in (failed_queries or [])[:6]) or "（无）",
            ),
            stream=False,
            temperature=0.0,
            max_tokens=256,
            timeout=8.0,
            api_key_token=api_key_token,
        )
        content = (
            ((result or {}).get("choices") or [{}])[0]
            .get("message", {})
            .get("content")
            or ""
        )
        plan = parse_search_plan(content)
        if not plan:
            logger.info("检索规划无法解析，回退原问题 | raw=%s", str(content)[:80])
            return fallback
        if plan["action"] == "search" and not plan["queries"]:
            return fallback
        if plan["action"] == "fetch" and not plan["urls"]:
            return {"action": "stop", "queries": [], "urls": []} if sources else fallback
        return plan
    except Exception as exc:
        logger.warning("检索规划失败，回退原问题 | error=%s", exc)
        return fallback


async def fetch_source_pages(
    urls: List[str],
    seen: Optional[set] = None,
    limit: int = 2,
) -> List[Dict[str, str]]:
    """Read a few search-hit pages so the answer can use body text, not snippets."""
    fetched: List[Dict[str, str]] = []
    visited = seen if seen is not None else set()
    for raw in urls:
        url = (raw or "").strip()
        if not url or url in visited:
            continue
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        if any(marker in url for marker in (" ", "\n", "\r", "@")):
            continue
        visited.add(url)
        text = await fetch_page_text(url, timeout=8.0)
        if not text:
            continue
        fetched.append({"url": url, "text": text[:1500]})
        if len(fetched) >= limit:
            break
    return fetched


def build_followup_search_query(query: str, sources: List[Dict[str, str]]) -> Optional[str]:
    """Refine the original topic with bounded text from actual search results."""
    query_terms = set(re.findall(r"\w+", query.casefold()))
    ranked_sources = sorted(
        sources[:3],
        key=lambda source: len(query_terms.intersection(re.findall(
            r"\w+", f"{source.get('title', '')} {source.get('snippet', '')}".casefold()
        ))),
        reverse=True,
    )
    for source in ranked_sources:
        fragments = []
        for field, limit in (("title", 70), ("snippet", 100)):
            text = " ".join(source.get(field, "").split())
            if text and text.casefold() not in query.casefold():
                fragments.append(text[:limit])
        if fragments:
            return " ".join([query[:220], *fragments])[:400]
    return None


def extract_stream_content(chunk: str) -> Tuple[bool, str]:
    """
    从 SSE chunk 中提取内容（增强容错）
    """
    try:
        # 尝试直接解析
        data = json.loads(chunk)
        content = (
            data.get("choices", [{}])[0]
            .get("delta", {})
            .get("content", "")
        )
        return True, content if content else ""
    except (json.JSONDecodeError, KeyError, IndexError):
        # 尝试容错解析
        try:
            data = _parser.parse(chunk)
            content = (
                data.get("choices", [{}])[0]
                .get("delta", {})
                .get("content", "")
            )
            return True, content if content else ""
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.debug(f"SSE chunk 解析失败：{str(e)[:50]} | chunk: {chunk[:100]}")
            return False, ""


def select_model_for_prompt(prompt: str, use_reasoning: bool, has_files: bool) -> str:
    """
    根据提示内容智能选择模型
    """
    if has_files:
        return "Qwen/Qwen3.5-4B"
    if use_reasoning:
        return DEFAULT_REASONING_MODEL

    analysis_keywords = ['分析', '解释', '原理', '为什么', '比较', '区别',
                         '是什么', '优缺点', '如何理解', '详细说明']
    if any(kw in prompt.lower() for kw in analysis_keywords):
        return DEFAULT_ARCHITECT_MODEL

    return DEFAULT_FAST_MODEL


def format_tokens_usage(resp: Dict) -> Dict:
    """格式化 Token 使用统计"""
    usage = resp.get("usage", {})
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0)
    }


async def compress_conversation_history(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    max_messages: int = 10
) -> str:
    """
    压缩会话历史（只保留最近的若干条）
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
        conversation_id: 会话 ID
        max_messages: 保留的最大消息数
        
    Returns:
        压缩后的历史文本
    """
    try:
        # 获取最近的对话历史
        result = await db.execute(
            select(History)
            .where(
                History.user_id == user_id,
                History.conversation_id == conversation_id
            )
            .order_by(History.id.desc())
            .limit(max_messages)
        )
        histories = result.scalars().all()
        
        if not histories:
            return ""
        
        # 反转顺序（从早到晚）
        histories.reverse()
        
        # 压缩格式：只保留 prompt 和 response 的关键部分
        compressed = []
        for h in histories:
            prompt_short = h.prompt[:100] + "..." if len(h.prompt) > 100 else h.prompt
            response_short = h.response[:150] + "..." if len(h.response) > 150 else h.response
            compressed.append(f"用户：{prompt_short}\n助手：{response_short}")
        
        context = "\n\n--- 对话历史 ---\n" + "\n\n".join(compressed) + "\n---\n\n"
        
        logger.info(f"压缩会话历史 | conversation_id={conversation_id} | messages={len(histories)}")
        return context
        
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"压缩会话历史失败 | error={str(e)}")
        return ""


async def get_or_parse_file(
    file_path: str,
    user_id: int,
    conversation_id: Optional[int],
    db: AsyncSession,
    parse_prompt: str = None
) -> Tuple[str, Dict]:
    """
    获取或解析文件（带缓存）
    
    逻辑：
    1. 检查缓存是否有解析结果
    2. 如果有缓存，直接返回
    3. 如果没有，调用工具解析并写入缓存
    
    Args:
        file_path: 文件路径
        user_id: 用户 ID
        conversation_id: 会话 ID
        db: 数据库会话
        parse_prompt: 解析提示词
        
    Returns:
        (解析后的文本，元数据)
    """
    try:
        # 验证访问权限
        verified_path = await verify_file_access(file_path, user_id, conversation_id, db)
        
        # 查询数据库中的文件记录
        result = await db.execute(
            select(File).where(File.file_path == verified_path)
        )
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="文件未找到")
        
        # 检查是否有有效的解析缓存
        if file_record.is_parse_cache_valid(ttl_seconds=3600):  # 缓存有效期 1 小时
            logger.info(f"使用解析缓存 | file={file_record.filename} | cached_at={file_record.parsed_at}")
            return file_record.parsed_content, {
                "type": "cached",
                "filename": file_record.filename,
                "cached_at": file_record.parsed_at.isoformat()
            }
        
        # 判断文件类型
        ext = Path(file_record.filename).suffix.lower()
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']
        
        if ext in image_extensions:
            # 图片：调用视觉模型
            result = await analyze_image(
                verified_path,
                parse_prompt or "请详细描述这张图片的内容"
            )
            
            parsed_content = result['description']
            model_used = result.get('model_used', 'unknown')
            metadata = {
                "type": "image",
                "filename": file_record.filename,
                "description": parsed_content[:500],
                "model_used": model_used
            }

            # 更新缓存
            file_record.update_parse_cache(parsed_content, ttl_seconds=3600)
            await db.commit()

            logger.info(f"图片解析成功并更新缓存 | file={file_record.filename} | model={model_used}")
            return parsed_content, metadata
            
        else:
            if ext not in {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv", ".log", ".pdf", ".docx"}:
                raise HTTPException(status_code=422, detail=f"附件格式暂不支持：{file_record.filename}，请转换为 PDF、DOCX 或文本文件。")
            try:
                parsed_content = await asyncio.to_thread(parse_document, str(verified_path))
            except Exception as e:
                logger.error(f"普通文档解析失败 | file={file_path} | error={str(e)}")
                raise HTTPException(status_code=422, detail=f"附件解析失败：{file_record.filename}")
            if not parsed_content or not parsed_content.strip():
                raise HTTPException(status_code=422, detail=f"附件无可读取正文：{file_record.filename}")
            file_record.update_parse_cache(parsed_content, ttl_seconds=3600)
            await db.commit()
            metadata = {
                "type": "parsed",
                "filename": file_record.filename,
                "path": str(verified_path),
            }
            return parsed_content, metadata
            
    except HTTPException:
        raise
    except FileNotFoundError as e:
        logger.error(f"文件未找到 | file={file_path} | error={str(e)}")
        raise HTTPException(status_code=404, detail=f"文件未找到：{file_path}")
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"文件解析失败 | file={file_path} | error={str(e)}")
        raise HTTPException(status_code=500, detail=f"文件解析失败：{str(e)}")


async def verify_file_access(
    file_path: str,
    user_id: int,
    conversation_id: Optional[int],
    db: AsyncSession
) -> str:
    """
    验证文件访问权限（会话隔离）
    """
    # 如果是绝对路径，转为相对路径
    if Path(file_path).is_absolute():
        upload_dir = Path("./uploads").resolve()
        try:
            file_path_obj = Path(file_path).resolve()
            file_path_obj.relative_to(upload_dir)
            file_path = str(file_path_obj.relative_to(upload_dir))
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail="只能访问 uploads 目录内的文件"
            )
    
    # 查询数据库：先精确匹配 file_path，再按 filename 兜底
    base_filters = [File.user_id == user_id]
    if conversation_id:
        base_filters.append(File.conversation_id == conversation_id)

    result = await db.execute(
        select(File).where(*base_filters, File.file_path == file_path)
    )
    file_record = result.scalar_one_or_none()

    if not file_record:
        # 兜底：按文件名匹配（用户可能只传了文件名）
        result = await db.execute(
            select(File).where(*base_filters, File.filename == Path(file_path).name)
        )
        file_record = result.scalar_one_or_none()
    
    if not file_record:
        raise HTTPException(
            status_code=403,
            detail="无权访问该文件（可能属于其他会话）"
        )
    
    return file_record.file_path


# 辅助函数
# -----------------------------

async def _build_context(
    user_id: int,
    prompt: str,
    db: AsyncSession,
    conversation_id: Optional[int],
    enable_search: Optional[bool],
    search_count: int,
    search_mode: str = "auto",
    files_to_parse: Optional[List[str]] = None,
    include_history: bool = True,
    on_stage: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    search_depth: str = "shallow",
    api_key_token: Optional[str] = None,
) -> Tuple[str, List[Dict[str, str]], bool, bool, List[Dict[str, str]]]:
    """
    构建上下文：会话历史 + 文件解析 + 联网搜索
    """
    context_parts = []
    sources = []
    attachment_terms = []
    had_files = bool(files_to_parse)
    stage_errors = []

    async def stage(event: Dict[str, Any]) -> None:
        if on_stage:
            result = on_stage(event)
            if inspect.isawaitable(result):
                await result
    
    context_parts.append(current_time_block())

    if include_history and conversation_id:
        history_context = await compress_conversation_history(db, user_id, conversation_id)
        if history_context:
            context_parts.append(history_context)
    
    if files_to_parse:
        for file_path in files_to_parse:
            await stage({"stage": "parsing", "status": "started", "filename": Path(file_path).name})
            try:
                parsed_content, metadata = await get_or_parse_file(
                    file_path, user_id, conversation_id, db
                )
                context_parts.append(f"\n[参考文件：{metadata['filename']}]\n{parsed_content}\n")
                sources.append({"kind": "file", "title": metadata["filename"]})
                attachment_terms.append(metadata["filename"])
                # Only explicit short identity fields are eligible for a web query.
                for line in parsed_content[:2000].splitlines()[:30]:
                    match = re.match(r"^\s*(?:公司(?:名称)?|产品(?:名称)?|标题|company|product|title)\s*[:：]\s*(.{2,60})$", line, re.IGNORECASE)
                    if match:
                        attachment_terms.append(match.group(1))
                        break
                await stage({"stage": "parsing", "status": "completed", "filename": metadata["filename"]})
            except HTTPException as e:
                context_parts.append(f"\n[附件处理失败：{Path(file_path).name}]\n{e.detail}\n")
                stage_errors.append({"stage": "parsing", "error": str(e.detail)})
                await stage({"stage": "parsing", "status": "failed", "error": str(e.detail)})
                logger.warning(f"文件访问被拒绝 | file={file_path} | status={e.status_code} | detail={e.detail}")
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                context_parts.append(f"\n[附件处理失败：{Path(file_path).name}]\n附件解析失败，请检查文件格式或内容。\n")
                stage_errors.append({"stage": "parsing", "error": "附件解析失败，请检查文件格式或内容。"})
                await stage({"stage": "parsing", "status": "failed", "error": "附件解析失败，请检查文件格式或内容。"})
                logger.warning(f"文件解析失败 | file={file_path} | error={str(e)}")
    
    should_search = False
    
    effective_mode = search_mode
    if search_mode == "auto" and enable_search is not None:
        effective_mode = "on" if enable_search else "off"
    if effective_mode == "off":
        logger.info(f"用户禁止搜索 | prompt={prompt[:50]}...")
        await stage({"stage": "searching", "status": "skipped", "reason": "disabled"})
    else:
        should_search = effective_mode == "on" or await ai_decide_search(
            prompt, api_key_token=api_key_token
        )
        logger.info(f"联网模式={effective_mode} | {'执行搜索' if should_search else '跳过搜索'}")
        if not should_search:
            await stage({"stage": "searching", "status": "skipped", "reason": "auto_not_needed"})
    
    if should_search:
        search = FreeWebSearch()
        fallback_query = build_bounded_search_query(prompt, attachment_terms)
        max_rounds = 2 if search_depth == "multi" else 1
        seen_urls = set()
        fetched_urls = set()
        planned_sources: List[Dict[str, str]] = []
        failed_queries: List[str] = []
        empty_retry_left = 1
        round_number = 0
        while round_number < max_rounds:
            round_number += 1
            event = {"stage": "searching", "round": round_number, "total_rounds": max_rounds}
            await stage({**event, "status": "started"})
            try:
                plan = await plan_search_actions(
                    prompt,
                    attachment_names=attachment_terms,
                    sources=planned_sources,
                    failed_queries=failed_queries,
                    api_key_token=api_key_token,
                )
                action = plan.get("action")
                if action == "stop":
                    if planned_sources:
                        await stage({**event, "status": "skipped", "reason": "plan_stop"})
                        break
                    action = "search"
                    plan = {"queries": [fallback_query], "urls": []}
                if action == "fetch":
                    allowed = {item.get("url") for item in planned_sources if item.get("url")}
                    if not allowed:
                        action = "search"
                        plan = {"queries": [fallback_query], "urls": []}
                    else:
                        requested = [url for url in (plan.get("urls") or []) if url in allowed]
                        if not requested or all(url in fetched_urls for url in requested):
                            await stage({**event, "status": "skipped", "reason": "already_fetched"})
                            break
                        pages = await fetch_source_pages(
                            requested,
                            fetched_urls,
                        )
                        if not pages:
                            raise ValueError("未获得网页正文")
                        for page in pages:
                            context_parts.append(f"\n[网页正文 {page['url']}]\n{page['text']}\n")
                        await stage({**event, "status": "completed", "sources": list(sources)})
                        continue
                queries = [item for item in (plan.get("queries") or []) if item] or [fallback_query]
                queries = [item for item in queries if item not in failed_queries] or queries
                web_sources: List[Dict[str, str]] = []
                last_error: Optional[Exception] = None
                for query in queries[:3]:
                    try:
                        round_text, round_sources = await search.search_with_sources(
                            query=query, count=search_count
                        )
                    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as exc:
                        last_error = exc
                        continue
                    if not round_sources:
                        last_error = ValueError("未获得网页来源")
                        continue
                    if round_text:
                        context_parts.append(f"\n[第 {round_number} 轮网络搜索结果]\n{round_text}\n")
                    web_sources.extend(round_sources)
                if not web_sources:
                    failed_queries.extend(item for item in queries if item)
                    if empty_retry_left > 0 and (
                        last_error is None or isinstance(last_error, ValueError)
                    ):
                        empty_retry_left -= 1
                        max_rounds = max(max_rounds, round_number + 1)
                        logger.info("检索无结果，换词重试 | failed=%s", failed_queries[:4])
                        await stage({**event, "status": "skipped", "reason": "empty_retry"})
                        continue
                    raise last_error or ValueError("未获得网页来源")
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                warning = {**event, "error": f"第 {round_number} 轮搜索未获得有效结果，将使用已有资料回答。"}
                stage_errors.append(warning)
                context_parts.append(f"\n[网络搜索失败]\n{warning['error']}\n")
                await stage({**warning, "status": "failed"})
                logger.warning("第 %s 轮搜索失败 | error=%s", round_number, e)
                break
            for source in web_sources:
                if source["url"] not in seen_urls:
                    sources.append(source)
                    planned_sources.append(source)
                    seen_urls.add(source["url"])
            pages = await fetch_source_pages(
                [item["url"] for item in web_sources],
                fetched_urls,
                limit=2,
            )
            for page in pages:
                context_parts.append(f"\n[网页正文 {page['url']}]\n{page['text']}\n")
            await stage({**event, "status": "completed", "sources": list(sources)})
    
    return "\n".join(context_parts) if context_parts else "", sources, should_search, had_files, stage_errors


def _select_prompt_template(prompt: str, use_reasoning: bool) -> str:
    """选择提示词模板（支持从注册表获取自定义版本）"""
    # 优先从注册表获取用户自定义版本
    try:
        from app.services.skill_registry import get_skill
        if use_reasoning:
            custom = get_skill("chat_reasoning_prompt")
            if custom:
                return custom
        elif any(keyword in prompt.lower() for keyword in ['代码', '编程', 'function', 'code', '程序']):
            custom = get_skill("chat_code_prompt")
            if custom:
                return custom
        else:
            custom = get_skill("chat_general_prompt")
            if custom:
                return custom
    except Exception:
        pass
    
    # 否则使用默认模板
    if use_reasoning:
        return REASONING_PROMPT
    elif any(keyword in prompt.lower() for keyword in ['代码', '编程', 'function', 'code', '程序']):
        return CODE_PROMPT
    return GENERAL_PROMPT


# 流式响应生成
# -----------------------------

async def _aclose_llm_stream(stream) -> None:
    """关闭 LLM 流，确保适配器与信号量在客户端断开后释放。"""
    if stream is None:
        return
    release_now = getattr(stream, "release_now", None)
    if callable(release_now):
        release_now()
    aclose = getattr(stream, "aclose", None)
    if aclose is None:
        return

    async def _close():
        try:
            await aclose()
        except Exception:
            logger.debug("关闭 LLM 流失败", exc_info=True)

    close_task = asyncio.get_running_loop().create_task(_close())
    try:
        await asyncio.shield(close_task)
    except asyncio.CancelledError:
        return


async def stream_response(
    user_id: str,
    prompt: str,
    model: str,
    conversation_id: Optional[int],
    db: AsyncSession,
    request: Request,
    use_reasoning: bool = False,
    enable_search: Optional[bool] = None,
    search_count: int = 5,
    files_to_parse: List[str] = None,
    include_history: bool = True,
    resume_from: Optional[str] = None,
    api_key_token: str = None,
    search_mode: str = "auto",
    search_depth: str = "shallow",
) -> AsyncGenerator[str, None]:
    """
    通用流式响应（支持文件解析、历史上下文、联网搜索、SSE 断开检测）
    """
    cancel_event = asyncio.Event()

    # 恢复上下文：如果有部分响应，将其作为前缀
    prefix_text = ""
    if resume_from and resume_from in _partial_response_cache:
        cache = _partial_response_cache.pop(resume_from)
        prefix_text = cache.get("partial_response", "")
        logger.info(f"从部分响应恢复 | task_id={resume_from} | prefix_len={len(prefix_text)}")

    stage_events = asyncio.Queue()

    async def prepare_context():
        try:
            return await _build_context(
                user_id=int(user_id),
                prompt=prompt,
                db=db,
                conversation_id=int(conversation_id) if conversation_id else None,
                enable_search=enable_search,
                search_mode=search_mode,
                search_depth=search_depth,
                search_count=search_count,
                files_to_parse=files_to_parse,
                include_history=include_history,
                on_stage=stage_events.put,
                api_key_token=api_key_token,
            )
        finally:
            await stage_events.put(None)

    context_task = asyncio.create_task(prepare_context())
    try:
        while True:
            event = await stage_events.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"
        full_context, sources, _, _, stage_errors = await context_task
    finally:
        if not context_task.done():
            context_task.cancel()
        try:
            await context_task
        except asyncio.CancelledError:
            pass
    system_prompt = _select_prompt_template(prompt, use_reasoning)
    fitted_context, context_budget = fit_context(prompt, full_context, model, api_key_token)
    final_prompt = system_prompt.format(prompt=prompt, context=fitted_context or "（无额外上下文）")

    # 如果有前缀文本，追加到提示词中
    if prefix_text:
        final_prompt += f"\n\n注意：之前已生成部分内容，请在此基础上继续：\n{prefix_text[-500:]}"

    logger.info(f"开始流式生成 | user_id={user_id} | model={model}")

    response_parts = []

    yield json.dumps({"stage": "answering", "status": "started", "model": model, "sources": sources, "search_depth": search_depth}, ensure_ascii=False) + "\n"
    result_gen = None
    try:
        try:
            result_gen = await call_llm(model=model, prompt=final_prompt, stream=True,
                                        max_tokens=context_budget.max_output_tokens,
                                        cancel_event=cancel_event, api_key_token=api_key_token)
        except Exception as error:
            if not is_context_length_error(error) or not fitted_context:
                raise
            compact_context, _ = fit_context(prompt, fitted_context[:len(fitted_context) // 2], model, api_key_token)
            retry_prompt = system_prompt.format(prompt=prompt, context=compact_context or "（无额外上下文）")
            result_gen = await call_llm(model=model, prompt=retry_prompt, stream=True,
                                        max_tokens=context_budget.max_output_tokens,
                                        cancel_event=cancel_event, api_key_token=api_key_token)

        async for chunk in result_gen:
            # 检测 SSE 断开
            if request and await request.is_disconnected():
                logger.warning(f"客户端断开连接，取消 LLM 调用 | user_id={user_id}")
                cancel_event.set()
                # 保存部分响应
                partial_text = prefix_text + "".join(response_parts)
                if len(partial_text) > 10:
                    task_id = str(uuid.uuid4())
                    _cleanup_partial_cache()
                    _partial_response_cache[task_id] = {
                        "prompt": prompt,
                        "partial_response": partial_text,
                        "model": model,
                        "user_id": user_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f'{{"interrupted": true, "resume_id": "{task_id}", "partial_length": {len(partial_text)}}}\n'
                return

            if cancel_event.is_set():
                return

            yield chunk
            success, content = extract_stream_content(chunk)
            if success and content:
                response_parts.append(content)

        full_response = prefix_text + "".join(response_parts)

        # 检查响应是否为空，避免保存空记录
        if not full_response or not full_response.strip():
            logger.warning(f"AI 生成响应为空 | user_id={user_id} | prompt={prompt[:50]}...")
            yield f'{{"error": "AI 生成响应为空，未保存历史记录"}}\n'
            return

        logger.info(f"流式生成完成，保存历史记录 | response_length={len(full_response)}")
        new_conv_id = await save_history_to_db(
            db=db,
            user_id=int(user_id),
            conversation_id=conversation_id,
            prompt=prompt,
            response=full_response,
            thinking=None,
            metadata={"sources": sources, "warnings": stage_errors, "model": model, "stage": "completed", "search_depth": search_depth},
            commit=False
        )
        await _append_shared_chat_messages(db, int(user_id), new_conv_id, prompt, full_response)
        logger.info(f"历史记录保存成功 | conversation_id={new_conv_id}")
        yield f'{{"conversation_id": {new_conv_id}}}\n'

    except asyncio.CancelledError:
        logger.info(f"LLM 调用被取消 | user_id={user_id}")
        partial_text = prefix_text + "".join(response_parts)
        if len(partial_text) > 10:
            task_id = str(uuid.uuid4())
            _cleanup_partial_cache()
            _partial_response_cache[task_id] = {
                "prompt": prompt,
                "partial_response": partial_text,
                "model": model,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f'{{"interrupted": true, "resume_id": "{task_id}", "partial_length": {len(partial_text)}}}\n'
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"流式生成失败 | error={str(e)}")
        yield '{"error": "服务内部错误，请稍后重试"}\n'
    except LLMCallError as e:
        logger.error(f"流式生成失败 | error={e.message}")
        yield json.dumps({"error": e.message}, ensure_ascii=False) + "\n"
    except Exception as e:
        logger.error(f"流式生成失败 | error={str(e)}")
        yield '{"error": "服务内部错误，请稍后重试"}\n'
    finally:
        await _aclose_llm_stream(result_gen)


# 非流式生成 ==============

async def generate_response(
    user_id: str,
    prompt: str,
    model: str,
    conversation_id: Optional[int],
    db: AsyncSession,
    use_reasoning: bool = False,
    enable_search: Optional[bool] = None,
    search_count: int = 5,
    files_to_parse: List[str] = None,
    include_history: bool = True,
    api_key_token: str = None,
    search_mode: str = "auto",
    search_depth: str = "shallow",
) -> Dict:
    """
    通用非流式响应
    """
    full_context, sources, did_search, had_files, stage_errors = await _build_context(
        user_id=int(user_id),
        prompt=prompt,
        db=db,
        conversation_id=int(conversation_id) if conversation_id else None,
        enable_search=enable_search,
        search_mode=search_mode,
        search_depth=search_depth,
        search_count=search_count,
        files_to_parse=files_to_parse,
        include_history=include_history,
        api_key_token=api_key_token,
    )
    
    system_prompt = _select_prompt_template(prompt, use_reasoning)
    fitted_context, context_budget = fit_context(prompt, full_context, model, api_key_token)
    final_prompt = system_prompt.format(prompt=prompt, context=fitted_context or "（无额外上下文）")
    
    logger.info(f"执行非流式请求 | user_id={user_id} | model={model}")
    
    try:
        result = await call_llm(model=model, prompt=final_prompt, stream=False,
                                max_tokens=context_budget.max_output_tokens,
                                api_key_token=api_key_token)
    except Exception as error:
        if not is_context_length_error(error) or not fitted_context:
            raise
        compact_context, _ = fit_context(prompt, fitted_context[:len(fitted_context) // 2], model, api_key_token)
        retry_prompt = system_prompt.format(prompt=prompt, context=compact_context or "（无额外上下文）")
        result = await call_llm(model=model, prompt=retry_prompt, stream=False,
                                max_tokens=context_budget.max_output_tokens,
                                api_key_token=api_key_token)
    response = result["choices"][0]["message"]["content"]
    tokens_used = format_tokens_usage(result)
    
    # 检查响应是否为空，避免保存空记录
    if not response or not response.strip():
        logger.warning(f"AI 生成响应为空 | user_id={user_id} | prompt={prompt[:50]}...")
        return {
            "response": "",
            "tokens_used": tokens_used,
            "conversation_id": None,
            "context_length": len(fitted_context),
            "context_usage": {
                "context_length": context_budget.context_length,
                "input_budget_tokens": context_budget.input_budget_tokens,
                "input_tokens_estimate": context_budget.input_tokens,
                "max_output_tokens": context_budget.max_output_tokens,
                "truncated": context_budget.truncated,
            },
            "error": "AI 生成响应为空，未保存历史记录"
        }
    
    new_conv_id = await save_history_to_db(
        db=db,
        user_id=int(user_id),
        conversation_id=conversation_id,
        prompt=prompt,
        response=response,
        thinking=None,
        metadata={"sources": sources, "warnings": stage_errors, "model": model, "search_depth": search_depth, "stages": {"search": did_search, "files": had_files}},
        commit=False
    )
    await _append_shared_chat_messages(db, int(user_id), new_conv_id, prompt, response)
    
    return {
        "response": response,
        "tokens_used": tokens_used,
        "conversation_id": new_conv_id,
        "context_length": len(fitted_context),
        "context_usage": {
            "context_length": context_budget.context_length,
            "input_budget_tokens": context_budget.input_budget_tokens,
            "input_tokens_estimate": context_budget.input_tokens,
            "max_output_tokens": context_budget.max_output_tokens,
            "truncated": context_budget.truncated,
        },
        "sources": sources,
        "search_depth": search_depth,
        "warnings": stage_errors,
    }


# API 端点
# -----------------------------

@router.post("/chat", summary="通用聊天（支持文件/图片理解）")
@router.post("/code", summary="通用问答兼容入口（支持文件/图片理解）", include_in_schema=False)
async def generate_code(
    request: Request,
    body: CodeRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    通用问答 API
    
    功能：
    - 生活问题、技术咨询、代码生成
    - 图片/文件理解（首次解析后缓存）
    - 会话历史压缩（自动携带上下文）
    - 联网搜索增强
    
    参数：
    - prompt: 问题或需求
    - model: 指定模型
    - stream: 是否流式输出
    - use_reasoning: 是否启用深度推理
    - enable_vision: 是否启用图片理解（兼容旧字段）
    - enable_search: 是否启用联网搜索
    - image_path: 图片路径（兼容旧字段）
    - files: 文件路径列表（新字段）
    - conversation_id: 会话 ID
    """
    user_id = token.get("sub")
    conversation_id = body.conversation_id
    
    # 构建文件列表：兼容旧字段 image_path + 新字段 files
    files_to_parse = []
    if body.image_path:
        files_to_parse.append(body.image_path)
    if body.files:
        for f in body.files:
            if f.server_path and f.server_path not in files_to_parse:
                files_to_parse.append(f.server_path)
    
    logger.info(f"通用问答请求 | user_id={user_id} | model={body.model} | stream={body.stream} | reasoning={body.use_reasoning}")
    
    # 自动选择模型（如果未指定）
    auto_model = body.model
    if not auto_model:
        auto_model = select_model_for_prompt(
            prompt=body.prompt,
            use_reasoning=body.use_reasoning,
            has_files=bool(files_to_parse)
        )
        logger.info(f"自动选择模型: {auto_model}")
    
    try:
        if body.stream:
            return StreamingResponse(
                stream_response(
                    user_id=user_id,
                    prompt=body.prompt,
                    model=auto_model,
                    conversation_id=conversation_id,
                    db=db,
                    request=request,
                    use_reasoning=body.use_reasoning,
                    enable_search=body.enable_search,
                    search_mode=body.search_mode,
                    search_depth=body.search_depth,
                    search_count=body.search_count or 5,
                    files_to_parse=files_to_parse if files_to_parse else None,
                    include_history=True,
                    resume_from=getattr(body, 'resume_id', None),
                    api_key_token=body.api_key_token
                ),
                media_type="text/event-stream",
                headers=CHAT_STREAM_HEADERS,
            )
        else:
            return await generate_response(
                user_id=user_id,
                prompt=body.prompt,
                model=auto_model,
                conversation_id=conversation_id,
                db=db,
                use_reasoning=body.use_reasoning,
                enable_search=body.enable_search,
                search_mode=body.search_mode,
                search_depth=body.search_depth,
                search_count=body.search_count or 5,
                files_to_parse=files_to_parse if files_to_parse else None,
                include_history=True,
                api_key_token=body.api_key_token
            )
    
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"请求失败 | user_id={user_id} | error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/code/history")
async def delete_code_history(
    conversation_ids: List[int] = Query(default=[], description="要删除的会话ID列表"),
    all: bool = Query(False, description="是否清除所有历史记录"),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    删除代码助手对话历史记录

    - **conversation_ids**: 要删除的会话ID列表
    - **all**: 是否清除所有历史记录（会忽略 conversation_ids）
    """
    user_id = token.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    if not all and not conversation_ids:
        raise HTTPException(status_code=400, detail="请提供要删除的会话ID或设置 all=true")

    logger.info(f"删除代码助手历史记录 | user_id={user_id} | all={all} | count={len(conversation_ids) if not all else 'all'}")

    try:
        if all:
            stmt = delete(History).where(History.user_id == user_id)
            result = await db.execute(stmt)
            shared_deleted = await _delete_shared_chat_data(db, int(user_id), delete_all=True)
            await db.commit()
            await invalidate_history_caches()
            deleted_count = result.rowcount
            logger.info(f"清除全部历史记录 | user_id={user_id} | deleted={deleted_count} | shared={shared_deleted}")
            return {"status": "deleted", "count": deleted_count, "shared_count": shared_deleted}
        else:
            stmt = delete(History).where(
                and_(
                    History.conversation_id.in_(conversation_ids),
                    History.user_id == user_id
                )
            )
            result = await db.execute(stmt)
            shared_deleted = await _delete_shared_chat_data(db, int(user_id), conversation_ids=conversation_ids)
            await db.commit()
            await invalidate_history_caches()
            deleted_count = result.rowcount
            logger.info(f"删除历史记录 | user_id={user_id} | deleted={deleted_count} | shared={shared_deleted}")
            return {"status": "deleted", "count": deleted_count, "shared_count": shared_deleted, "conversation_ids": conversation_ids}

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"删除历史记录异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除历史记录失败"
        )


@router.post("/code/resume", summary="恢复中断的代码生成")
async def resume_code_generation(
    request: Request,
    body: Dict[str, Any],
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """
    恢复中断的代码生成

    参数：
    - resume_id: 中断时返回的 resume_id
    - prompt: 新的或修改后的需求（可选，如果不传则使用原始 prompt）
    - model: 指定模型（可选）
    - stream: 是否流式输出（默认 true）
    - use_reasoning: 是否启用深度推理
    - enable_search: 是否启用联网搜索
    """
    user_id = token.get("sub")
    resume_id = body.get("resume_id")

    if not resume_id or resume_id not in _partial_response_cache:
        raise HTTPException(status_code=404, detail="找不到可恢复的部分响应（可能已过期）")

    cache = _partial_response_cache[resume_id]
    if cache.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权恢复此响应")

    new_prompt = body.get("prompt", "")
    auto_model = body.get("model", cache.get("model"))
    use_reasoning = body.get("use_reasoning", False)
    enable_search = body.get("enable_search", None)
    search_count = body.get("search_count", 5)

    # 构建恢复提示词
    if new_prompt:
        resume_prompt = new_prompt
        # 将部分响应作为上下文
        resume_prompt += f"\n\n--- 之前已生成的内容（供参考）---\n{cache['partial_response'][-1000:]}"
    else:
        resume_prompt = cache.get("prompt", "")

    logger.info(f"恢复代码生成 | user_id={user_id} | resume_id={resume_id} | has_new_prompt={bool(new_prompt)}")

    return StreamingResponse(
        stream_response(
            user_id=user_id,
            prompt=resume_prompt,
            model=auto_model,
            conversation_id=None,
            db=db,
            request=request,
            use_reasoning=use_reasoning,
            enable_search=enable_search,
            search_count=search_count,
            files_to_parse=None,
            include_history=False,
            resume_from=resume_id
        ),
        media_type="text/event-stream",
        headers=CHAT_STREAM_HEADERS,
    )


@router.get("/code/resume/{resume_id}", summary="获取部分响应内容")
async def get_partial_response(
    resume_id: str,
    token: dict = Depends(verify_token),
):
    """获取被中断的部分响应内容"""
    user_id = token.get("sub")

    if resume_id not in _partial_response_cache:
        raise HTTPException(status_code=404, detail="部分响应不存在或已过期")

    cache = _partial_response_cache[resume_id]
    if cache.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权访问")

    return {
        "resume_id": resume_id,
        "prompt": cache.get("prompt", ""),
        "partial_response": cache.get("partial_response", ""),
        "model": cache.get("model", ""),
        "timestamp": cache.get("timestamp", "")
    }
