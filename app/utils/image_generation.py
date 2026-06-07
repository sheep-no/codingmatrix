"""
Kolors 图像生成工具 - 支持文生图和图生图

模型：Kwai-Kolors/Kolors
功能：
- 文生图 (Text-to-Image)
- 图生图 (Image-to-Image)
- 图像编辑
"""
import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import io

import httpx
from httpx import Timeout
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

# Kolors 模型配置
KOLORS_MODEL = "Kwai-Kolors/Kolors"
KOLORS_BASE_URL = "https://api.siliconflow.cn/v1"

# 支持的输入/输出格式
SUPPORTED_FORMATS = ['.png', '.jpg', '.jpeg', '.webp']
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# 默认参数
DEFAULT_CONFIG = {
    "width": 1024,
    "height": 1024,
    "num_inferences": 50,
    "guidance_scale": 7.5,
    "num_images": 1,
}

OUTPUT_DIR = Path("./generated_images")
OUTPUT_DIR.mkdir(exist_ok=True)

# 并发限制
_max_concurrent_generations = asyncio.Semaphore(4)

# 连接池（复用 HTTP 客户端）
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """获取或创建共享的 HTTP 客户端（连接池复用，线程安全）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _http_client_lock:
            # 双重检查锁定
            if _http_client is not None and not _http_client.is_closed:
                return _http_client
            _http_client = httpx.AsyncClient(
                timeout=Timeout(120.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
    return _http_client


async def close_http_client():
    """关闭 HTTP 客户端"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def _save_images_from_response(
    result: dict,
    prefix: str,
    output_format: str
) -> tuple[list[str], list[str]]:
    """
    从 API 响应中保存图片到本地
    返回 (images_data_url_list, image_paths_list)
    images_data_url_list 包含 data:image/xxx;base64,... 格式，可直接用于 <img src>
    """
    import time
    import uuid

    images = []
    image_paths = []
    mime = "jpeg" if output_format in ("jpg", "jpeg") else output_format

    for image_data in result.get("data", []):
        b64_data = image_data.get("b64_json")
        if b64_data:
            images.append(f"data:image/{mime};base64,{b64_data}")

            timestamp = int(time.time())
            img_id = uuid.uuid4().hex[:8]
            img_filename = f"{prefix}_{timestamp}_{img_id}.{output_format}"
            img_path = OUTPUT_DIR / img_filename

            base64_to_image(b64_data, str(img_path))
            image_paths.append(str(img_path))

    return images, image_paths


def image_to_base64(image_path: str) -> str:
    """将图片转换为 base64"""
    image_file = Path(image_path)
    
    if not image_file.exists():
        raise FileNotFoundError(f"图片文件不存在：{image_path}")
    
    file_size = image_file.stat().st_size
    if file_size > MAX_IMAGE_SIZE:
        raise ValueError(f"图片文件过大：{file_size / 1024 / 1024:.2f}MB > 10MB")
    
    ext = image_file.suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的图片格式：{ext}")
    
    with open(image_path, 'rb') as f:
        image_data = f.read()
        base64_data = base64.b64encode(image_data).decode('utf-8')
    
    mime_ext = ext.lstrip('.')
    if mime_ext == 'jpg':
        mime_ext = 'jpeg'
    mime_type = f"image/{mime_ext}"
    
    return f"data:{mime_type};base64,{base64_data}"


def base64_to_image(base64_data: str, output_path: str) -> str:
    """将 base64 数据保存为图片"""
    if base64_data.startswith('data:'):
        base64_data = base64_data.split(',')[1]
    
    image_data = base64.b64decode(base64_data)
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'wb') as f:
        f.write(image_data)
    
    return str(output_file)


