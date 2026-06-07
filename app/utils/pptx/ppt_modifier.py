"""
PPT 修改处理器

根据修改意图修改 PPTX 文件，支持：
- 修改字体
- 修改字号
- 修改颜色
- 修改布局

流程：
1. 解析修改意图
2. 读取 PPTX 文件
3. 应用修改
4. 保存新 PPTX 文件
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from copy import deepcopy

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor

from app.utils.pptx.modify_intent_parser import ModifyIntent, ModifyTarget

logger = logging.getLogger(__name__)

# 颜色映射
COLOR_MAP = {
    "红色": RGBColor(0xFF, 0x00, 0x00),
    "蓝色": RGBColor(0x00, 0x00, 0xFF),
    "绿色": RGBColor(0x00, 0xFF, 0x00),
    "黄色": RGBColor(0xFF, 0xFF, 0x00),
    "黑色": RGBColor(0x00, 0x00, 0x00),
    "白色": RGBColor(0xFF, 0xFF, 0xFF),
    "紫色": RGBColor(0x80, 0x00, 0x80),
    "橙色": RGBColor(0xFF, 0xA5, 0x00),
    "灰色": RGBColor(0x80, 0x80, 0x80),
    "粉色": RGBColor(0xFF, 0xC0, 0xCB),
    "青色": RGBColor(0x00, 0xFF, 0xFF),
    "red": RGBColor(0xFF, 0x00, 0x00),
    "blue": RGBColor(0x00, 0x00, 0xFF),
    "green": RGBColor(0x00, 0xFF, 0x00),
    "yellow": RGBColor(0xFF, 0xFF, 0x00),
    "black": RGBColor(0x00, 0x00, 0x00),
    "white": RGBColor(0xFF, 0xFF, 0xFF),
}


class PPTModifier:
    """PPT 修改器"""

    def __init__(self, pptx_path: str):
        """
        初始化修改器

        Args:
            pptx_path: PPTX 文件路径
        """
        self.pptx_path = Path(pptx_path)
        if not self.pptx_path.exists():
            raise FileNotFoundError(f"PPTX 文件不存在：{pptx_path}")

        self.prs = Presentation(str(self.pptx_path))

    def apply_modifications(self, intent: ModifyIntent, output_path: str) -> bool:
        """
        应用修改

        Args:
            intent: 修改意图
            output_path: 输出路径

        Returns:
            是否成功
        """
        try:
            for target in intent.targets:
                self._apply_target(target)

            # 保存
            self.prs.save(output_path)
            logger.info(f"修改完成，保存到：{output_path}")
            return True

        except Exception as e:
            logger.error(f"应用修改失败：{e}")
            return False

    def _apply_target(self, target: ModifyTarget):
        """应用单个修改目标"""
        if target.slide_number:
            # 修改指定幻灯片
            slide_idx = target.slide_number - 1
            if 0 <= slide_idx < len(self.prs.slides):
                slide = self.prs.slides[slide_idx]
                self._modify_slide(slide, target)
            else:
                logger.warning(f"幻灯片 {target.slide_number} 不存在")
        else:
            # 修改所有幻灯片
            for slide in self.prs.slides:
                self._modify_slide(slide, target)

    def _modify_slide(self, slide, target: ModifyTarget):
        """修改单个幻灯片"""
        for shape in slide.shapes:
            if shape.has_text_frame:
                self._modify_text_frame(shape.text_frame, target)

    def _modify_text_frame(self, text_frame, target: ModifyTarget):
        """修改文本框"""
        for para in text_frame.paragraphs:
            # 检查是否是目标元素
            if not self._is_target_element(para, target):
                continue

            # 应用修改
            if target.property_name == "font" and target.property_value:
                self._apply_font(para, target.property_value)

            elif target.property_name == "size" and target.property_value:
                self._apply_font_size(para, target.property_value)

            elif target.property_name == "color" and target.property_value:
                self._apply_color(para, target.property_value)

    def _is_target_element(self, para, target: ModifyTarget) -> bool:
        """检查是否是目标元素"""
        if not target.element_type:
            return True  # 没有指定元素类型，修改所有

        text = para.text.strip()
        if not text:
            return False

        # 判断元素类型
        if target.element_type == "title":
            # 标题通常是第一个非空段落，或字号较大
            if para.font.size and para.font.size >= Pt(24):
                return True
            return False

        elif target.element_type == "text":
            # 正文
            if para.font.size and para.font.size < Pt(24):
                return True
            return True

        return True

    def _apply_font(self, para, font_name: str):
        """应用字体"""
        try:
            para.font.name = font_name
            logger.debug(f"字体修改为：{font_name}")
        except Exception as e:
            logger.warning(f"修改字体失败：{e}")

    def _apply_font_size(self, para, size_str: str):
        """应用字号"""
        try:
            # 提取数字
            import re
            match = re.search(r'(\d+)', size_str)
            if match:
                size = int(match.group(1))
                para.font.size = Pt(size)
                logger.debug(f"字号修改为：{size}pt")
        except Exception as e:
            logger.warning(f"修改字号失败：{e}")

    def _apply_color(self, para, color_str: str):
        """应用颜色"""
        if not color_str:
            return
        try:
            # 从颜色映射中查找（中文颜色名 .lower() 无实际效果，直接查原值）
            color = COLOR_MAP.get(color_str) or COLOR_MAP.get(color_str.lower())
            if color:
                para.font.color.rgb = color
                logger.debug(f"颜色修改为：{color_str}")
            else:
                # 尝试解析十六进制颜色
                if color_str.startswith('#'):
                    hex_color = color_str.lstrip('#')
                    if len(hex_color) == 6:
                        r = int(hex_color[0:2], 16)
                        g = int(hex_color[2:4], 16)
                        b = int(hex_color[4:6], 16)
                        para.font.color.rgb = RGBColor(r, g, b)
                        logger.debug(f"颜色修改为：{color_str}")
        except Exception as e:
            logger.warning(f"修改颜色失败：{e}")


def modify_ppt(
    pptx_path: str,
    intent: ModifyIntent,
    output_path: str
) -> bool:
    """
    修改 PPT

    Args:
        pptx_path: 输入 PPTX 路径
        intent: 修改意图
        output_path: 输出 PPTX 路径

    Returns:
        是否成功
    """
    modifier = PPTModifier(pptx_path)
    return modifier.apply_modifications(intent, output_path)
