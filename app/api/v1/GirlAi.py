# app/api/v1/GirlAi.py
"""
虚拟姬 AI 对话接口 - v2 增强版
特点：多角色系统、智能模型选择、情感陪伴优化
"""

import asyncio
import logging
import threading
import time
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import get_db
from app.schema.girl_request import GirlRequest, GirlResponse, HistoryRecord, HistoryResponse
from app.db.chat_history_service import ChatHistoryService
from app.utils import call_llm
from app.utils.security import verify_token

# import sys (adapter module moved to app.adapter)
# sys.path removed - using app.adapter
from app.adapter import ModelAdapter

# 初始化日志
logger = logging.getLogger(__name__)
router = APIRouter()

# 角色配置

CHARACTER_PROFILES: Dict[str, Dict[str, Any]] = {
    "gentle": {
        "id": "gentle",
        "name": "温柔姐姐",
        "description": "温柔体贴的大姐姐，总是耐心倾听你的烦恼",
        "personality": "温柔、体贴、善解人意、成熟",
        "speaking_style": "语气温柔，常用「呢」「哦」「呀」等语气词，喜欢用~符号",
        "greetings": [
            "亲爱的，今天过得怎么样呀？~",
            "欢迎回来~ 我一直在等你呢",
            "看到你来了真开心，想和我聊聊天吗？~"
        ],
        "tags": ["温柔", "治愈", "姐姐", "贴心"],
        "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        "temperature": 0.8,
        "max_tokens": 180
    },
    "lively": {
        "id": "lively",
        "name": "元气少女",
        "description": "活泼开朗的元气少女，充满活力和正能量",
        "personality": "活泼、开朗、乐观、元气满满",
        "speaking_style": "语气轻快，常用感叹号，大量使用 emoji 和颜文字",
        "greetings": [
            "呀吼~！今天也要元气满满哦！(≧∇≦) ﾉ",
            "哇！你来啦！我等你好久啦~✨",
            "哈喽哈喽~ 今天有什么有趣的事情吗？٩(◕‿◕) ﾉ"
        ],
        "tags": ["元气", "活泼", "少女", "可爱"],
        "model": "Qwen/Qwen3.5-4B",
        "temperature": 0.9,
        "max_tokens": 150
    },
    "tsundere": {
        "id": "tsundere",
        "name": "傲娇妹妹",
        "description": "典型的傲娇性格，嘴硬心软，其实很在乎你",
        "personality": "傲娇、别扭、嘴硬心软、容易害羞",
        "speaking_style": "口是心非，常用「才不是」「哼」「笨蛋」等词汇",
        "greetings": [
            "哼、哼！才、才不是特意等你呢！(￣^￣)",
            "哦…你来了啊…我、我只是刚好路过而已！",
            "…笨蛋，下次别让我等这么久啦！"
        ],
        "tags": ["傲娇", "妹妹", "别扭", "可爱"],
        "model": "Qwen/Qwen3.5-4B",
        "temperature": 0.85,
        "max_tokens": 160
    },
    "intellectual": {
        "id": "intellectual",
        "name": "知性学姐",
        "description": "知性优雅的学霸学姐，博学多才又不失温柔",
        "personality": "知性、理性、博学、优雅",
        "speaking_style": "语气温和，措辞文雅，偶尔引用名言或知识点",
        "greetings": [
            "你好呀，今天也是求知的一天呢",
            "欢迎来到知识的殿堂，有什么我可以帮你的吗？",
            "又见面了，最近在读什么有趣的书吗？"
        ],
        "tags": ["知性", "学霸", "优雅", "理性"],
        "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        "temperature": 0.7,
        "max_tokens": 200
    },
    "companion": {
        "id": "companion",
        "name": "专属伴侣",
        "description": "贴心的专属伴侣，只属于你的 AI 恋人",
        "personality": "专一、深情、贴心、浪漫",
        "speaking_style": "语气温柔亲昵，常用爱称，表达爱意",
        "greetings": [
            "亲爱的~ 我好想你呀！❤",
            "你终于来啦~ 我一直在想你呢 (´｡• ᵕ •｡`)",
            "最喜欢你啦~ 今天也想和你在一起 ❤"
        ],
        "tags": ["伴侣", "恋人", "专一", "浪漫"],
        "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        "temperature": 0.85,
        "max_tokens": 200
    }
}

# 全局配置

DEFAULT_MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_TOKENS = 180
REQUEST_TIMEOUT = 30.0
MAX_HISTORY_MESSAGES = 10

# Model Adapter 缓存
_model_adapters: Dict[str, ModelAdapter] = {}
_model_adapters_lock = threading.Lock()


