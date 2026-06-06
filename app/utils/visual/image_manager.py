"""
图片素材管理器 - 管理 PPT 所需的图片素材

功能：
1. 根据描述生成图片（使用 Kolors 等 API）
2. 搜索并下载免费图片
3. 图片缓存管理
4. 图片裁剪和适配
"""
import asyncio
import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import httpx
from PIL import Image
import io

from app.core.config import settings

logger = logging.getLogger(__name__)

# 图片保存目录
IMAGE_CACHE_DIR = Path("./pptx_output/image_cache")
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class ImageSource(Enum):
    """图片来源"""
    GENERATED = "generated"  # AI 生成
    KOLORS = "kolors"       # Kolors API
    UNSPLASH = "unsplash"   # Unsplash 免费图片
    LOCAL = "local"         # 本地素材库
    NONE = "none"           # 无图片


@dataclass
class ImageAsset:
    """图片资源"""
    source: ImageSource
    local_path: Optional[str] = None
    url: Optional[str] = None
    description: str = ""
    keywords: List[str] = None
    width: int = 0
    height: int = 0
    used_in_slide: int = 0  # 使用的幻灯片索引
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class ImageManager:
    """图片素材管理器"""
    
    def __init__(self):
        self.cache: Dict[str, ImageAsset] = {}
        self.generated_count = 0
        self.max_generations_per_ppt = 3  # 限制每 PPT 生成图片数量，节省成本
    
    async def get_image_for_slide(
        self,
        image_type: str,
        description: str,
        keywords: List[str],
        slide_index: int,
        style: str = "插画风格，扁平化设计"
    ) -> ImageAsset:
        """
        为幻灯片获取合适的图片
        
        Args:
            image_type: 图片类型（photo, illustration, chart, icon, diagram）
            description: 图片描述
            keywords: 关键词列表
            slide_index: 幻灯片索引
            style: 风格描述
        
        Returns:
            ImageAsset: 图片资源对象
        """
        # 生成缓存键
        cache_key = self._generate_cache_key(description, keywords)
        
        # 检查缓存
        if cache_key in self.cache:
            logger.info(f"图片命中缓存 | key={cache_key[:20]}...")
            return self.cache[cache_key]
        
        # 决定图片来源
        if self.generated_count >= self.max_generations_per_ppt:
            logger.info("已达到最大生成次数，使用占位符")
            return self._create_placeholder(description, keywords)
        
        # 尝试获取图片，按优先级降级
        asset = None
        errors = []
        
        # 策略1：优先使用高品图像搜索（所有类型都适用）
        try:
            asset = await self._search_gaopin(keywords)
            if asset:
                logger.info(f"高品图像搜索成功 | type={image_type}")
        except Exception as e:
            errors.append(f"Gaopin: {str(e)}")
            logger.warning(f"高品图像搜索失败: {e}")
        
        # 策略2：插画/图表类型尝试 Kolors 生成
        if not asset and image_type in ["illustration", "diagram", "icon"]:
            try:
                asset = await self._generate_with_kolors(description, keywords, style)
                if asset and asset.source != ImageSource.NONE:
                    logger.info(f"Kolors 生成成功 | type={image_type}")
            except Exception as e:
                errors.append(f"Kolors: {str(e)}")
                logger.warning(f"Kolors 生成失败: {e}")
        
        # 策略3：照片类尝试 Unsplash
        if not asset and image_type == "photo":
            try:
                asset = await self._search_unsplash(keywords)
                if asset and asset.source != ImageSource.NONE:
                    logger.info("Unsplash 获取成功")
            except Exception as e:
                errors.append(f"Unsplash: {str(e)}")
                logger.warning(f"Unsplash 获取失败: {e}")
        
        # 最终降级：使用专业占位符
        if not asset or asset.source == ImageSource.NONE:
            logger.info(f"所有图片获取策略失败，使用占位符 | errors={errors}")
            asset = self._create_placeholder(description, keywords)
        
        if asset and asset.source != ImageSource.NONE:
            asset.used_in_slide = slide_index
            self.cache[cache_key] = asset
            self.generated_count += 1
        
        return asset
    
    async def _generate_with_kolors(
        self,
        description: str,
        keywords: List[str],
        style: str
    ) -> Optional[ImageAsset]:
        """使用 Kolors API 生成图片"""
        try:
            # 构建提示词
            prompt = f"{description}, {style}, 高质量, 插画风格"
            
            # Kolors API 调用
            data = {
                "model": "Kwai-Kolors/Kolors",
                "prompt": prompt,
                "image_size": [768, 768],
                "num_inference_steps": 20,
                "guidance_scale": 7.5
            }
            
            headers = {
                "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=120) as client:
                # 发起生成请求
                response = await client.post(
                    "https://api.siliconflow.cn/v1/images/generations",
                    headers=headers,
                    json=data
                )
                
                if response.status_code != 200:
                    logger.error(f"Kolors API 错误: {response.status_code} | {response.text}")
                    return None
                
                result = response.json()
                image_url = result.get("data", [{}])[0].get("url")
                
                if not image_url:
                    return None
                
                # 下载并保存图片
                local_path = await self._download_image(image_url, description)
                
                if local_path:
                    return ImageAsset(
                        source=ImageSource.KOLORS,
                        local_path=local_path,
                        url=image_url,
                        description=description,
                        keywords=keywords
                    )
                
        except Exception as e:
            logger.error(f"Kolors 图片生成失败: {str(e)}")
        
        return None
    
    async def _search_unsplash(
        self,
        keywords: List[str]
    ) -> ImageAsset:
        """从 Unsplash 搜索免费图片"""
        try:
            # 使用 Unsplash Source API（无需 API key）
            keyword = keywords[0] if keywords else "business"
            url = f"https://source.unsplash.com/800x600/?{keyword}"
            
            # 尝试下载
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    local_path = await self._save_image_bytes(
                        response.content, 
                        f"unsplash_{keyword}"
                    )
                    
                    if local_path:
                        return ImageAsset(
                            source=ImageSource.UNSPLASH,
                            local_path=local_path,
                            url=url,
                            description=f"Unsplash: {keyword}",
                            keywords=keywords
                        )
                        
        except Exception as e:
            logger.error(f"Unsplash 图片获取失败: {str(e)}")
        
        return ImageAsset(source=ImageSource.NONE)
    
    async def _search_gaopin(
        self,
        keywords: List[str]
    ) -> Optional[ImageAsset]:
        """从高品图像搜索图片"""
        try:
            keyword = keywords[0] if keywords else "safety"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.gaopinimages.com/",
                "Content-Type": "application/json"
            }
            
            payload = {
                "keyType": 1,
                "sortOrder": "1",
                "from": 1,
                "size": 3,
                "qk": keyword,
                "style": 1,
                "materialCategory": "",
                "color": "",
                "imagesShape": "",
                "licenseType": "",
                "materialType": "",
                "modelSex": "",
                "peopleNum": "",
                "portraitureRight": "",
                "secondCategory": "",
                "huiXuanSelected": ""
            }
            
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://www.gaopinimages.com/crest/search/searchImageV2",
                    json=payload,
                    headers=headers
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("return_code") == "000000":
                        images = data.get("return_data", {}).get("data", [])
                        if images:
                            img_url = images[0].get("thumbnailUrl300C")
                            if img_url:
                                # 下载并转换图片
                                local_path = await self._download_image(img_url, f"gaopin_{keyword}")
                                if local_path:
                                    logger.info(f"高品图像搜索成功 | keyword={keyword} | url={img_url}")
                                    return ImageAsset(
                                        source=ImageSource.LOCAL,
                                        local_path=local_path,
                                        url=img_url,
                                        description=f"高品图像: {keyword}",
                                        keywords=keywords
                                    )
            
            logger.warning(f"高品图像搜索无结果 | keyword={keyword}")
            
        except Exception as e:
            logger.error(f"高品图像搜索失败: {str(e)}")
        
        return None
    
    async def _download_image(self, url: str, description: str) -> Optional[str]:
        """下载图片并保存到本地，自动转换 WEBP 格式"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    # 检查是否是 WEBP 格式
                    content_type = response.headers.get("content-type", "")
                    is_webp = "webp" in content_type.lower() or ".webp" in url.lower()
                    
                    filename = self._generate_filename(description)
                    
                    if is_webp:
                        # WEBP 需要转换
                        from PIL import Image
                        import io
                        
                        img = Image.open(io.BytesIO(response.content))
                        if img.mode in ('RGBA', 'LA', 'P'):
                            img = img.convert('RGB')
                        
                        # 保存为 PNG
                        local_path = IMAGE_CACHE_DIR / filename.replace(".jpg", ".png").replace(".webp", ".png")
                        img.save(local_path, 'PNG', quality=95)
                        logger.info(f"WEBP 图片转换成功 | path={local_path}")
                    else:
                        # 直接保存
                        local_path = IMAGE_CACHE_DIR / filename
                        with open(local_path, "wb") as f:
                            f.write(response.content)
                        logger.info(f"图片下载成功 | path={local_path}")
                    
                    return str(local_path)
                    
        except Exception as e:
            logger.error(f"图片下载失败: {str(e)}")
        
        return None
    
    async def _save_image_bytes(
        self,
        image_bytes: bytes,
        keyword: str
    ) -> Optional[str]:
        """保存图片字节到本地"""
        try:
            filename = f"{keyword}_{uuid.uuid4().hex[:8]}.jpg"
            local_path = IMAGE_CACHE_DIR / filename
            
            with open(local_path, "wb") as f:
                f.write(image_bytes)
            
            return str(local_path)
        except Exception as e:
            logger.error(f"图片保存失败: {str(e)}")
            return None
    
    def _create_placeholder(
        self,
        description: str,
        keywords: List[str]
    ) -> ImageAsset:
        """创建专业的占位符图片"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            filename = f"placeholder_{uuid.uuid4().hex[:8]}.png"
            local_path = IMAGE_CACHE_DIR / filename
            
            width, height = 800, 600
            
            # 根据关键词选择配色方案
            color_schemes = {
                "warning": ((255, 102, 0), (255, 153, 102)),   # 橙色
                "water": ((0, 66, 150), (74, 144, 217)),      # 蓝色
                "safety": ((0, 128, 0), (102, 178, 102)),      # 绿色
                "danger": ((204, 0, 0), (255, 102, 102)),     # 红色
                "info": ((100, 100, 100), (150, 150, 150)),   # 灰色
            }
            
            scheme = "water"
            for key in color_schemes:
                if any(key in k.lower() for k in keywords):
                    scheme = key
                    break
            
            color1, color2 = color_schemes[scheme]
            
            # 创建渐变背景
            img = Image.new('RGB', (width, height), color1)
            draw = ImageDraw.Draw(img)
            
            for i in range(height):
                ratio = i / height
                r = int(color1[0] + (color2[0] - color1[0]) * ratio)
                g = int(color1[1] + (color2[1] - color1[1]) * ratio)
                b = int(color1[2] + (color2[2] - color1[2]) * ratio)
                draw.line([(0, i), (width, i)], fill=(r, g, b))
            
            # 添加装饰边框
            border_width = 20
            draw.rectangle([(0, 0), (width-1, height-1)], outline='white', width=border_width)
            
            # 添加中心图标区域
            icon_size = 150
            icon_left = (width - icon_size) // 2
            icon_top = (height - icon_size) // 2 - 30
            draw.ellipse(
                [(icon_left, icon_top), (icon_left + icon_size, icon_top + icon_size)],
                fill='white',
                outline='white',
                width=5
            )
            
            # 添加图标符号（使用 Unicode 或简单形状）
            icon_symbols = {
                "warning": "!",  # 感叹号
                "water": "~",    # 波浪
                "safety": "+",   # 加号
                "danger": "X",    # X
                "info": "i",     # i
            }
            symbol = icon_symbols.get(scheme, "·")
            
            # 绘制符号
            symbol_size = 80
            symbol_left = (width - symbol_size) // 2
            symbol_top = (height - symbol_size) // 2 - 30
            draw.text(
                (symbol_left + symbol_size//2, symbol_top + symbol_size//2),
                symbol,
                fill=color1,
                anchor="mm"
            )
            
            # 添加文字标签
            text = "图片占位符"
            text_bbox = draw.textbbox((0, 0), text)
            text_width = text_bbox[2] - text_bbox[0]
            text_left = (width - text_width) // 2
            draw.text(
                (text_left, height - 80),
                text,
                fill='white'
            )
            
            # 保存
            img.save(local_path)
            logger.info(f"创建专业占位符 | scheme={scheme} | path={local_path}")
            
            return ImageAsset(
                source=ImageSource.LOCAL,
                local_path=str(local_path),
                description=f"占位符: {description}",
                keywords=keywords
            )
        except Exception as e:
            logger.error(f"占位符创建失败: {str(e)}")
            return ImageAsset(source=ImageSource.NONE)
    
    def _generate_cache_key(self, description: str, keywords: List[str]) -> str:
        """生成缓存键"""
        content = f"{description}:{','.join(keywords)}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _generate_filename(self, description: str) -> str:
        """生成文件名"""
        safe_name = "".join(c for c in description if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name[:30]
        return f"{safe_name}_{uuid.uuid4().hex[:8]}.png"
    
    async def generate_icon(
        self,
        icon_type: str,
        color: str = "#004296"
    ) -> Optional[str]:
        """生成图标（使用 emoji 或简单形状作为备选）"""
        # 简单的 emoji 图标映射
        icon_map = {
            "warning": "[WARNING]",
            "info": "[INFO]",
            "check": "✓",
            "cross": "✗",
            "arrow": "→",
            "star": "★",
            "heart": "♥",
            "book": "📖",
            "people": "👥",
            "chart": "[CHART]",
            "lightbulb": "[TIP]",
            "target": "[TARGET]",
        }
        
        emoji = icon_map.get(icon_type.lower(), "●")
        
        # 创建图标图片
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            size = 128
            img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)
            
            # 绘制圆形背景
            draw.ellipse([8, 8, size-8, size-8], fill=color)
            
            # 保存
            filename = f"icon_{icon_type}_{uuid.uuid4().hex[:8]}.png"
            local_path = IMAGE_CACHE_DIR / filename
            img.save(local_path)
            
            return str(local_path)
        except Exception as e:
            logger.error(f"图标生成失败: {str(e)}")
            return None
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.generated_count = 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "cached_images": len(self.cache),
            "generated_count": self.generated_count,
            "cache_dir": str(IMAGE_CACHE_DIR)
        }


# 全局实例
image_manager = ImageManager()