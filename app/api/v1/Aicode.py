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
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, Tuple, Optional, List
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schema.codeRequest import CodeRequest
from app.utils import call_llm
from app.utils.web_search import FreeWebSearch
from fastapi.responses import StreamingResponse
from app.utils.security import verify_token
from app.db.add_history import save_history_to_db
from app.utils.vision import analyze_image
from app.models.file import File
from app.models.history import History
from sqlalchemy import select, delete, and_
from sqlalchemy.exc import SQLAlchemyError

from app.utils.json_parser import RobustJSONParser

# 初始化日志
logger = logging.getLogger(__name__)
router = APIRouter()
_parser = RobustJSONParser(strict_mode=False)

# 部分响应缓存 {task_id: {"prompt": ..., "partial_response": ..., "model": ..., "timestamp": ...}}
_partial_response_cache: Dict[str, dict] = {}
_PARTIAL_TTL = 300  # 5 分钟过期


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

def ai_decide_search(prompt: str) -> bool:
    """
    AI 自主判断是否需要网络搜索
    
    判断逻辑：
    1. 需要搜索的场景：时效性信息、新闻动态、实时数据、最新信息
    2. 不需要搜索的场景：代码生成、知识讲解、文本处理、数学计算
    
    Args:
        prompt: 用户问题
        
    Returns:
        True=需要搜索，False=不需要搜索
    """
    prompt_lower = prompt.lower()
    
    # 需要搜索的关键词（时效性、动态信息）
    search_triggers = [
        # 时间相关
        "最新", "最近", "新闻", "今天", "昨天", "本周", "本月", "今年", "明年",
        "2024", "2025", "2026", "2027",
        
        # 动态事件
        "发布会", "更新", "版本", "发布", "上线", "上线时间", "发售", "官宣",
        "价格", "股价", "汇率", "排名", "排行榜", "榜单",
        "天气", "疫情", "政策", "法规", "新规",
        "销量", "用户数", "市场份额",
        
        # 英文查询
        "latest", "recent", "news", "today", "this week", "this month",
        "release date", "price", "update", "version",
        "who is", "what is the current", "current status"
    ]
    
    # 不需要搜索的关键词（静态知识、代码生成）
    no_search_triggers = [
        # 代码生成
        "代码", "编程", "function", "class", "def ", "import", "const ",
        "写一个", "生成代码", "实现一个", "创建一个", "编写",
        "api 接口", "endpoint", "route", "controller",
        
        # 知识讲解
        "解释", "原理", "概念", "是什么意思", "什么是", "定义",
        "教学", "教程", "学习", "入门", "指南",
        "为什么", "如何实现", "怎么写",
        
        # 文本处理
        "翻译", "润色", "写作", "改写", "总结", "摘要",
        
        # 数学计算
        "计算", "等于", "公式", "求解", "积分", "微分"
    ]
    
    # 优先匹配需要搜索的
    for keyword in search_triggers:
        if keyword in prompt_lower:
            return True
    
    # 匹配不需要搜索的
    for keyword in no_search_triggers:
        if keyword in prompt_lower:
            return False
    
    # 默认不搜索
    return False


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
        return "THUDM/GLM-4.1V-9B-Thinking"
    if use_reasoning:
        return "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"

    analysis_keywords = ['分析', '解释', '原理', '为什么', '比较', '区别',
                         '是什么', '优缺点', '如何理解', '详细说明']
    if any(kw in prompt.lower() for kw in analysis_keywords):
        return "THUDM/GLM-Z1-9B-0414"

    return "Qwen/Qwen3-8B"


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
            # 其他文件：返回文件路径（由主模型处理）
            metadata = {
                "type": "file",
                "filename": file_record.filename,
                "path": str(verified_path)
            }
            
            return f"[文件：{file_record.filename}]", metadata
            
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
    files_to_parse: Optional[List[str]] = None,
    include_history: bool = True
) -> str:
    """
    构建上下文：会话历史 + 文件解析 + 联网搜索
    """
    context_parts = []
    
    if include_history and conversation_id:
        history_context = await compress_conversation_history(db, user_id, conversation_id)
        if history_context:
            context_parts.append(history_context)
    
    if files_to_parse:
        for file_path in files_to_parse:
            try:
                parsed_content, metadata = await get_or_parse_file(
                    file_path, user_id, conversation_id, db
                )
                context_parts.append(f"\n[参考文件：{metadata['filename']}]\n{parsed_content}\n")
            except HTTPException as e:
                logger.warning(f"文件访问被拒绝，跳过 | file={file_path} | status={e.status_code} | detail={e.detail}")
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                logger.warning(f"文件解析失败，跳过 | file={file_path} | error={str(e)}")
    
    should_search = False
    
    if enable_search is False:
        logger.info(f"用户禁止搜索 | prompt={prompt[:50]}...")
    else:
        ai_needs_search = ai_decide_search(prompt)
        
        if enable_search is True:
            should_search = ai_needs_search
            log_msg = "执行搜索" if should_search else "跳过搜索"
            logger.info(f"用户允许 + AI 判断{log_msg} | prompt={prompt[:50]}...")
        else:
            should_search = ai_needs_search
            log_msg = "执行搜索" if should_search else "跳过搜索"
            logger.info(f"用户未指定 + AI 判断{log_msg} | prompt={prompt[:50]}...")
    
    if should_search:
        try:
            search = FreeWebSearch()
            search_text = await search.search_and_format(query=prompt, count=search_count)
            if search_text:
                context_parts.append(f"\n[网络搜索结果]\n{search_text}\n")
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            logger.warning(f"搜索失败，继续执行 | error={str(e)}")
    
    return "\n".join(context_parts) if context_parts else ""


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
    api_key_token: str = None
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

    full_context = await _build_context(
        user_id=int(user_id),
        prompt=prompt,
        db=db,
        conversation_id=int(conversation_id) if conversation_id else None,
        enable_search=enable_search,
        search_count=search_count,
        files_to_parse=files_to_parse,
        include_history=include_history
    )

    system_prompt = _select_prompt_template(prompt, use_reasoning)
    final_prompt = system_prompt.format(prompt=prompt, context=full_context or "（无额外上下文）")

    # 如果有前缀文本，追加到提示词中
    if prefix_text:
        final_prompt += f"\n\n注意：之前已生成部分内容，请在此基础上继续：\n{prefix_text[-500:]}"

    logger.info(f"开始流式生成 | user_id={user_id} | model={model}")

    response_parts = []

    try:
        result_gen = await call_llm(model=model, prompt=final_prompt, stream=True, cancel_event=cancel_event, api_key_token=api_key_token)

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
            thinking=None
        )
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
    api_key_token: str = None
) -> Dict:
    """
    通用非流式响应
    """
    full_context = await _build_context(
        user_id=int(user_id),
        prompt=prompt,
        db=db,
        conversation_id=int(conversation_id) if conversation_id else None,
        enable_search=enable_search,
        search_count=search_count,
        files_to_parse=files_to_parse,
        include_history=include_history
    )
    
    system_prompt = _select_prompt_template(prompt, use_reasoning)
    final_prompt = system_prompt.format(prompt=prompt, context=full_context or "（无额外上下文）")
    
    logger.info(f"执行非流式请求 | user_id={user_id} | model={model}")
    
    result = await call_llm(model=model, prompt=final_prompt, stream=False, api_key_token=api_key_token)
    response = result["choices"][0]["message"]["content"]
    tokens_used = format_tokens_usage(result)
    
    # 检查响应是否为空，避免保存空记录
    if not response or not response.strip():
        logger.warning(f"AI 生成响应为空 | user_id={user_id} | prompt={prompt[:50]}...")
        return {
            "response": "",
            "tokens_used": tokens_used,
            "conversation_id": None,
            "context_length": len(full_context),
            "error": "AI 生成响应为空，未保存历史记录"
        }
    
    new_conv_id = await save_history_to_db(
        db=db,
        user_id=int(user_id),
        conversation_id=conversation_id,
        prompt=prompt,
        response=response,
        thinking=None
    )
    
    return {
        "response": response,
        "tokens_used": tokens_used,
        "conversation_id": new_conv_id,
        "context_length": len(full_context)
    }


# API 端点
# -----------------------------

@router.post("/code", summary="通用问答（支持文件/图片理解）")
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
                    search_count=body.search_count or 5,
                    files_to_parse=files_to_parse if files_to_parse else None,
                    include_history=True,
                    resume_from=getattr(body, 'resume_id', None),
                    api_key_token=body.api_key_token
                ),
                media_type="text/plain"
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
            await db.commit()
            deleted_count = result.rowcount
            logger.info(f"清除全部历史记录 | user_id={user_id} | deleted={deleted_count}")
            return {"status": "deleted", "count": deleted_count}
        else:
            stmt = delete(History).where(
                and_(
                    History.conversation_id.in_(conversation_ids),
                    History.user_id == user_id
                )
            )
            result = await db.execute(stmt)
            await db.commit()
            deleted_count = result.rowcount
            logger.info(f"删除历史记录 | user_id={user_id} | deleted={deleted_count}")
            return {"status": "deleted", "count": deleted_count, "conversation_ids": conversation_ids}

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
        media_type="text/plain"
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
