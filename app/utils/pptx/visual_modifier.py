"""
PPT 视觉修改器 - 集成层

将视觉分析、意图解析、PPTX 修改器串联为完整流程。

流程：
1. 用户输入修改需求（自然语言）
2. 修改意图解析器提取目标幻灯片和修改类型
3. 视觉分析器分析目标幻灯片的当前状态
4. 结合视觉分析结果和修改意图，生成修改方案
5. PPTX 修改器应用修改
6. 返回修改后的预览图供用户确认

使用方式：
    result = await modify_ppt_visual(
        pptx_path="output.pptx",
        user_input="修改第三页的字体为微软雅黑",
        output_path="output_modified.pptx"
    )
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from app.utils.pptx.slide_renderer import SlideRenderer
from app.utils.pptx.visual_analyzer import PPTVisualAnalyzer, SlideStyleInfo
from app.utils.pptx.modify_intent_parser import (
    ModifyIntentParser, ModifyIntent, ModifyTarget,
    parse_modify_intent, format_modify_intent
)
from app.utils.pptx.ppt_modifier import PPTModifier, modify_ppt

logger = logging.getLogger(__name__)


@dataclass
class ModifyResult:
    """修改结果"""
    success: bool
    message: str
    intent: Optional[ModifyIntent] = None
    analysis: Optional[Dict[str, Any]] = None
    output_path: Optional[str] = None
    preview_images: List[bytes] = field(default_factory=list)  # 修改后的预览图


class PPTVisualModifier:
    """PPT 视觉修改器"""

    def __init__(self, pptx_path: str, api_key_token: Optional[str] = None, user_id: Optional[str] = None):
        """
        初始化修改器

        Args:
            pptx_path: PPTX 文件路径
            api_key_token: 用户 API Key Token（用于视觉模型调用）
            user_id: 用户 ID
        """
        self.pptx_path = Path(pptx_path)
        if not self.pptx_path.exists():
            raise FileNotFoundError(f"PPTX 文件不存在：{pptx_path}")

        self.api_key_token = api_key_token
        self.user_id = user_id
        self.renderer = SlideRenderer(str(self.pptx_path))
        self.intent_parser = ModifyIntentParser()

    async def modify(
        self,
        user_input: str,
        output_path: str,
        analyze_before_modify: bool = True
    ) -> ModifyResult:
        """
        执行修改

        Args:
            user_input: 用户修改需求（自然语言）
            output_path: 输出文件路径
            analyze_before_modify: 修改前是否分析当前状态

        Returns:
            修改结果
        """
        try:
            # 1. 解析修改意图
            intent = self.intent_parser.parse(user_input)
            if not intent.targets:
                return ModifyResult(
                    success=False,
                    message="无法识别修改意图，请更明确地描述修改需求。例如：'修改第三页的字体为微软雅黑'"
                )

            logger.info(f"解析修改意图：{format_modify_intent(intent)}")

            # 2. 分析当前状态（可选）
            analysis = None
            if analyze_before_modify:
                analysis = await self._analyze_target_slides(intent)

            # 3. 应用修改
            modifier = PPTModifier(str(self.pptx_path))
            success = modifier.apply_modifications(intent, output_path)

            if not success:
                return ModifyResult(
                    success=False,
                    message="修改应用失败",
                    intent=intent,
                    analysis=analysis
                )

            # 4. 生成修改后的预览图
            preview_images = self._generate_previews(output_path, intent)

            return ModifyResult(
                success=True,
                message=f"修改完成：{format_modify_intent(intent)}",
                intent=intent,
                analysis=analysis,
                output_path=output_path,
                preview_images=preview_images
            )

        except Exception as e:
            logger.error(f"修改失败：{e}")
            return ModifyResult(
                success=False,
                message=f"修改失败：{str(e)}"
            )

    async def analyze(self, slide_number: Optional[int] = None) -> Dict[str, Any]:
        """
        分析当前 PPT 状态

        Args:
            slide_number: 指定幻灯片编号，None 表示分析所有

        Returns:
            分析结果
        """
        analyzer = PPTVisualAnalyzer(str(self.pptx_path), self.api_key_token, self.user_id)

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

    async def _analyze_target_slides(self, intent: ModifyIntent) -> Dict[str, Any]:
        """分析目标幻灯片的当前状态"""
        target_slides = set()
        for target in intent.targets:
            if target.slide_number:
                target_slides.add(target.slide_number)

        if not target_slides:
            # 没有指定幻灯片，分析前几页
            target_slides = set(range(1, min(4, len(self.renderer.prs.slides) + 1)))

        analysis = {}
        analyzer = PPTVisualAnalyzer(str(self.pptx_path), self.api_key_token, self.user_id)

        for slide_num in target_slides:
            style_info = await analyzer.analyze_slide(slide_num)
            if style_info:
                analysis[f"slide_{slide_num}"] = {
                    "layout_type": style_info.layout_type,
                    "fonts": style_info.fonts,
                    "font_sizes": style_info.font_sizes,
                    "colors": style_info.colors,
                    "visual_description": style_info.visual_description
                }

        return analysis

    def _generate_previews(self, output_path: str, intent: ModifyIntent) -> List[bytes]:
        """生成修改后的预览图"""
        try:
            renderer = SlideRenderer(output_path)
            preview_images = []

            target_slides = set()
            for target in intent.targets:
                if target.slide_number:
                    target_slides.add(target.slide_number)

            if not target_slides:
                # 没有指定幻灯片，生成前几页预览
                target_slides = set(range(1, min(4, len(renderer.prs.slides) + 1)))

            for slide_num in target_slides:
                img_bytes = renderer.render_slide(slide_num)
                if img_bytes:
                    preview_images.append(img_bytes)

            return preview_images

        except Exception as e:
            logger.warning(f"生成预览图失败：{e}")
            return []


async def modify_ppt_visual(
    pptx_path: str,
    user_input: str,
    output_path: str,
    api_key_token: Optional[str] = None,
    user_id: Optional[str] = None,
    analyze_before_modify: bool = True
) -> Dict[str, Any]:
    """
    视觉增强 PPT 修改

    Args:
        pptx_path: 输入 PPTX 路径
        user_input: 用户修改需求
        output_path: 输出 PPTX 路径
        api_key_token: 用户 API Key Token
        user_id: 用户 ID
        analyze_before_modify: 修改前是否分析

    Returns:
        修改结果字典
    """
    modifier = PPTVisualModifier(pptx_path, api_key_token, user_id)
    result = await modifier.modify(user_input, output_path, analyze_before_modify)

    return {
        "success": result.success,
        "message": result.message,
        "output_path": result.output_path,
        "intent": {
            "raw_text": result.intent.raw_text if result.intent else "",
            "targets": [
                {
                    "slide_number": t.slide_number,
                    "element_type": t.element_type,
                    "property_name": t.property_name,
                    "property_value": t.property_value
                }
                for t in result.intent.targets
            ] if result.intent else [],
            "confidence": result.intent.confidence if result.intent else 0
        } if result.intent else None,
        "analysis": result.analysis,
        "preview_count": len(result.preview_images)
    }


async def analyze_ppt_for_modification(
    pptx_path: str,
    slide_number: Optional[int] = None,
    api_key_token: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    分析 PPT 用于修改（不执行修改）

    Args:
        pptx_path: PPTX 文件路径
        slide_number: 指定幻灯片编号
        api_key_token: 用户 API Key Token
        user_id: 用户 ID

    Returns:
        分析结果
    """
    modifier = PPTVisualModifier(pptx_path, api_key_token, user_id)
    return await modifier.analyze(slide_number)
