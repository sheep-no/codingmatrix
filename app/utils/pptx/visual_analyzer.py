"""
PPT 视觉分析器

结合预览图（视觉模型）和 PPTX 元数据（字体、颜色）进行分析。
用于理解当前 PPT 的布局和样式，支持精确修改。

流程：
1. 渲染预览图（slide_renderer）
2. 调用视觉模型分析布局
3. 读取 PPTX 元数据增强细节
4. 融合两层信息返回分析结果
"""

import json
import logging
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from app.utils.pptx.slide_renderer import SlideRenderer, render_slide_preview, get_slide_metadata

logger = logging.getLogger(__name__)


@dataclass
class SlideStyleInfo:
    """幻灯片样式信息"""
    slide_number: int
    layout_type: str  # title, content, two_column, image_text, etc.
    fonts: List[str] = field(default_factory=list)
    font_sizes: List[int] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    elements: List[Dict[str, Any]] = field(default_factory=list)
    visual_description: str = ""  # 视觉模型对布局的描述


@dataclass
class PPTAnalysisResult:
    """PPT 分析结果"""
    total_slides: int
    slides: List[SlideStyleInfo] = field(default_factory=list)
    global_fonts: List[str] = field(default_factory=list)
    global_colors: List[str] = field(default_factory=list)
    style_summary: str = ""  # 整体样式总结


class PPTVisualAnalyzer:
    """PPT 视觉分析器"""

    def __init__(self, pptx_path: str, api_key_token: Optional[str] = None, user_id: Optional[str] = None):
        """
        初始化分析器

        Args:
            pptx_path: PPTX 文件路径
            api_key_token: 用户 API Key Token
            user_id: 用户 ID（用于查找用户的 API Key）
        """
        self.pptx_path = Path(pptx_path)
        if not self.pptx_path.exists():
            raise FileNotFoundError(f"PPTX 文件不存在：{pptx_path}")

        self.api_key_token = api_key_token
        self.user_id = user_id
        self.renderer = SlideRenderer(str(self.pptx_path))

    async def analyze_slide(self, slide_number: int) -> Optional[SlideStyleInfo]:
        """
        分析指定幻灯片

        Args:
            slide_number: 幻灯片编号（从 1 开始）

        Returns:
            样式信息
        """
        try:
            # 1. 渲染预览图
            preview_bytes = self.renderer.render_slide(slide_number)
            if not preview_bytes:
                logger.warning(f"渲染幻灯片 {slide_number} 失败")
                return None

            # 2. 获取元数据
            metadata = self.renderer.get_slide_metadata(slide_number)
            if not metadata:
                logger.warning(f"获取幻灯片 {slide_number} 元数据失败")
                return None

            # 3. 调用视觉模型分析
            visual_description = await self._analyze_with_vision(preview_bytes, slide_number)

            # 4. 融合信息
            style_info = SlideStyleInfo(
                slide_number=slide_number,
                layout_type=self._detect_layout_type(metadata),
                fonts=metadata.get("fonts", []),
                font_sizes=metadata.get("font_sizes", []),
                colors=metadata.get("colors", []),
                elements=metadata.get("elements", []),
                visual_description=visual_description
            )

            return style_info

        except Exception as e:
            logger.error(f"分析幻灯片 {slide_number} 失败：{e}")
            return None

    async def analyze_all_slides(self) -> PPTAnalysisResult:
        """
        分析所有幻灯片

        Returns:
            分析结果
        """
        result = PPTAnalysisResult(total_slides=len(self.renderer.prs.slides))

        all_fonts = set()
        all_colors = set()

        for i in range(1, result.total_slides + 1):
            style_info = await self.analyze_slide(i)
            if style_info:
                result.slides.append(style_info)
                all_fonts.update(style_info.fonts)
                all_colors.update(style_info.colors)

        result.global_fonts = list(all_fonts)
        result.global_colors = list(all_colors)

        # 生成样式总结
        result.style_summary = self._generate_style_summary(result)

        return result

    async def _analyze_with_vision(self, image_bytes: bytes, slide_number: int) -> str:
        """
        调用视觉模型分析预览图

        Args:
            image_bytes: 图片 bytes
            slide_number: 幻灯片编号

        Returns:
            视觉描述
        """
        try:
            from app.utils.vision import _call_vision_model
            from httpx import Timeout

            # 转为 base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            image_data_uri = f"data:image/png;base64,{image_base64}"

            # 构建提示词
            prompt = f"""请分析这张 PPT 幻灯片预览图的布局和样式。

要求：
1. 描述整体布局类型（如：标题页、内容页、左文右图、居中布局等）
2. 描述标题的位置和大小
3. 描述文本内容的位置和排列方式
4. 描述图片/形状的位置和大小
5. 描述整体视觉风格

请用简洁的中文描述，不超过 200 字。"""

            # 调用视觉模型（返回 str）
            response = await _call_vision_model(
                image_base64=image_data_uri,
                prompt=prompt,
                model="deepseek-ai/DeepSeek-OCR",
                timeout=Timeout(30.0, connect=10.0),
                api_key_token=self.api_key_token,
                user_id=self.user_id
            )

            # _call_vision_model 直接返回 content 字符串
            if isinstance(response, str):
                return response
            if isinstance(response, dict):
                return response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return str(response)

        except Exception as e:
            logger.warning(f"视觉模型分析失败：{e}")
            return "视觉分析不可用"

    def _detect_layout_type(self, metadata: Dict[str, Any]) -> str:
        """检测布局类型"""
        elements = metadata.get("elements", [])
        if not elements:
            return "blank"

        has_text = any(e.get("type") == "text" for e in elements)
        has_image = any(e.get("type") == "image" for e in elements)

        if has_image and has_text:
            return "image_text"
        if has_text:
            return "content"
        return "title_only"

    def _generate_style_summary(self, result: PPTAnalysisResult) -> str:
        """生成样式总结"""
        summary_parts = []

        # 统计布局类型
        layout_counts = {}
        for slide in result.slides:
            layout = slide.layout_type
            layout_counts[layout] = layout_counts.get(layout, 0) + 1

        summary_parts.append(f"共 {result.total_slides} 页幻灯片")
        summary_parts.append(f"布局类型：{', '.join(f'{k}({v}页)' for k, v in layout_counts.items())}")

        if result.global_fonts:
            summary_parts.append(f"使用字体：{', '.join(result.global_fonts[:3])}")

        if result.global_colors:
            summary_parts.append(f"使用颜色：{', '.join(result.global_colors[:3])}")

        return "；".join(summary_parts)


