"""
PPT 修改意图解析器

解析用户的自然语言修改需求，提取：
1. 目标幻灯片（第几页）
2. 修改类型（字体、布局、颜色等）
3. 具体修改内容

示例：
- "修改第三页的字体与布局" → slide=3, modify=[font, layout]
- "把标题改成微软雅黑" → slide=all, modify=[font], target=title
- "第二页的背景改成蓝色" → slide=2, modify=[color], target=background
"""

import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModifyTarget:
    """修改目标"""
    slide_number: Optional[int] = None  # None 表示所有幻灯片
    element_type: Optional[str] = None  # title, text, background, image
    property_name: Optional[str] = None  # font, color, size, layout
    property_value: Optional[str] = None  # 具体值


@dataclass
class ModifyIntent:
    """修改意图"""
    raw_text: str
    targets: List[ModifyTarget] = field(default_factory=list)
    confidence: float = 0.0


class ModifyIntentParser:
    """修改意图解析器"""

    # 幻灯片编号模式
    SLIDE_PATTERNS = [
        r"第(\d+)页",
        r"第(\d+)张",
        r"幻灯片(\d+)",
        r"slide\s*(\d+)",
        r"第(\d+)节",
    ]

    # 修改类型关键词
    MODIFY_KEYWORDS = {
        "font": ["字体", "字型", "font"],
        "size": ["字号", "大小", "size", "字体大小"],
        "color": ["颜色", "色彩", "color", "背景色", "字体颜色"],
        "layout": ["布局", "排版", "layout", "位置", "排列"],
        "background": ["背景", "background", "底色"],
        "style": ["样式", "风格", "style", "外观"],
    }

    # 目标元素关键词
    ELEMENT_KEYWORDS = {
        "title": ["标题", "题目", "主标题", "title"],
        "text": ["正文", "内容", "文本", "文字", "text", "bullet", "要点"],
        "background": ["背景", "background", "底色"],
        "image": ["图片", "图像", "image", "照片"],
    }

    # 常见字体
    FONTS = [
        "微软雅黑", "宋体", "黑体", "楷体", "仿宋",
        "Arial", "Times New Roman", "Calibri", "Helvetica",
        "Georgia", "Verdana", "Tahoma", "Consolas",
    ]

    # 常见颜色
    COLORS = [
        "红色", "蓝色", "绿色", "黄色", "黑色", "白色",
        "紫色", "橙色", "灰色", "粉色", "青色",
        "red", "blue", "green", "yellow", "black", "white",
    ]

    def parse(self, text: str) -> ModifyIntent:
        """
        解析修改意图

        Args:
            text: 用户输入文本

        Returns:
            修改意图
        """
        if not text or not text.strip():
            return ModifyIntent(raw_text=text or "")

        intent = ModifyIntent(raw_text=text)

        # 提取幻灯片编号
        slide_numbers = self._extract_slide_numbers(text)

        # 提取修改类型
        modify_types = self._extract_modify_types(text)

        # 提取目标元素
        element_types = self._extract_element_types(text)

        # 提取具体值
        font_value = self._extract_font(text)
        color_value = self._extract_color(text)

        # 如果提取到了字体/颜色值但没有对应的修改类型，自动补充
        if font_value and "font" not in modify_types:
            modify_types.append("font")
        if color_value and "color" not in modify_types:
            modify_types.append("color")

        # 只有有明确修改类型或具体值时才创建目标
        if not modify_types:
            return intent

        # 构建修改目标
        if slide_numbers:
            for slide_num in slide_numbers:
                for modify_type in modify_types:
                    target = ModifyTarget(
                        slide_number=slide_num,
                        property_name=modify_type,
                        element_type=element_types[0] if element_types else None,
                        property_value=font_value if modify_type == "font" else color_value if modify_type == "color" else None
                    )
                    intent.targets.append(target)
        else:
            # 没有指定幻灯片，修改所有
            for modify_type in modify_types:
                target = ModifyTarget(
                    slide_number=None,
                    property_name=modify_type,
                    element_type=element_types[0] if element_types else None,
                    property_value=font_value if modify_type == "font" else color_value if modify_type == "color" else None
                )
                intent.targets.append(target)

        # 计算置信度
        intent.confidence = self._calculate_confidence(intent)

        return intent

    def _extract_slide_numbers(self, text: str) -> List[int]:
        """提取幻灯片编号"""
        numbers = []
        for pattern in self.SLIDE_PATTERNS:
            matches = re.findall(pattern, text)
            numbers.extend(int(m) for m in matches)
        return list(set(numbers))

    def _extract_modify_types(self, text: str) -> List[str]:
        """提取修改类型"""
        types = []
        text_lower = text.lower()
        for type_name, keywords in self.MODIFY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    types.append(type_name)
                    break
        return list(set(types))

    def _extract_element_types(self, text: str) -> List[str]:
        """提取目标元素类型"""
        types = []
        text_lower = text.lower()
        for element_name, keywords in self.ELEMENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    types.append(element_name)
                    break
        return list(set(types))

    def _extract_font(self, text: str) -> Optional[str]:
        """提取字体名称"""
        for font in self.FONTS:
            if font in text:
                return font
        return None

    def _extract_color(self, text: str) -> Optional[str]:
        """提取颜色"""
        for color in self.COLORS:
            if color in text:
                return color
        return None

    def _calculate_confidence(self, intent: ModifyIntent) -> float:
        """计算置信度"""
        if not intent.targets:
            return 0.0

        score = 0.0

        # 有明确的幻灯片编号
        if any(t.slide_number for t in intent.targets):
            score += 0.3

        # 有明确的修改类型
        if any(t.property_name for t in intent.targets):
            score += 0.3

        # 有明确的修改值
        if any(t.property_value for t in intent.targets):
            score += 0.4

        return min(1.0, score)


def parse_modify_intent(text: str) -> ModifyIntent:
    """
    解析修改意图

    Args:
        text: 用户输入文本

    Returns:
        修改意图
    """
    parser = ModifyIntentParser()
    return parser.parse(text)


def format_modify_intent(intent: ModifyIntent) -> str:
    """
    格式化修改意图为可读字符串

    Args:
        intent: 修改意图

    Returns:
        可读字符串
    """
    if not intent.targets:
        return "未识别到修改意图"

    parts = []
    for target in intent.targets:
        slide_str = f"第{target.slide_number}页" if target.slide_number else "所有页"
        element_str = target.element_type or "整体"
        property_str = target.property_name or "样式"
        value_str = f"→ {target.property_value}" if target.property_value else ""

        parts.append(f"{slide_str} {element_str} {property_str} {value_str}")

    return "；".join(parts)