def _get_model_adapter(model_name: str) -> ModelAdapter:
    """获取或创建 Model Adapter（单例缓存，线程安全）"""
    with _model_adapters_lock:
        if model_name not in _model_adapters:
            _model_adapters[model_name] = ModelAdapter(model_name)
            logger.debug(f"Model Adapter 已创建：{model_name}")
        return _model_adapters[model_name]


def _get_character(character_id: str) -> Dict[str, Any]:
    """获取角色配置"""
    return CHARACTER_PROFILES.get(character_id, CHARACTER_PROFILES["gentle"])


def _build_emotion_prompt(
    character: Dict[str, Any],
    user_prompt: str,
    recent_messages: List[Dict[str, str]],
    user_name: Optional[str] = None
) -> str:
    """构建情感陪伴优化的 Prompt"""
    parts = []
    
    # 角色设定
    parts.append(f"你是{character['name']}，{character['description']}")
    parts.append(f"性格：{character['personality']}")
    parts.append(f"说话风格：{character['speaking_style']}")
    parts.append("请始终保持角色设定，给予温暖、贴心的回应。")
    parts.append("")
    
    # 对话示例（Few-shot）
    parts.append("【对话示例】")
    for greeting in character["greetings"][:2]:
        parts.append(f"你：{greeting}")
    parts.append("")
    
    # 对话历史
    if recent_messages:
        parts.append("【对话历史】")
        for msg in recent_messages[-6:]:
            role = "用户" if msg["role"] == "user" else character["name"]
            parts.append(f"{role}: {msg['content']}")
        parts.append("")
    
    # 用户称呼
    if user_name:
        parts.append(f"用户称呼：{user_name}")
        parts.append("")
    
    # 当前输入
    parts.append("【当前对话】")
    parts.append(f"用户：{user_prompt}")
    parts.append(f"{character['name']}:")
    
    full_prompt = "\n".join(parts)
    logger.debug(f"Prompt 构建完成，长度：{len(full_prompt)} 字符")
    
    return full_prompt


def _clean_response(content: str, character_name: str) -> str:
    """清理 AI 响应（移除角色名前缀等）"""
    import re
    
    patterns = [
        rf"^{character_name}:\s*",
        rf"^【[^】]*】\s*",
        rf"^\([^)]*\)\s*",
        r'^":\s*'
    ]
    
    for pattern in patterns:
        content = re.sub(pattern, "", content, flags=re.IGNORECASE)
    
    return content.strip()


# API 接口

