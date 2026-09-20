"""
视觉模型工具 - 支持图片理解和分析

模型分工:
- Qwen/Qwen3.5-4B: 视觉理解、图像分析和内容描述（主力）
- deepseek-ai/DeepSeek-OCR: OCR 文字识别（专用）
- PaddlePaddle/PaddleOCR-VL-1.5: 文档视觉理解与 OCR
"""
import base64
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from httpx import Timeout
from fastapi import HTTPException
from app.agent.models import DEFAULT_CODE_MODEL, DEFAULT_OCR_MODEL, DEFAULT_VISUAL_MODEL

logger = logging.getLogger(__name__)

# 视觉模型配置
VISION_MODEL = DEFAULT_VISUAL_MODEL
OCR_MODEL = DEFAULT_OCR_MODEL
IMAGE_DESC_MODEL = DEFAULT_VISUAL_MODEL

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']

# 最大图片大小（10MB）
MAX_IMAGE_SIZE = 10 * 1024 * 1024

# 内容审核的不安全关键词（中英双语）
_UNSAFE_KEYWORDS = [
    "色情", "暴力", "血腥", "敏感", "侵权", "违法", "不当", "恐怖",
    "porn", "violence", "violent", "nsfw", "explicit", "illegal",
    "inappropriate", "sensitive", "copyright",
]
_NEGATION_MARKERS = [
    "不包含", "不含", "没有", "未发现", "不涉及", "未包含",
    "not contain", "does not", "doesn't", "no ", "none", "without",
]


def image_to_base64(image_path: str) -> str:
    """
    将图片转换为 base64 编码
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        base64 编码的图片数据（data URI 格式）
    """
    image_file = Path(image_path)
    
    if not image_file.exists():
        raise FileNotFoundError(f"图片文件不存在：{image_path}")
    
    # 检查文件大小
    file_size = image_file.stat().st_size
    if file_size > MAX_IMAGE_SIZE:
        raise ValueError(f"图片文件过大：{file_size / 1024 / 1024:.2f}MB > 10MB")
    
    # 检查格式
    ext = image_file.suffix.lower()
    if ext not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(f"不支持的图片格式：{ext}")
    
    # 读取并转换
    with open(image_path, 'rb') as f:
        image_data = f.read()
        base64_data = base64.b64encode(image_data).decode('utf-8')
    
    # 返回 Data URI 格式
    mime_ext = ext.lstrip('.')
    if mime_ext == 'jpg':
        mime_ext = 'jpeg'
    mime_type = f"image/{mime_ext}"
    
    return f"data:{mime_type};base64,{base64_data}"


# 视觉模型降级列表
VISION_MODEL_FALLBACK = [
    DEFAULT_VISUAL_MODEL,
    "PaddlePaddle/PaddleOCR-VL-1.5",
    DEFAULT_OCR_MODEL,
]


async def _call_vision_model(
    image_base64: str,
    prompt: str,
    model: str,
    timeout: Timeout,
    api_key_token: Optional[str] = None,
    user_id: Optional[str] = None,
    llm_caller=None,
) -> Dict[str, Any]:
    """调用视觉模型（通过统一 call_llm 路径）"""
    if llm_caller is None:
        from app.utils import call_llm as llm_caller

    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_base64}},
            {"type": "text", "text": prompt}
        ]
    }]

    result = await llm_caller(
        model=model,
        prompt="",
        messages=messages,
        max_tokens=2048,
        timeout=timeout.total if hasattr(timeout, 'total') else 60.0,
        api_key_token=api_key_token,
    )

    content = None
    if isinstance(result, dict):
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
    if content is None:
        raise ValueError(f"视觉模型返回结构异常: {type(result).__name__}")
    return content


async def analyze_image(
    image_path: str,
    prompt: str = "请详细描述这张图片的内容",
    model: Optional[str] = None,
    timeout: Timeout = Timeout(60.0, connect=10.0)
) -> Dict[str, Any]:
    """
    分析图片内容（带降级机制）

    降级顺序：
    1. Qwen/Qwen3.5-4B
    2. PaddlePaddle/PaddleOCR-VL-1.5
    3. deepseek-ai/DeepSeek-OCR

    Args:
        image_path: 图片文件路径
        prompt: 分析提示词
        model: 显式指定时仅使用该模型；省略或为 None 时启用自动降级
        timeout: 超时设置

    Returns:
        {
            "description": "图片描述",
            "objects": ["检测到的物体"],
            "text": "识别的文字（如有）",
            "raw_response": "原始响应",
            "model_used": "实际使用的模型名称"
        }
    """
    # 转换为 base64
    image_base64 = image_to_base64(image_path)

    # 显式指定模型用于单模型诊断；未指定时才启用自动降级。
    fallback_models = [model] if model else VISION_MODEL_FALLBACK
    last_error: Optional[Exception] = None
    for fallback_model in fallback_models:
        try:
            logger.info(f"尝试视觉模型: {fallback_model}")
            description = await _call_vision_model(image_base64, prompt, fallback_model, timeout)
            logger.info(f"视觉模型成功: {fallback_model}")

            # 解析结果
            return {
                "description": description,
                "objects": [],
                "text": description,
                "raw_response": None,
                "model_used": fallback_model
            }

        except Exception as e:
            # 网络错误、结构异常、LLMCallError 等都应触发降级，而非直接 500
            detail = getattr(e, "detail", None) or str(e)
            logger.warning(f"视觉模型 {fallback_model} 调用失败: {detail}")
            last_error = e
            continue

    # 所有模型都失败
    logger.error("所有视觉模型均失败")
    last_detail = getattr(last_error, "detail", None) or (str(last_error) if last_error else "未知错误")
    raise HTTPException(
        status_code=503,
        detail=f"所有视觉模型均失败：{last_detail}"
    )