async def analyze_ppt_visual(
    pptx_path: str,
    slide_number: Optional[int] = None,
    api_key_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    分析 PPT 视觉样式

    Args:
        pptx_path: PPTX 文件路径
        slide_number: 指定幻灯片编号，None 表示分析所有
        api_key_token: 用户 API Key Token

    Returns:
        分析结果字典
    """
    analyzer = PPTVisualAnalyzer(pptx_path, api_key_token)

    if slide_number:
        style_info = await analyzer.analyze_slide(slide_number)
        if style_info:
            return {
                "slide_number": style_info.slide_number,
                "layout_type": style_info.layout_type,
                "fonts": style_info.fonts,
                "font_sizes": style_info.font_sizes,
                "colors": style_info.colors,
                "elements": style_info.elements,
                "visual_description": style_info.visual_description
            }
        return {"error": f"分析幻灯片 {slide_number} 失败"}

    result = await analyzer.analyze_all_slides()
    return {
        "total_slides": result.total_slides,
        "global_fonts": result.global_fonts,
        "global_colors": result.global_colors,
        "style_summary": result.style_summary,
        "slides": [
            {
                "slide_number": s.slide_number,
                "layout_type": s.layout_type,
                "fonts": s.fonts,
                "font_sizes": s.font_sizes,
                "colors": s.colors,
                "visual_description": s.visual_description
            }
            for s in result.slides
        ]
    }
