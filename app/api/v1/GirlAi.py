# app/api/v1/GirlAi.py
"""
虚拟姬 AI 对话接口 - v3 增强版
特点：多角色系统、智能模型选择、情感陪伴优化、自定义角色、历史搜索、用户记忆
"""

import asyncio
import json
import logging
import time
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

from app.db.database import get_db
from app.schema.girl_request import GirlRequest, GirlResponse, HistoryRecord, HistoryResponse
from app.db.chat_history_service import ChatHistoryService
from app.services.girlai_state_adapter import append_conversation_turn
from app.models.chat_history import CustomCharacter, UserPreference
from app.utils import call_llm
from app.agent.models import DEFAULT_FAST_MODEL, DEFAULT_REASONING_MODEL
from app.utils.security import verify_token
from app.utils.aicloud.http_client import call_with_retry

from app.adapter import ModelAdapter

# 初始化日志
logger = logging.getLogger(__name__)
router = APIRouter()

# 并发限制
_max_concurrent_calls = asyncio.Semaphore(10)

# 异步锁
_model_adapters_lock = asyncio.Lock()

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
        "model": DEFAULT_REASONING_MODEL,
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
        "model": DEFAULT_FAST_MODEL,
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
        "model": DEFAULT_FAST_MODEL,
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
        "model": DEFAULT_REASONING_MODEL,
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
        "model": DEFAULT_REASONING_MODEL,
        "temperature": 0.85,
        "max_tokens": 200
    }
}

# 全局配置

DEFAULT_MODEL = DEFAULT_REASONING_MODEL
DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_TOKENS = 180
REQUEST_TIMEOUT = 30.0
MAX_HISTORY_MESSAGES = 10