async def extract_text_from_image(
    image_path: str,
    model: str = OCR_MODEL
) -> str:
    """
    从图片中提取文字（OCR）
    
    Args:
        image_path: 图片文件路径
        model: OCR 模型
        
    Returns:
        识别的文字内容
    """
    result = await analyze_image(
        image_path,
        prompt="请识别并提取图片中的所有文字内容，保持原始格式",
        model=model
    )
    return result["text"]


async def generate_code_from_image(
    image_path: str,
    requirement: str = "",
    model: str = VISION_MODEL
) -> Dict[str, Any]:
    """
    根据图片生成代码（UI 截图转代码）
    
    Args:
        image_path: UI 截图路径
        requirement: 额外需求描述
        model: 使用的模型
        
    Returns:
        {
            "description": "界面描述",
            "technology_stack": ["建议的技术栈"],
            "code_structure": "代码结构建议",
            "raw_description": "原始描述"
        }
    """
    # 分析 UI 图片
    prompt = f"""请分析这张 UI 设计图/界面截图，并提供以下信息：

1. 界面类型和功能描述
2. 主要 UI 组件（按钮、表单、列表等）
3. 布局结构（上下布局、左右布局等）
4. 配色方案和风格
5. 推荐的技术实现方案

{requirement if requirement else ""}

请用中文详细回答。"""
    
    description_result = await analyze_image(image_path, prompt, model)
    
    # 根据描述生成代码
    code_prompt = f"""基于以下界面描述，生成完整的前端代码：

{description_result["description"]}

要求：
1. 使用现代前端框架（React/Vue）
2. 响应式设计
3. 语义化 HTML
4. 包含必要的样式

请生成完整的代码文件。"""
    
    # 调用代码生成模型（复用现有函数）
    from app.utils import call_llm
    
    code_result = await call_llm(
        model=DEFAULT_CODE_MODEL,
        prompt=code_prompt,
        max_tokens=4096
    )
    
    return {
        "description": description_result["description"],
        "technology_stack": ["React", "TailwindCSS"],  # 默认推荐
        "code_structure": "components/",
        "raw_description": code_result
    }


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中提取第一个合法 JSON 对象，失败返回 None。"""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            return obj
        start = text.find("{", start + 1)
    return None


def _keyword_safety_check(description: str) -> tuple[bool, list[str]]:
    """关键词兜底：剔除被否定词修饰的命中，返回 (safe, flags)。"""
    lowered = description.lower()
    flags = []
    for keyword in _UNSAFE_KEYWORDS:
        needle = keyword.lower()
        idx = lowered.find(needle)
        while idx != -1:
            window = lowered[max(0, idx - 24):idx]
            if not any(marker in window for marker in _NEGATION_MARKERS):
                flags.append(keyword)
                break
            idx = lowered.find(needle, idx + 1)
    return (not flags), sorted(set(flags))


async def check_image_safety(image_path: str) -> Dict[str, Any]:
    """
    检查图片安全性（内容审核）
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        {
            "safe": True/False,
            "reason": "判断理由",
            "flags": ["敏感内容标签"]
        }
    """
    prompt = """请检查这张图片是否包含以下内容：
1. 色情、暴力或敏感内容
2. 侵权或版权内容
3. 违法信息

只输出一个 JSON 对象，不要有任何其他文字，格式如下：
{"safe": true 或 false, "reason": "判断理由", "flags": ["命中的敏感标签"]}

安全时 safe 为 true、flags 为空数组；不安全时 safe 为 false 并给出理由与标签。"""

    result = await analyze_image(image_path, prompt, model=VISION_MODEL)

    description = result["description"]

    # 优先使用模型返回的结构化判定，避免关键词匹配的误判/漏判
    parsed = _extract_json_object(description)
    if parsed is not None and isinstance(parsed.get("safe"), bool):
        is_safe = parsed["safe"]
        reason = str(parsed.get("reason") or description)
        raw_flags = parsed.get("flags")
        flags = [str(flag) for flag in raw_flags] if isinstance(raw_flags, list) else []
        if not is_safe and not flags:
            flags = ["需要人工审核"]
        return {"safe": is_safe, "reason": reason, "flags": flags}

    # 模型未按 JSON 输出时回退到中英双语关键词兜底
    is_safe, flags = _keyword_safety_check(description)
    return {
        "safe": is_safe,
        "reason": description,
        "flags": [] if is_safe else (flags or ["需要人工审核"]),
    }
