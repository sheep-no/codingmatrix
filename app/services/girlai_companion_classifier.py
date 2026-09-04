"""Emotion, work-intent, and deterministic response policy for GirlAI."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional

from app.core.config import settings
from app.schema.girl_companion import CompanionTurn, EmotionState, IntentState
from app.services.girlai_companion_model import CompanionModelService
from app.utils import call_llm

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)

_EMOTION_ALIASES = {
    "neutral": "neutral",
    "calm": "neutral",
    "平静": "neutral",
    "中性": "neutral",
    "happy": "happy",
    "joy": "happy",
    "开心": "happy",
    "高兴": "happy",
    "sad": "sad",
    "悲伤": "sad",
    "难过": "sad",
    "anxious": "anxious",
    "anxiety": "anxious",
    "焦虑": "anxious",
    "stressed": "stressed",
    "stress": "stressed",
    "压力": "stressed",
    "tired": "tired",
    "fatigued": "tired",
    "疲惫": "tired",
    "累": "tired",
    "angry": "angry",
    "anger": "angry",
    "生气": "angry",
    "愤怒": "angry",
    "overwhelmed": "overwhelmed",
    "不堪重负": "overwhelmed",
    "崩溃": "overwhelmed",
    "focused": "focused",
    "专注": "focused",
}

_INTENT_ALIASES = {
    "unknown": "unknown",
    "未知": "unknown",
    "chat": "chat",
    "conversation": "chat",
    "闲聊": "chat",
    "acknowledge": "acknowledge",
    "confirmation": "acknowledge",
    "确认": "acknowledge",
    "planning": "task_planning",
    "task_planning": "task_planning",
    "任务规划": "task_planning",
    "task_execution": "task_execution",
    "execution": "task_execution",
    "执行任务": "task_execution",
    "task_review": "task_review",
    "review": "task_review",
    "复盘": "task_review",
    "task_blocked": "task_blocked",
    "blocked": "task_blocked",
    "遇到阻塞": "task_blocked",
    "rest_request": "rest_request",
    "rest": "rest_request",
    "休息": "rest_request",
    "help_request": "help_request",
    "help": "help_request",
    "求助": "help_request",
    "remember_preference": "remember_preference",
    "memory": "remember_preference",
    "记住偏好": "remember_preference",
}

_CARE_EMOTIONS = {"sad", "anxious", "stressed", "tired", "angry", "overwhelmed"}
_CARE_DESCRIPTIONS = {
    "sad": "有些难过",
    "anxious": "有些焦虑",
    "stressed": "承受着压力",
    "tired": "有些疲惫",
    "angry": "有些生气",
    "overwhelmed": "感到事情压得太多",
}

LlmCaller = Callable[..., Awaitable[Mapping[str, Any]]]


@dataclass
class ClassificationResult:
    emotion: EmotionState = field(
        default_factory=lambda: EmotionState(low_confidence=True)
    )
    intent: IntentState = field(
        default_factory=lambda: IntentState(low_confidence=True)
    )
    model: Optional[str] = None
    calls: int = 0
    fallback_used: bool = False
    fallback_history: list[str] = field(default_factory=list)
    degraded_capabilities: list[str] = field(default_factory=list)
    parse_failed: bool = False


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def _state_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        return {"label": value}
    return {}


def normalize_emotion(
    value: Any,
    threshold: Optional[float] = None,
) -> EmotionState:
    payload = _state_payload(value)
    raw_label = str(payload.get("label") or "neutral").strip().lower()
    normalized = _EMOTION_ALIASES.get(raw_label, "neutral")
    confidence = _number(payload.get("confidence"))
    configured_threshold = (
        settings.GIRLAI_EMOTION_CONFIDENCE_THRESHOLD if threshold is None else threshold
    )
    low_confidence = confidence < configured_threshold or raw_label not in _EMOTION_ALIASES
    return EmotionState(
        label="neutral" if low_confidence else normalized,
        intensity=_number(payload.get("intensity")),
        confidence=confidence,
        raw_label=raw_label if raw_label != normalized or low_confidence else None,
        low_confidence=low_confidence,
    )


def normalize_intent(
    value: Any,
    threshold: Optional[float] = None,
) -> IntentState:
    payload = _state_payload(value)
    raw_label = str(payload.get("label") or "unknown").strip().lower()
    normalized = _INTENT_ALIASES.get(raw_label, "unknown")
    confidence = _number(payload.get("confidence"))
    configured_threshold = (
        settings.GIRLAI_INTENT_CONFIDENCE_THRESHOLD if threshold is None else threshold
    )
    low_confidence = confidence < configured_threshold or raw_label not in _INTENT_ALIASES
    return IntentState(
        label="unknown" if low_confidence else normalized,
        confidence=confidence,
        raw_label=raw_label if raw_label != normalized or low_confidence else None,
        low_confidence=low_confidence,
    )


def parse_classification_response(response: Mapping[str, Any]) -> ClassificationResult:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("分类模型返回了无效响应") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("分类模型返回了空响应")
    candidate = content.strip()
    fenced = _JSON_FENCE_RE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError("分类模型返回了无效 JSON") from error
    if not isinstance(payload, dict) or "emotion" not in payload or "intent" not in payload:
        raise ValueError("分类模型缺少情绪或意图字段")
    return ClassificationResult(
        emotion=normalize_emotion(payload["emotion"]),
        intent=normalize_intent(payload["intent"]),
    )


async def classify_companion_input(
    user_prompt: str,
    *,
    model_service: Optional[CompanionModelService] = None,
    llm_caller: Optional[LlmCaller] = None,
) -> ClassificationResult:
    service = model_service or CompanionModelService()
    try:
        models = await service.select_models()
    except Exception as error:
        logger.warning("GirlAI 分类模型选择失败 | error_type=%s", type(error).__name__)
        return ClassificationResult(
            degraded_capabilities=["emotion_classification", "intent_classification"],
            parse_failed=True,
        )
    primary = models["classification"]
    candidates = list(dict.fromkeys([primary, models.get("fallback")]))
    caller = llm_caller or call_llm
    classification_prompt = (
        "分析下面的用户输入，只返回 JSON。"
        "emotion 必须包含 label、intensity、confidence；"
        "intent 必须包含 label、confidence。"
        "情绪标签仅可使用 neutral、happy、sad、anxious、stressed、tired、angry、"
        "overwhelmed、focused。意图标签仅可使用 unknown、chat、acknowledge、"
        "task_planning、task_execution、task_review、task_blocked、rest_request、"
        "help_request、remember_preference。\n用户输入："
        f"{user_prompt}"
    )
    attempted: list[str] = []
    for model in candidates:
        if not model:
            continue
        attempted.append(model)
        try:
            response = await asyncio.wait_for(
                caller(
                    model=model,
                    prompt=classification_prompt,
                    system_prompt="",
                    stream=False,
                    max_tokens=180,
                    thinking_budget=0,
                    temperature=0.0,
                ),
                timeout=settings.GIRLAI_CLASSIFICATION_TIMEOUT_SECONDS,
            )
            result = parse_classification_response(response)
            result.model = model
            result.calls = len(attempted)
            result.fallback_used = model != primary
            result.fallback_history = attempted[:-1]
            return result
        except Exception as error:
            logger.warning(
                "GirlAI 分类模型失败 | model=%s | error_type=%s",
                model,
                type(error).__name__,
            )

    return ClassificationResult(
        calls=len(attempted),
        fallback_used=len(attempted) > 1,
        fallback_history=attempted,
        degraded_capabilities=["emotion_classification", "intent_classification"],
        parse_failed=True,
    )


def apply_companion_policy(turn: CompanionTurn, result: ClassificationResult) -> CompanionTurn:
    turn.emotion = result.emotion
    turn.intent = result.intent
    turn.model_context.classification_model = result.model
    turn.model_context.calls += result.calls
    turn.model_context.fallback_used = turn.model_context.fallback_used or result.fallback_used
    turn.model_context.fallback_history = list(
        dict.fromkeys([*turn.model_context.fallback_history, *result.fallback_history])
    )
    turn.degraded_capabilities = list(
        dict.fromkeys([*turn.degraded_capabilities, *result.degraded_capabilities])
    )
    if turn.emotion.low_confidence:
        turn.degraded_capabilities = list(
            dict.fromkeys([*turn.degraded_capabilities, "emotion_low_confidence"])
        )
    if turn.intent.low_confidence:
        turn.degraded_capabilities = list(
            dict.fromkeys([*turn.degraded_capabilities, "intent_low_confidence"])
        )

    turn.care_required = turn.emotion.label in _CARE_EMOTIONS
    if turn.care_required:
        turn.response_style = "care"
        turn.work_options = _work_options(turn.intent.label, caring=True)
        description = _CARE_DESCRIPTIONS[turn.emotion.label]
        prefix = f"我听见你现在{description}，我们可以把节奏放慢一点。"
        options = "；".join(turn.work_options)
        turn.assistant_text = (
            f"{prefix}\n\n{turn.assistant_text}\n\n你可以选择：{options}。"
        )[:20000]
    elif turn.emotion.low_confidence or turn.intent.low_confidence:
        turn.response_style = "neutral"
        turn.work_options = _work_options(turn.intent.label)
    else:
        turn.response_style = "standard"
        turn.work_options = _work_options(turn.intent.label)
    return turn


def _work_options(intent: str, caring: bool = False) -> list[str]:
    options = {
        "task_planning": ["梳理当前目标", "拆分一个最小步骤"],
        "task_execution": ["继续当前步骤", "检查执行结果"],
        "task_review": ["回顾已完成内容", "确定下一步改进"],
        "task_blocked": ["确认当前阻塞点", "选择一个可绕开的步骤"],
        "rest_request": ["休息五分钟", "稍后继续当前任务"],
        "help_request": ["描述当前问题", "一起确定优先级"],
    }.get(intent, ["先处理一个最小步骤", "说明你想优先推进的事项"])
    if caring:
        return ["先暂停一分钟调整状态", options[0], options[1]]
    return options


__all__ = [
    "ClassificationResult",
    "apply_companion_policy",
    "classify_companion_input",
    "normalize_emotion",
    "normalize_intent",
    "parse_classification_response",
]