# 角色 SVG 头像（内联，无需外部文件）
CHARACTER_AVATARS: Dict[str, str] = {
    "gentle": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#f9a8d4"/><stop offset="100%" style="stop-color:#f472b6"/></linearGradient></defs><circle cx="50" cy="50" r="48" fill="url(#g1)"/><circle cx="50" cy="42" r="18" fill="#fff" opacity="0.9"/><ellipse cx="50" cy="70" rx="22" ry="16" fill="#fff" opacity="0.9"/><circle cx="44" cy="40" r="2.5" fill="#333"/><circle cx="56" cy="40" r="2.5" fill="#333"/><path d="M45 48 Q50 52 55 48" stroke="#f472b6" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M32 30 Q38 18 50 18 Q62 18 68 30" stroke="#f472b6" stroke-width="3" fill="none"/></svg>''',
    "lively": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#fcd34d"/><stop offset="100%" style="stop-color:#f59e0b"/></linearGradient></defs><circle cx="50" cy="50" r="48" fill="url(#g2)"/><circle cx="50" cy="42" r="18" fill="#fff" opacity="0.9"/><ellipse cx="50" cy="70" rx="22" ry="16" fill="#fff" opacity="0.9"/><circle cx="44" cy="40" r="2.5" fill="#333"/><circle cx="56" cy="40" r="2.5" fill="#333"/><path d="M43 48 Q50 54 57 48" stroke="#f59e0b" stroke-width="2" fill="none" stroke-linecap="round"/><text x="30" y="25" font-size="12" fill="#f59e0b">★</text><text x="62" y="22" font-size="10" fill="#f59e0b">✦</text><path d="M30 32 Q40 20 50 22 Q60 20 70 32" stroke="#f59e0b" stroke-width="3" fill="none"/></svg>''',
    "tsundere": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g3" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#fca5a5"/><stop offset="100%" style="stop-color:#ef4444"/></linearGradient></defs><circle cx="50" cy="50" r="48" fill="url(#g3)"/><circle cx="50" cy="42" r="18" fill="#fff" opacity="0.9"/><ellipse cx="50" cy="70" rx="22" ry="16" fill="#fff" opacity="0.9"/><circle cx="44" cy="40" r="2.5" fill="#333"/><circle cx="56" cy="40" r="2.5" fill="#333"/><path d="M44 49 L50 47 L56 49" stroke="#ef4444" stroke-width="2" fill="none" stroke-linecap="round"/><ellipse cx="38" cy="46" rx="4" ry="2.5" fill="#fca5a5" opacity="0.6"/><ellipse cx="62" cy="46" rx="4" ry="2.5" fill="#fca5a5" opacity="0.6"/><path d="M32 30 Q40 22 50 24 Q60 22 68 30" stroke="#ef4444" stroke-width="3" fill="none"/></svg>''',
    "intellectual": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g4" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#a78bfa"/><stop offset="100%" style="stop-color:#7c3aed"/></linearGradient></defs><circle cx="50" cy="50" r="48" fill="url(#g4)"/><circle cx="50" cy="42" r="18" fill="#fff" opacity="0.9"/><ellipse cx="50" cy="70" rx="22" ry="16" fill="#fff" opacity="0.9"/><circle cx="44" cy="40" r="2.5" fill="#333"/><circle cx="56" cy="40" r="2.5" fill="#333"/><rect x="38" y="37" width="24" height="8" rx="4" fill="none" stroke="#7c3aed" stroke-width="1.5"/><path d="M46 48 Q50 50 54 48" stroke="#7c3aed" stroke-width="1.5" fill="none" stroke-linecap="round"/><path d="M32 30 Q40 18 50 20 Q60 18 68 30" stroke="#7c3aed" stroke-width="3" fill="none"/></svg>''',
    "companion": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g5" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#fda4af"/><stop offset="100%" style="stop-color:#e11d48"/></linearGradient></defs><circle cx="50" cy="50" r="48" fill="url(#g5)"/><circle cx="50" cy="42" r="18" fill="#fff" opacity="0.9"/><ellipse cx="50" cy="70" rx="22" ry="16" fill="#fff" opacity="0.9"/><circle cx="44" cy="40" r="2.5" fill="#333"/><circle cx="56" cy="40" r="2.5" fill="#333"/><path d="M44 48 Q50 53 56 48" stroke="#e11d48" stroke-width="2" fill="none" stroke-linecap="round"/><text x="62" y="30" font-size="14" fill="#e11d48">♥</text><path d="M32 30 Q40 20 50 22 Q60 20 68 30" stroke="#e11d48" stroke-width="3" fill="none"/></svg>''',
}

# Model Adapter 缓存
_model_adapters: Dict[str, ModelAdapter] = {}


async def _get_model_adapter(model_name: str) -> ModelAdapter:
    """获取或创建 Model Adapter（单例缓存，异步安全）"""
    async with _model_adapters_lock:
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
    user_name: Optional[str] = None,
    user_preferences: Optional[List[Dict[str, str]]] = None
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
    
    # 用户偏好记忆
    if user_preferences:
        parts.append("【你记住的用户信息】")
        for pref in user_preferences:
            parts.append(f"- {pref['key']}：{pref['value']}")
        parts.append("请在对话中自然地运用这些信息，让用户感到被记住和关心。")
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


# =============================================================================
# 用户偏好提取（异步，不阻塞响应）
# =============================================================================

# 偏好提取的关键词模式
_PREFERENCE_PATTERNS = {
    "name": [
        r"我叫(.{1,20})", r"我的名字是(.{1,20})", r"叫我(.{1,20})",
        r"我是(.{1,20})同学", r"我是(.{1,20})老师",
    ],
    "age": [
        r"我(\d{1,3})岁", r"我今年(\d{1,3})", r"我(\d{1,3})年出生",
    ],
    "hobby": [
        r"我喜欢(.{1,30})", r"我的爱好是(.{1,30})", r"我最爱(.{1,30})",
        r"我平时喜欢(.{1,30})", r"我经常(.{1,30})",
    ],
    "mood": [
        r"我(很开心|很高兴|很伤心|很难过|很累|很烦|压力大|焦虑|无聊)",
        r"今天(心情好|心情不好|心情差|很糟糕|很美好)",
    ],
    "work": [
        r"我在(.{1,30})工作", r"我是(.{1,20})职业", r"我的工作是(.{1,30})",
        r"我是做(.{1,20})的", r"我在(.{1,20})上班",
    ],
    "location": [
        r"我住在(.{1,30})", r"我在(.{1,20})住", r"我家在(.{1,30})",
        r"我是(.{1,20})人",
    ],
}


async def _extract_user_preferences(
    user_id: str,
    user_message: str,
    assistant_response: str,
    db: AsyncSession
):
    """从对话中异步提取用户偏好并保存"""
    import re

    try:
        extracted = {}
        for key, patterns in _PREFERENCE_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, user_message)
                if match:
                    value = match.group(1).strip()
                    if value and len(value) <= 100:
                        extracted[key] = value
                    break

        if not extracted:
            return

        # 保存到数据库（upsert 逻辑）
        from sqlalchemy import select, and_

        for key, value in extracted.items():
            stmt = select(UserPreference).where(
                and_(
                    UserPreference.user_id == int(user_id),
                    UserPreference.preference_key == key
                )
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.preference_value = value
                existing.updated_at = datetime.now()
            else:
                pref = UserPreference(
                    user_id=int(user_id),
                    preference_key=key,
                    preference_value=value,
                    confidence=80,
                    source="extracted"
                )
                db.add(pref)

        await db.commit()
        logger.debug(f"用户偏好提取完成 | user_id={user_id} | preferences={list(extracted.keys())}")

    except Exception as e:
        logger.debug(f"用户偏好提取失败（不影响主流程）| user_id={user_id} | error={e}")


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


@router.get("/GirlAi/characters/{character_id}/avatar")
async def get_character_avatar(character_id: str):
    """获取角色 SVG 头像"""
    svg = CHARACTER_AVATARS.get(character_id)
    if not svg:
        # 返回默认头像
        svg = CHARACTER_AVATARS["gentle"]
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/GirlAi/history/search")
async def search_history(
    q: str = Query(..., min_length=1, max_length=100, description="搜索关键词"),
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
    limit: Optional[int] = 20,
    offset: Optional[int] = 0
):
    """搜索对话历史"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    from sqlalchemy import select, and_
    from app.models.chat_history import ChatHistory

    stmt = (
        select(ChatHistory)
        .where(
            and_(
                ChatHistory.user_id == int(user_id),
                ChatHistory.content.ilike(f"%{q}%"),
                ChatHistory.is_archived == False
            )
        )
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    records = result.scalars().all()

    return {
        "records": [
            {
                "id": str(r.id),
                "role": r.role,
                "content": r.content,
                "model": r.model,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ],
        "total": len(records),
        "query": q
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

    async with _max_concurrent_calls:
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

            # 加载用户偏好
            user_preferences = []
            try:
                from sqlalchemy import select
                pref_stmt = (
                    select(UserPreference)
                    .where(UserPreference.user_id == int(user_id))
                    .order_by(UserPreference.confidence.desc())
                    .limit(10)
                )
                pref_result = await db.execute(pref_stmt)
                prefs = pref_result.scalars().all()
                user_preferences = [
                    {"key": p.preference_key, "value": p.preference_value}
                    for p in prefs
                ]
            except Exception as e:
                logger.debug(f"加载用户偏好失败: {e}")

            # 构建情感优化 Prompt
            full_prompt = _build_emotion_prompt(
                character=character,
                user_prompt=body.prompt,
                recent_messages=recent_messages,
                user_name=None,
                user_preferences=user_preferences
            )

            logger.debug(f"Prompt 构建完成 | user_id={user_id} | prompt_length={len(full_prompt)}")
            logger.info(f"调用 AI 服务 | user_id={user_id} | model={character['model']}")

            # 使用 Model Adapter 调用 AI 服务
            adapter = await _get_model_adapter(character['model'])
            
            ai_start_time = time.time()
            
            # 添加重试机制
            async def llm_call():
                return await asyncio.wait_for(
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
            
            response = await call_with_retry(llm_call, max_retries=3)
            
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
            await append_conversation_turn(
                db,
                int(user_id),
                body.prompt,
                ai_content,
                model=character['model'],
                character_id=getattr(body, 'character_id', None),
            )
            await db.commit()
            save_duration = time.time() - save_start_time
            logger.debug(f"对话记录保存完成 | user_id={user_id} | duration={save_duration:.2f}s")

            # 异步提取用户偏好（不阻塞响应）
            asyncio.create_task(
                _extract_user_preferences(user_id, body.prompt, ai_content, db)
            )

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


# =============================================================================
# 自定义角色 CRUD
# =============================================================================

@router.get("/GirlAi/characters/custom/list")
async def list_custom_characters(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的自定义角色列表"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    from sqlalchemy import select
    stmt = (
        select(CustomCharacter)
        .where(CustomCharacter.user_id == int(user_id))
        .order_by(CustomCharacter.created_at.desc())
    )
    result = await db.execute(stmt)
    characters = result.scalars().all()

    return {
        "characters": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "personality": c.personality,
                "speaking_style": c.speaking_style,
                "greetings": json.loads(c.greetings) if c.greetings else [],
                "tags": json.loads(c.tags) if c.tags else [],
                "model": c.model,
                "temperature": c.temperature / 100.0,
                "max_tokens": c.max_tokens,
                "avatar_color": c.avatar_color,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in characters
        ],
        "total": len(characters)
    }


@router.post("/GirlAi/characters/custom")
async def create_custom_character(
    body: Dict[str, Any],
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """创建自定义角色"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    # 验证必填字段
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="角色名称不能为空")
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="角色名称过长")

    # 检查用户角色数量限制（最多 10 个）
    from sqlalchemy import select, func as sql_func
    count_stmt = (
        select(sql_func.count())
        .select_from(CustomCharacter)
        .where(CustomCharacter.user_id == int(user_id))
    )
    count_result = await db.execute(count_stmt)
    if count_result.scalar() >= 10:
        raise HTTPException(status_code=400, detail="自定义角色数量已达上限（10个）")

    character = CustomCharacter(
        user_id=int(user_id),
        name=name,
        description=body.get("description", "")[:200],
        personality=body.get("personality", "")[:200],
        speaking_style=body.get("speaking_style", "")[:200],
        greetings=json.dumps(body.get("greetings", []), ensure_ascii=False),
        tags=json.dumps(body.get("tags", []), ensure_ascii=False),
        model=body.get("model", DEFAULT_MODEL),
        temperature=int(float(body.get("temperature", 0.8)) * 100),
        max_tokens=int(body.get("max_tokens", 180)),
        avatar_color=body.get("avatar_color", "#667eea")[:20],
    )

    db.add(character)
    await db.commit()
    await db.refresh(character)

    return {
        "id": str(character.id),
        "name": character.name,
        "message": "角色创建成功"
    }


@router.delete("/GirlAi/characters/custom/{character_id}")
async def delete_custom_character(
    character_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除自定义角色"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    from sqlalchemy import select, and_
    stmt = select(CustomCharacter).where(
        and_(
            CustomCharacter.id == character_id,
            CustomCharacter.user_id == int(user_id)
        )
    )
    result = await db.execute(stmt)
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    await db.delete(character)
    await db.commit()

    return {"status": "deleted", "id": character_id}


# =============================================================================
# 用户偏好记忆
# =============================================================================

@router.get("/GirlAi/preferences")
async def get_user_preferences(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """获取用户偏好记忆"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    from sqlalchemy import select
    stmt = (
        select(UserPreference)
        .where(UserPreference.user_id == int(user_id))
        .order_by(UserPreference.updated_at.desc())
    )
    result = await db.execute(stmt)
    preferences = result.scalars().all()

    return {
        "preferences": [
            {
                "id": str(p.id),
                "key": p.preference_key,
                "value": p.preference_value,
                "confidence": p.confidence,
                "source": p.source,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in preferences
        ]
    }


@router.delete("/GirlAi/preferences/{preference_id}")
async def delete_user_preference(
    preference_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """删除用户偏好"""
    user_id = token.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的用户令牌")

    from sqlalchemy import select, and_
    stmt = select(UserPreference).where(
        and_(
            UserPreference.id == preference_id,
            UserPreference.user_id == int(user_id)
        )
    )
    result = await db.execute(stmt)
    pref = result.scalar_one_or_none()

    if not pref:
        raise HTTPException(status_code=404, detail="偏好记录不存在")

    await db.delete(pref)
    await db.commit()

    return {"status": "deleted", "id": preference_id}


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