@router.get("/GirlAi/characters")
async def get_characters(token: dict = Depends(verify_token)):
    """获取所有可用角色列表"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")
    
    characters = [
        {
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "tags": c["tags"],
            "speaking_style": c["speaking_style"]
        }
        for c in CHARACTER_PROFILES.values()
    ]
    
    return {
        "characters": characters,
        "total": len(characters)
    }


@router.post(
    "/GirlAi",
    summary="虚拟姬 AI 对话（增强版）",
    response_model=GirlResponse,
    status_code=status.HTTP_200_OK
)
async def generate_message(
    body: GirlRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
) -> GirlResponse:
    """
    虚拟姬 AI 对话接口
    
    **增强功能:**
    - 新增 character_id 参数选择角色（支持：gentle/lively/tsundere/intellectual/companion）
    - 智能模型选择（根据角色自动选择最优模型）
    - 情感陪伴优化的 Prompt
    - Model Adapter 多模型支持
    """
    user_id = token.get("sub")

    if not user_id:
        logger.warning(f"虚拟姬请求失败：无效的用户令牌 | user_id={user_id}")
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    # 获取角色配置
    character = _get_character(getattr(body, 'character_id', 'gentle') or 'gentle')
    logger.info(
        f"虚拟姬对话请求 | user_id={user_id} | 角色={character['name']} | "
        f"模型={character['model']} | prompt_preview={body.prompt[:50] if body.prompt else ''}..."
    )

    start_time = time.time()

    try:
        # 快速加载上下文
        history_service = ChatHistoryService(db)

        logger.debug(f"加载对话上下文 | user_id={user_id} | max_messages={MAX_HISTORY_MESSAGES}")
        recent_messages, history_summary = await history_service.get_lightweight_context(
            user_id,
            max_messages=MAX_HISTORY_MESSAGES
        )

        context_load_time = time.time() - start_time
        logger.debug(
            f"上下文加载完成 | user_id={user_id} | duration={context_load_time:.2f}s | messages_loaded={len(recent_messages)}"
        )

        # 构建情感优化 Prompt
        full_prompt = _build_emotion_prompt(
            character=character,
            user_prompt=body.prompt,
            recent_messages=recent_messages,
            user_name=None
        )

        logger.debug(f"Prompt 构建完成 | user_id={user_id} | prompt_length={len(full_prompt)}")
        logger.info(f"调用 AI 服务 | user_id={user_id} | model={character['model']}")

        # 使用 Model Adapter 调用 AI 服务
        adapter = _get_model_adapter(character['model'])
        
        ai_start_time = time.time()
        response = await asyncio.wait_for(
            call_llm(
                model=character['model'],
                prompt=full_prompt,
                system_prompt="",
                stream=False,
                max_tokens=getattr(body, 'max_tokens', None) or character['max_tokens'],
                thinking_budget=64,
                temperature=getattr(body, 'temperature', None) or character['temperature']
            ),
            timeout=REQUEST_TIMEOUT
        )
        ai_duration = time.time() - ai_start_time

        ai_content = response["choices"][0]["message"]["content"]
        tokens_used = response["usage"]["total_tokens"]
        
        # 清理响应
        ai_content = _clean_response(ai_content, character['name'])

        logger.info(f"AI 响应成功 | user_id={user_id} | tokens_used={tokens_used} | duration={ai_duration:.2f}s")
        logger.debug(f"AI 响应内容 | user_id={user_id} | content_length={len(ai_content)}")

        # 保存对话记录
        save_start_time = time.time()
        await history_service.save_conversation_turn(
            user_id=user_id,
            user_content=body.prompt,
            assistant_content=ai_content,
            model=character['model'],
            tokens_used=tokens_used
        )
        save_duration = time.time() - save_start_time

        logger.debug(f"对话记录保存完成 | user_id={user_id} | duration={save_duration:.2f}s")

        total_duration = time.time() - start_time
        logger.info(f"虚拟姬请求完成 | user_id={user_id} | 角色={character['name']} | total_duration={total_duration:.2f}s")

        return GirlResponse(
            message=ai_content,
            model=character['model'],
            tokens_used=tokens_used
        )

    except asyncio.TimeoutError:
        logger.error(f"虚拟姬请求超时 | user_id={user_id} | timeout={REQUEST_TIMEOUT}s")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI 响应超时，请稍后重试"
        )

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"虚拟姬请求异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成失败：{str(e)}"
        )


@router.get("/GirlAi/history")
async def get_history(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
    limit: Optional[int] = 20,
    offset: Optional[int] = 0
):
    """获取对话历史记录"""
    user_id = token.get("sub")

    if not user_id:
        logger.warning(f"获取历史记录失败：无效的用户令牌 | user_id={user_id}")
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    logger.info(f"查询虚拟姬历史记录 | user_id={user_id} | limit={limit} | offset={offset}")

    try:
        history_service = ChatHistoryService(db)

        query_start_time = time.time()
        records, total = await history_service.get_user_history(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        query_duration = time.time() - query_start_time

        logger.debug(
            f"历史记录查询完成 | user_id={user_id} | total={total} | returned={len(records)} | duration={query_duration:.2f}s"
        )

        history_records = [
            HistoryRecord(
                id=str(record.id),
                role=record.role,
                content=record.content,
                model=record.model,
                token_usage=record.token_usage,
                created_at=record.created_at
            )
            for record in records
        ]

        has_more = offset + len(records) < total
        logger.info(f"返回历史记录 | user_id={user_id} | records_count={len(history_records)} | has_more={has_more}")

        return HistoryResponse(
            total=total,
            records=history_records,
            has_more=has_more
        )

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"获取历史记录异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取历史记录失败"
        )


@router.delete("/GirlAi/history")
async def delete_history(
    record_ids: List[str] = Query(..., description="要删除的记录ID列表"),
    all: bool = Query(False, description="是否清除所有历史记录"),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    删除虚拟姬对话历史记录

    - **record_ids**: 要删除的记录ID列表
    - **all**: 是否清除所有历史记录（会忽略 record_ids）
    """
    user_id = token.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    logger.info(f"删除虚拟姬历史记录 | user_id={user_id} | all={all} | count={len(record_ids) if not all else 'all'}")

    try:
        history_service = ChatHistoryService(db)

        if all:
            deleted_count = await history_service.clear_user_history(user_id)
            logger.info(f"清除全部历史记录 | user_id={user_id} | deleted={deleted_count}")
            return {"status": "deleted", "count": deleted_count}
        else:
            deleted_count = await history_service.delete_records(record_ids, user_id)
            logger.info(f"删除历史记录 | user_id={user_id} | deleted={deleted_count}")
            return {"status": "deleted", "count": deleted_count, "ids": record_ids}

    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"删除历史记录异常 | user_id={user_id} | error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除历史记录失败"
        )
