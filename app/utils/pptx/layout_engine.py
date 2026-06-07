"""PPTX 智能排版引擎模块

提供文字分析、布局优化、自适应字号、分栏处理、防溢出检测等功能。
"""

import math
import re
from pptx.util import Inches, Pt
from typing import Dict, List, Optional, Any


class TextAnalyzer:
    """文字分析器

    分析文本密度、统计字符数、预估文本显示高度。
    """

    # 中文字符正则表达式
    _CHINESE_CHAR_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df\U0002a700-\U0002ebef]')
    # 英文字符和数字
    _ASCII_CHAR_RE = re.compile(r'[a-zA-Z0-9]')
    # 标点符号
    _PUNCTUATION_RE = re.compile(r'[.,!?;:，。！？；："\'""''、（）【】《》]')

    @classmethod
    def analyze_text_density(cls, text: str) -> Dict[str, float]:
        """分析文字密度

        Args:
            text: 待分析的文本

        Returns:
            包含字符数、中文字符比例、英文字符比例、密度分数的字典
        """
        if not text:
            return {
                'total_chars': 0,
                'chinese_ratio': 0.0,
                'ascii_ratio': 0.0,
                'density_score': 0.0,
            }

        total = len(text)
        chinese_count = cls.count_chinese_chars(text)
        ascii_count = len(cls._ASCII_CHAR_RE.findall(text))
        space_count = text.count(' ') + text.count('\n') + text.count('\t')

        # 中文占 2 个单位宽度，英文占 1 个单位
        effective_length = chinese_count * 2 + ascii_count + space_count
        # 密度分数：文本紧凑程度，范围 0-1
        density_score = min(1.0, effective_length / max(total, 1))

        return {
            'total_chars': total,
            'chinese_count': chinese_count,
            'ascii_count': ascii_count,
            'chinese_ratio': chinese_count / total,
            'ascii_ratio': ascii_count / total,
            'effective_length': effective_length,
            'density_score': density_score,
        }

    @classmethod
    def count_chinese_chars(cls, text: str) -> int:
        """统计中文字符数

        Args:
            text: 待统计的文本

        Returns:
            中文字符数量
        """
        if not text:
            return 0
        return len(cls._CHINESE_CHAR_RE.findall(text))

    @classmethod
    def estimate_display_height(
        cls,
        text: str,
        font_size: int,
        line_spacing: float = 1.5,
        max_width: float = 6.0,
    ) -> float:
        """预估文本在给定宽度下需要的显示高度（英寸）

        Args:
            text: 待预估的文本
            font_size: 字号（Pt）
            line_spacing: 行高倍数
            max_width: 容器最大宽度（英寸）

        Returns:
            预估显示高度（英寸）
        """
        if not text:
            return 0.0

        density = cls.analyze_text_density(text)
        effective_length = density['effective_length']

        # 估算每行可容纳的字符数
        # 英文字符约 0.5pt 宽，中文字符约 1pt 宽
        char_width_pt = font_size * 0.5
        max_width_pt = Inches(max_width).pt
        chars_per_row = max(1, int(max_width_pt / char_width_pt))

        # 对于中文，每行字符数减半
        if density['chinese_ratio'] > 0.5:
            chars_per_row = max(1, chars_per_row // 2)

        # 计算总行数
        lines = math.ceil(effective_length / max(chars_per_row, 1))

        # 计算高度：每行高度 * 行数 * 行高倍数
        line_height_pt = font_size * line_spacing
        total_height_pt = line_height_pt * lines

        return Pt(total_height_pt).inches


class LayoutOptimizer:
    """布局优化器

    提供幻灯片内容优化、自适应字号、分栏处理、防溢出检测、留白优化等功能。
    """

    def __init__(self):
        self._analyzer = TextAnalyzer()

    def optimize_slide_content(
        self,
        slide_data: Dict[str, Any],
        template_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """优化单页内容布局

        根据模板配置自动调整内容排版，包括：
        - 标题自适应字号
        - 正文分栏处理
        - 防溢出检测
        - 留白优化

        Args:
            slide_data: 幻灯片数据字典，包含标题、正文、图片等
            template_config: 模板配置，包含容器尺寸、默认字号、边距等

        Returns:
            优化后的幻灯片数据字典
        """
        optimized = slide_data.copy()

        # 获取容器配置 (兼容 dict 和 TemplateConfig)
        def get_cfg(key, default):
            if isinstance(template_config, dict):
                return template_config.get(key, default)
            return getattr(template_config, key, default)

        content_width = get_cfg('slide_width', 13.333) - 2 * get_cfg('slide_margin', 0.8)
        content_height = get_cfg('slide_height', 7.5) - 2 * get_cfg('slide_margin', 0.8)
        margin = get_cfg('slide_margin', 0.8)
        available_width = content_width
        available_height = content_height

        # 优化标题
        if 'title' in slide_data and slide_data['title']:
            title_font = self.adjust_font_size(
                slide_data['title'],
                max_width=available_width,
                min_size=getattr(template_config, 'title_size', 24) - 8,
                max_size=getattr(template_config, 'title_size', 24) + 12,
            )
            optimized['title'] = {
                'text': slide_data['title'],
                'font_size': title_font,
            }
            available_height -= Pt(title_font).inches * 1.5
            available_height = max(available_height, 0.5)  # 保证至少 0.5 英寸可用高度

        # 优化正文
        if 'body' in slide_data and slide_data['body']:
            body_text = slide_data['body']
            
            body_font_size = getattr(template_config, 'body_size', 16)
            line_spacing = getattr(template_config, 'line_spacing', 1.3)

            # 分栏处理
            num_columns = 1
            if num_columns > 1:
                columns = self.split_to_columns(body_text, num_columns)
                optimized['body'] = {
                    'columns': columns,
                    'font_size': body_font_size,
                    'line_spacing': line_spacing,
                }
            else:
                # 自适应字号
                body_font = self.adjust_font_size(
                    body_text,
                    max_width=available_width,
                    min_size=body_font_size - 4,
                    max_size=body_font_size + 8,
                )

                # 防溢出检测
                estimated_height = self._analyzer.estimate_display_height(
                    text=body_text,
                    font_size=body_font,
                    line_spacing=line_spacing,
                    max_width=available_width,
                )

                if estimated_height > available_height:
                    height_diff = estimated_height - available_height
                    # 按比例缩小字号
                    scale_factor = available_height / estimated_height
                    body_font = max(
                        12,
                        int(body_font * scale_factor * 0.9),
                    )

                optimized['body'] = {
                    'text': body_text,
                    'font_size': body_font,
                    'line_spacing': line_spacing,
                }

        # 优化图片
        if 'images' in slide_data and slide_data['images']:
            optimized['images'] = self._optimize_image_layout(
                slide_data['images'],
                available_width,
                available_height,
                template_config,
            )

        # 留白优化
        optimized = self.optimize_whitespace(optimized, template_config)

        return optimized

    def adjust_font_size(
        self,
        text: str,
        max_width: float = 6.0,
        min_size: int = 12,
        max_size: int = 44,
    ) -> int:
        """自适应计算最佳字号

        通过二分查找找到在给定宽度下能完整显示文本的最大字号。

        Args:
            text: 待调整字号的文本
            max_width: 容器最大宽度（英寸）
            min_size: 最小字号（Pt）
            max_size: 最大字号（Pt）

        Returns:
            最优字号大小（Pt）
        """
        if not text:
            return max_size

        density = self._analyzer.analyze_text_density(text)
        effective_length = density['effective_length']

        # 二分查找最优字号
        low, high = min_size, max_size
        best_size = min_size

        while low <= high:
            mid = (low + high) // 2

            # 估算当前字号下单行能容纳的字符数
            char_width_pt = mid * 0.5
            max_width_pt = Inches(max_width).pt
            chars_per_row = max(1, int(max_width_pt / char_width_pt))

            # 中文占 2 个字符宽度
            if density['chinese_ratio'] > 0.5:
                chars_per_row = max(1, chars_per_row // 2)

            # 判断是否单行能放下
            if effective_length <= chars_per_row:
                best_size = mid
                low = mid + 1
            else:
                # 计算需要几行
                lines = math.ceil(effective_length / max(chars_per_row, 1))
                # 多行文本使用更大的行间距
                if lines <= 3:
                    best_size = mid
                    low = mid + 1
                else:
                    high = mid - 1

        return best_size

    def split_to_columns(
        self,
        content: str,
        num_columns: int = 2,
    ) -> List[Dict[str, Any]]:
        """将内容分割为多栏显示

        智能分割文本，尽量保证分界点在段落/句子边界。

        Args:
            content: 待分割的文本内容
            num_columns: 分栏数量

        Returns:
            每栏内容的列表，包含文本和排版提示
        """
        if not content or num_columns <= 1:
            return [{'text': content, 'width_ratio': 1.0}]

        # 尝试按段落分割
        paragraphs = re.split(r'\n\s*\n', content.strip())
        if len(paragraphs) < num_columns:
            # 段落不够分栏，按句子分割
            sentences = re.split(r'(?<=[。！？.!?])\s*', content.strip())
            items = sentences if len(sentences) >= num_columns else paragraphs
        else:
            items = paragraphs

        # 计算每段的有效长度用于均衡分配
        item_lengths = [self._analyzer.analyze_text_density(item)['effective_length'] for item in items]
        total_length = sum(item_lengths)
        target_per_column = total_length / num_columns

        columns: List[Dict[str, Any]] = []
        current_column_text = []
        current_column_length = 0
        column_index = 0

        for i, item in enumerate(items):
            current_column_text.append(item)
            current_column_length += item_lengths[i]

            # 判断是否需要换栏
            should_split = (
                column_index < num_columns - 1 and
                current_column_length >= target_per_column
            )

            # 剩余段落不够填满剩余栏时，也分割
            remaining_items = len(items) - i - 1
            remaining_columns = num_columns - column_index - 1
            force_split = remaining_items >= remaining_columns and remaining_columns > 0

            if should_split or force_split:
                col_text = '\n\n'.join(current_column_text).strip()
                columns.append({
                    'text': col_text,
                    'width_ratio': 1.0 / num_columns,
                    'length': current_column_length,
                })
                current_column_text = []
                current_column_length = 0
                column_index += 1

        # 最后一栏
        if current_column_text:
            col_text = '\n\n'.join(current_column_text).strip()
            columns.append({
                'text': col_text,
                'width_ratio': 1.0 / num_columns,
                'length': current_column_length,
            })

        # 确保栏数正确
        while len(columns) < num_columns:
            columns.append({'text': '', 'width_ratio': 1.0 / num_columns, 'length': 0})

        return columns

    def prevent_overflow(
        self,
        text: str,
        max_height: float,
        font_size: int,
        line_spacing: float = 1.5,
        max_width: float = 6.0,
    ) -> Dict[str, Any]:
        """防溢出检测

        检测文本是否会在给定容器高度下溢出，并提供处理建议。

        Args:
            text: 待检测的文本
            max_height: 容器最大高度（英寸）
            font_size: 当前字号（Pt）
            line_spacing: 行高倍数
            max_width: 容器最大宽度（英寸）

        Returns:
            检测结果，包含是否溢出、建议字号、建议截断位置等
        """
        result = {
            'will_overflow': False,
            'original_font_size': font_size,
            'recommended_font_size': font_size,
            'text_to_display': text,
            'truncate_position': None,
            'fits': True,
            'adjusted': False,
        }

        if not text:
            return result

        # 估算当前配置下的显示高度
        estimated_height = self._analyzer.estimate_display_height(
            text=text,
            font_size=font_size,
            line_spacing=line_spacing,
            max_width=max_width,
        )

        if estimated_height <= max_height:
            return result

        # 会发生溢出，计算推荐字号
        scale_factor = max_height / estimated_height
        recommended_font = max(8, int(font_size * scale_factor))
        result['recommended_font_size'] = recommended_font

        # 重新估算缩小字号后的高度
        new_height = self._analyzer.estimate_display_height(
            text=text,
            font_size=recommended_font,
            line_spacing=line_spacing,
            max_width=max_width,
        )

        # 如果即使缩小字号仍然溢出，建议截断
        if new_height > max_height:
            # 计算最大可显示字符数
            density = self._analyzer.analyze_text_density(text)
            max_chars = int(density['total_chars'] * (max_height / new_height) * 0.9)

            # 在安全位置截断（优先段落边界，其次句子边界，最后单词边界）
            truncated = self._truncate_at_boundary(text, max_chars)
            result['text_to_display'] = truncated
            result['truncate_position'] = len(truncated)

        result['will_overflow'] = True
        return result

    def optimize_whitespace(
        self,
        slide_data: Dict[str, Any],
        template_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """留白优化

        调整幻灯片各元素之间的间距，确保视觉平衡。

        Args:
            slide_data: 幻灯片数据
            template_config: 模板配置

        Returns:
            优化后的幻灯片数据，包含间距配置
        """
        optimized = slide_data.copy()
        margin = getattr(template_config, 'slide_margin', 0.5)
        element_spacing = getattr(template_config, 'paragraph_spacing', 0.3)

        # 计算各元素位置
        raw_layout = optimized.get('layout', {})
        if not isinstance(raw_layout, dict):
            raw_layout = {}
        layout = raw_layout

        # 标题区域
        if 'title' in optimized:
            layout['title'] = {
                'top': margin,
                'left': margin,
                'right': margin,
                'height': Pt(optimized['title']['font_size']).inches * 1.5,
            }

        # 内容区域
        if 'body' in optimized:
            header_end = layout.get('title', {}).get('height', 0) + margin + element_spacing
            layout['body'] = {
                'top': header_end,
                'left': margin,
                'right': margin,
                'bottom': margin,
            }

        # 图片区域
        if 'images' in optimized and isinstance(optimized['images'], list):
            body_bottom = layout.get('body', {}).get('bottom', margin)
            image_count = len(optimized['images'])
            if image_count > 0:
                layout['images'] = {
                    'spacing': element_spacing,
                    'columns': min(image_count, 3),
                }

        optimized['layout'] = layout
        optimized['spacing'] = {
            'margin': margin,
            'element_spacing': element_spacing,
        }

        return optimized

    def _optimize_image_layout(
        self,
        images: List[Any],
        available_width: float,
        available_height: float,
        template_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """优化图片布局

        根据图片数量和可用空间自动计算最佳布局方式。
        """
        num_images = len(images)
        if num_images == 0:
            return []

        image_config = getattr(template_config, 'images', {})

        if num_images == 1:
            return [{
                'source': images[0],
                'position': 'center',
                'width': min(available_width * 0.8, available_height * 0.8),
                'height': 'auto',
            }]

        # 计算最佳行列数
        cols = min(num_images, math.ceil(math.sqrt(num_images * (available_width / max(available_height, 0.1)))))
        cols = min(cols, 3)
        rows = math.ceil(num_images / cols)

        spacing = 0.2
        cell_width = (available_width - spacing * (cols - 1)) / cols
        cell_height = (available_height - spacing * (rows - 1)) / rows

        layout = []
        for i, img in enumerate(images):
            row = i // cols
            col = i % cols
            layout.append({
                'source': img,
                'position': f'grid-{row}-{col}',
                'width': cell_width,
                'height': cell_height,
            })

        return layout

    @staticmethod
    def _truncate_at_boundary(text: str, max_chars: int) -> str:
        """在安全边界处截断文本

        优先在段落边界截断，其次在句子边界，最后在单词边界。
        """
        if len(text) <= max_chars:
            return text

        # 搜索段落边界
        paragraph_end = text.rfind('\n\n', 0, max_chars)
        if paragraph_end > max_chars * 0.5:
            return text[:paragraph_end].rstrip() + '...'

        # 搜索句子边界
        sentence_end = max(
            text.rfind('。', 0, max_chars),
            text.rfind('！', 0, max_chars),
            text.rfind('？', 0, max_chars),
            text.rfind('.', 0, max_chars),
        )
        if sentence_end > max_chars * 0.5:
            return text[:sentence_end + 1].rstrip() + '...'

        # 搜索单词边界
        word_end = text.rfind(' ', 0, max_chars)
        if word_end > max_chars * 0.5:
            return text[:word_end].rstrip() + '...'

        # 强制截断
        return text[:max_chars].rstrip() + '...'


class LayoutUtils:
    """布局工具函数

    提供文字适配估算、最优字号计算、内容格式化等静态工具方法。
    """

    @staticmethod
    def text_fits(text: str, font_size: int, max_width: float) -> bool:
        """估算文字是否能在给定宽度内单行显示

        Args:
            text: 待检测的文本
            font_size: 字号（Pt）
            max_width: 容器最大宽度（英寸）

        Returns:
            是否能单行显示
        """
        if not text:
            return True

        analyzer = TextAnalyzer()
        density = analyzer.analyze_text_density(text)
        effective_length = density['effective_length']

        # 每字符宽度约 0.5 * font_size (pt)
        char_width_pt = font_size * 0.5
        max_width_pt = Inches(max_width).pt
        max_chars = int(max_width_pt / char_width_pt)

        return effective_length <= max_chars

    @staticmethod
    def calculate_optimal_font_size(text_length: int, container_width: float) -> int:
        """根据文本长度和容器宽度计算最优字号

        基于经验公式：字号 = (容器宽度 * 72) / (文本长度 * 字符宽度系数)

        Args:
            text_length: 文本有效长度（字符数）
            container_width: 容器宽度（英寸）

        Returns:
            最优字号大小（Pt），范围 10-44
        """
        if text_length <= 0:
            return 44

        # 经验公式
        container_pt = Inches(container_width).pt
        # 假设中文是主要字符类型，每个字符约 0.8pt 宽度
        char_width_factor = 0.8

        optimal = int(container_pt / (text_length * char_width_factor))

        # 限制在合理范围内
        return max(10, min(44, optimal))

    @staticmethod
    def get_layout_for_slide_type(slide_type: str) -> str:
        """根据幻灯片类型获取推荐布局名称"""
        layout_map = {
            'title': 'TITLE_SLIDE',
            'content': 'CONTENT_SLIDE',
            'section': 'SECTION_DIVIDER',
            'end': 'END_SLIDE'
        }
        return layout_map.get(slide_type.lower(), 'CONTENT_SLIDE')

    @staticmethod
    def calculate_content_area(slide_width: float, slide_height: float, margin: float) -> Dict[str, float]:
        """计算幻灯片内容区域"""
        return {
            'width': slide_width - 2 * margin,
            'height': slide_height - 2 * margin,
        }

    @staticmethod
    def format_slide_content(
        slide_type: str,
        content: Dict[str, Any],
        template_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """格式化幻灯片内容

        根据幻灯片类型和模板配置，标准化内容格式。

        Args:
            slide_type: 幻灯片类型，如 'title', 'content', 'two_column', 'image_text' 等
            content: 原始内容数据
            template_config: 模板配置

        Returns:
            格式化后的内容字典
        """
        formatter = getattr(LayoutUtils, f'_format_{slide_type}', LayoutUtils._format_default)
        return formatter(content, template_config)

    @staticmethod
    def _format_title(content: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, Any]:
        """格式化标题页"""
        title = content.get('title', '')
        subtitle = content.get('subtitle', '')

        return {
            'type': 'title',
            'title': {
                'text': title,
                'font_size': getattr(template_config, 'title_size', 44),
                'alignment': 'center',
            },
            'subtitle': {
                'text': subtitle,
                'font_size': getattr(template_config, 'subtitle_size', 24),
                'alignment': 'center',
            } if subtitle else None,
        }

    @staticmethod
    def _format_content(content: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, Any]:
        """格式化内容页"""
        title = content.get('title', '')
        body = content.get('body', content.get('text', ''))

        return {
            'type': 'content',
            'title': {
                'text': title,
                'font_size': getattr(template_config, 'title_size', 32),
            },
            'body': {
                'text': body,
                'font_size': getattr(template_config, 'body_size', 18),
                'line_spacing': getattr(template_config, 'line_spacing', 1.5),
                'bullets': False,
            },
        }

    @staticmethod
    def _format_two_column(content: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, Any]:
        """格式化双栏页"""
        left = content.get('left', content.get('column_1', ''))
        right = content.get('right', content.get('column_2', ''))

        return {
            'type': 'two_column',
            'title': content.get('title', ''),
            'columns': {
                'left': {
                    'text': left,
                    'width_ratio': content.get('left_ratio', 0.5),
                },
                'right': {
                    'text': right,
                    'width_ratio': content.get('right_ratio', 0.5),
                },
            },
        }

    @staticmethod
    def _format_image_text(content: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, Any]:
        """格式化图文混排页"""
        image = content.get('image', '')
        text = content.get('text', content.get('body', ''))
        image_position = content.get('image_position', 'left')

        return {
            'type': 'image_text',
            'title': content.get('title', ''),
            'image': {
                'source': image,
                'position': image_position,
                'width_ratio': content.get('image_ratio', 0.4),
            } if image else None,
            'text': {
                'text': text,
                'font_size': getattr(template_config, 'body_size', 16),
            },
        }

    @staticmethod
    def _format_default(content: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, Any]:
        """默认格式化"""
        return {
            'type': 'custom',
            'content': content,
            'template': template_config,
        }