async def text_to_image(
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    num_inferences: int = 50,
    guidance_scale: float = 7.5,
    num_images: int = 1,
    output_format: str = "png",
    seed: Optional[int] = None,
    timeout: Timeout = Timeout(120.0, connect=10.0),
    api_key_token: str = None
) -> Dict[str, Any]:
    """
    文生图 - 根据文字描述生成图片

    Args:
        prompt: 提示词，描述想要生成的图像
        negative_prompt: 反向提示词，描述不想出现的内容
        width: 图像宽度 (512/768/1024/1280)
        height: 图像高度 (512/768/1024/1280)
        num_inferences: 推理步数 (20-100，默认 50)
        guidance_scale: 引导系数 (1-20，默认 7.5)
        num_images: 生成图片数量 (1-4)
        output_format: 输出格式 (png/jpg)
        seed: 随机种子（可复现结果）
        timeout: 超时设置

    Returns:
        {
            "success": True,
            "images": ["base64_data_1", ...],
            "paths": ["/path/to/image1.png", ...],
            "prompt": "原始 prompt",
            "config": {...}
        }
    """
    data = {
        "model": KOLORS_MODEL,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_inferences": num_inferences,
        "guidance_scale": guidance_scale,
        "num_images": num_images,
        "response_format": "b64_json"
    }
    if seed is not None:
        data["seed"] = seed

    logger.info(f"文生图请求 | prompt={prompt[:50]}... | size={width}x{height}")
    result = await _call_kolors_api(data, timeout, api_key_token=api_key_token)
    images, image_paths = _save_images_from_response(result, "kolors", output_format)
    logger.info(f"文生图成功 | 生成 {len(images)} 张图片")

    return {
        "success": True,
        "images": images,
        "paths": image_paths,
        "prompt": prompt,
        "config": {
            "width": width, "height": height,
            "num_inferences": num_inferences,
            "guidance_scale": guidance_scale, "seed": seed
        }
    }


async def image_to_image(
    image_path: str,
    prompt: str,
    negative_prompt: str = "",
    strength: float = 0.75,
    width: Optional[int] = None,
    height: Optional[int] = None,
    num_inferences: int = 50,
    guidance_scale: float = 7.5,
    num_images: int = 1,
    output_format: str = "png",
    seed: Optional[int] = None,
    timeout: Timeout = Timeout(120.0, connect=10.0),
    api_key_token: str = None
) -> Dict[str, Any]:
    """
    图生图 - 基于参考图生成新图片

    Args:
        image_path: 参考图片路径
        prompt: 提示词，描述想要的效果
        negative_prompt: 反向提示词
        strength: 重绘强度 (0-1，0.5-0.8 推荐)
        width: 输出宽度（默认与原图相同）
        height: 输出高度（默认与原图相同）
        num_inferences: 推理步数
        guidance_scale: 引导系数
        num_images: 生成数量
        output_format: 输出格式
        seed: 随机种子
        timeout: 超时设置

    Returns:
        {
            "success": True,
            "images": ["base64_data_1", ...],
            "paths": ["/path/to/image1.png", ...],
            "reference_image": "原图路径",
            "prompt": "原始 prompt"
        }
    """
    data = {
        "model": KOLORS_MODEL,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "init_image": image_to_base64(image_path),
        "strength": strength,
        "num_inferences": num_inferences,
        "guidance_scale": guidance_scale,
        "num_images": num_images,
        "response_format": "b64_json"
    }
    if width:
        data["width"] = width
    if height:
        data["height"] = height
    if seed is not None:
        data["seed"] = seed

    logger.info(f"图生图请求 | ref={image_path} | prompt={prompt[:50]}... | strength={strength}")
    result = await _call_kolors_api(data, timeout, api_key_token=api_key_token)
    images, image_paths = _save_images_from_response(result, "kolors_img2img", output_format)
    logger.info(f"图生图成功 | 生成 {len(images)} 张图片")

    return {
        "success": True,
        "images": images,
        "paths": image_paths,
        "reference_image": image_path,
        "prompt": prompt,
        "config": {"strength": strength, "width": width, "height": height, "seed": seed}
    }


async def inpaint_image(
    image_path: str,
    mask_path: str,
    prompt: str,
    negative_prompt: str = "",
    strength: float = 0.75,
    num_inferences: int = 50,
    guidance_scale: float = 7.5,
    output_format: str = "png",
    seed: Optional[int] = None,
    timeout: Timeout = Timeout(120.0, connect=10.0),
    api_key_token: str = None
) -> Dict[str, Any]:
    """
    图像修复/局部重绘 - 修改图像的指定区域

    Args:
        image_path: 原图路径
        mask_path: 掩码图路径（白色区域为重绘区域）
        prompt: 提示词
        negative_prompt: 反向提示词
        strength: 重绘强度
        num_inferences: 推理步数
        guidance_scale: 引导系数
        output_format: 输出格式
        seed: 随机种子
        timeout: 超时设置

    Returns:
        {
            "success": True,
            "images": [...],
            "paths": [...],
            "prompt": prompt
        }
    """
    data = {
        "model": KOLORS_MODEL,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "init_image": image_to_base64(image_path),
        "mask_image": image_to_base64(mask_path),
        "strength": strength,
        "num_inferences": num_inferences,
        "guidance_scale": guidance_scale,
        "response_format": "b64_json"
    }
    if seed is not None:
        data["seed"] = seed

    logger.info(f"图像修复请求 | image={image_path} | mask={mask_path}")
    result = await _call_kolors_api(data, timeout, api_key_token=api_key_token)
    images, image_paths = _save_images_from_response(result, "kolors_inpaint", output_format)

    return {"success": True, "images": images, "paths": image_paths, "prompt": prompt}


async def _call_kolors_api(data: dict, timeout: Timeout, api_key_token: str = None, max_retries: int = 3) -> dict:
    """Kolors API 调用公共逻辑（带重试机制和并发限制）"""
    async with _max_concurrent_generations:
        last_error = None
        
        for attempt in range(max_retries):
            try:
                api_key = settings.SILICONFLOW_API_KEY
                if api_key_token:
                    from app.services.apikey_manager import get_apikey_manager
                    try:
                        apikey_manager = get_apikey_manager()
                        user_key = apikey_manager.get_key_by_token(api_key_token)
                        if user_key:
                            api_key = user_key
                    except Exception as e:
                        logger.warning(f"获取用户 API Key 失败，使用系统默认 Key: {e}")
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                client = await get_http_client()
                response = await client.post(
                    f"{KOLORS_BASE_URL}/images/generations",
                    headers=headers, json=data
                )
                
                if response.status_code == 200:
                    return response.json()
                
                error_msg = f"status={response.status_code} | {response.text}"
                logger.warning(f"Kolors API 调用失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                last_error = HTTPException(status_code=response.status_code, detail=f"图像生成失败：{response.text}")
                
                if response.status_code >= 500:
                    wait_time = (2 ** attempt) * 1.0
                    await asyncio.sleep(wait_time)
                else:
                    break
                    
            except httpx.TimeoutException as e:
                last_error = HTTPException(status_code=504, detail=f"图像生成超时：{str(e)}")
                logger.warning(f"Kolors API 超时 (尝试 {attempt + 1}/{max_retries}): {e}")
                wait_time = (2 ** attempt) * 1.0
                await asyncio.sleep(wait_time)
            except httpx.HTTPError as e:
                last_error = HTTPException(status_code=502, detail=f"图像生成网络错误：{str(e)}")
                logger.warning(f"Kolors API 网络错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                wait_time = (2 ** attempt) * 1.0
                await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = HTTPException(status_code=500, detail=f"图像生成失败：{str(e)}")
                logger.error(f"Kolors API 调用异常: {e}", exc_info=True)
                break
        
        raise last_error or HTTPException(status_code=500, detail="图像生成失败")


# 快捷函数 - 常用场景

async def generate_avatar(prompt: str, style: str = "anime") -> Dict[str, Any]:
    """生成头像"""
    style_prompts = {
        "anime": "日系动漫风格，精美的头像插画，细节丰富",
        "realistic": "写实风格，高质量肖像摄影，专业打光",
        "pixel": "像素艺术风格，复古游戏风格",
        "chibi": "Q 版卡通风格，可爱形象",
    }
    
    full_prompt = f"{style_prompts.get(style, '')}, {prompt}, 高质量，精细细节"
    
    return await text_to_image(
        prompt=full_prompt,
        negative_prompt="丑陋，模糊，低质量，畸形的脸，多余的四肢",
        width=512,
        height=512,
        num_inferences=30,
        num_images=1
    )


async def generate_landscape(prompt: str, style: str = "realistic") -> Dict[str, Any]:
    """生成风景图"""
    style_prompts = {
        "realistic": "照片级真实感，专业摄影，",
        "oil_painting": "油画风格，艺术大师作品，",
        "watercolor": "水彩画风格，清新淡雅，",
        "digital_art": "数字艺术，概念图，",
    }
    
    full_prompt = f"{style_prompts.get(style, '')}{prompt}, 高质量，精美构图"
    
    return await text_to_image(
        prompt=full_prompt,
        negative_prompt="丑陋，模糊，低质量，构图混乱",
        width=1280,
        height=768,
        num_inferences=50
    )


async def generate_icon(prompt: str) -> Dict[str, Any]:
    """生成图标"""
    return await text_to_image(
        prompt=f"{prompt}, 扁平化图标设计，简洁现代，矢量风格",
        negative_prompt="照片，写实，复杂细节，渐变色",
        width=512,
        height=512,
        num_inferences=30,
        guidance_scale=9.0
    )
