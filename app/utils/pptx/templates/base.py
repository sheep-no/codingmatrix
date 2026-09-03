"""
PPT 模板基类 - 定义模板数据结构和接口
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any, Tuple


class SlideLayout(Enum):
    """幻灯片布局类型"""
    TITLE_ONLY = "title_only"              # 仅标题（封面/章节）
    TITLE_CONTENT = "title_content"        # 标题 + 内容
    TITLE_IMAGE = "title_image"            # 标题 + 图片
    TITLE_TWO_COLUMN = "title_two_column"  # 标题 + 双栏
    TITLE_BULLET = "title_bullet"          # 标题 + 要点列表
    TITLE_CHART = "title_chart"            # 标题 + 图表
    FULL_IMAGE = "full_image"              # 全屏图片
    END_SLIDE = "end_slide"                # 结束页


class TemplateCategory(Enum):
    """模板分类"""
    BUSINESS = "business"      # 商务汇报
    ACADEMIC = "academic"      # 学术论文
    PITCH = "pitch"            # 产品路演
    TECH = "tech"              # 科技演示
    EDUCATION = "education"    # 教育培训
    MINIMAL = "minimal"        # 简约风格


@dataclass
class TemplateConfig:
    """模板配置"""
    # 基本信息
    template_id: str
    name: str
    name_zh: str
    category: TemplateCategory
    description: str

    # 配色方案
    primary_color: str = "1F4E79"      # 主色调
    secondary_color: str = "2E75B6"    # 辅助色
    accent_color: str = "70AD47"       # 强调色
    background_color: str = "FFFFFF"   # 背景色
    text_color: str = "333333"         # 文字色
    light_text_color: str = "666666"   # 浅色文字

    # 字体配置
    title_font: str = "微软雅黑"
    body_font: str = "微软雅黑"
    title_font_en: str = "Arial"       # 英文标题字体
    body_font_en: str = "Calibri"      # 英文字正文字体

    # 字号配置（磅值）
    title_size: int = 32
    subtitle_size: int = 20
    heading_size: int = 24
    body_size: int = 16
    bullet_size: int = 14
    caption_size: int = 12

    # 间距配置（英寸）
    slide_margin: float = 0.8           # 页面边距
    title_margin_bottom: float = 0.4    # 标题底部边距
    paragraph_spacing: float = 0.15     # 段落间距
    bullet_indent: float = 0.3          # 列表缩进
    line_spacing: float = 1.3           # 行距倍数

    # 装饰配置
    has_header_bar: bool = True         # 顶部装饰条
    has_footer_bar: bool = True         # 底部装饰条
    has_corner_decor: bool = False      # 角标装饰
    has_page_number: bool = True        # 页码
    slide_width: float = 13.333         # 幻灯片宽度（英寸）
    slide_height: float = 7.5           # 幻灯片高度（英寸）

    # 布局变体
    layouts: Dict[SlideLayout, Dict[str, Any]] = field(default_factory=dict)

    def copy(self) -> "TemplateConfig":
        """复制模板配置"""
        return TemplateConfig(
            template_id="custom_" + self.template_id,
            name=self.name + " (Custom)",
            name_zh=self.name_zh + " (自定义)",
            category=self.category,
            description=self.description,
            primary_color=self.primary_color,
            secondary_color=self.secondary_color,
            accent_color=self.accent_color,
            background_color=self.background_color,
            text_color=self.text_color,
            light_text_color=self.light_text_color,
            title_font=self.title_font,
            body_font=self.body_font,
            title_font_en=self.title_font_en,
            body_font_en=self.body_font_en,
            title_size=self.title_size,
            subtitle_size=self.subtitle_size,
            heading_size=self.heading_size,
            body_size=self.body_size,
            bullet_size=self.bullet_size,
            caption_size=self.caption_size,
            slide_margin=self.slide_margin,
            title_margin_bottom=self.title_margin_bottom,
            paragraph_spacing=self.paragraph_spacing,
            bullet_indent=self.bullet_indent,
            line_spacing=self.line_spacing,
            has_header_bar=self.has_header_bar,
            has_footer_bar=self.has_footer_bar,
            has_corner_decor=self.has_corner_decor,
            has_page_number=self.has_page_number,
            slide_width=self.slide_width,
            slide_height=self.slide_height,
            layouts=dict(self.layouts),
        )


class TemplateBase:
    """模板基类，所有具体模板需继承此类"""

    @property
    def config(self) -> TemplateConfig:
        """返回模板配置，子类必须实现"""
        raise NotImplementedError

    def get_layout(self, slide_type: SlideLayout) -> Dict[str, Any]:
        """获取指定布局的配置"""
        return self.config.layouts.get(slide_type, {})

    def apply_decorations(self, prs, slide, template_config: TemplateConfig, page_num: int, total_pages: int):
        """应用装饰元素（页眉/页脚/页码/角标等）"""
        from pptx.util import Inches
        from pptx.dml.color import RGBColor

        # 顶部装饰条
        if template_config.has_header_bar:
            self._add_header_bar(prs, slide, template_config)

        # 底部装饰条
        if template_config.has_footer_bar:
            self._add_footer_bar(prs, slide, template_config)

        # 页码
        if template_config.has_page_number:
            self._add_page_number(slide, prs, template_config, page_num, total_pages)

        # 角标装饰
        if template_config.has_corner_decor:
            self._add_corner_decor(slide, prs, template_config)

    def _add_header_bar(self, prs, slide, config: TemplateConfig):
        """添加顶部装饰条"""
        from pptx.util import Inches
        from pptx.dml.color import RGBColor

        bar_height = Inches(0.12)
        header_bar = slide.shapes.add_shape(
            1,  # MSO_SHAPE.RECTANGLE
            Inches(0), Inches(0),
            Inches(config.slide_width), bar_height
        )
        header_bar.fill.solid()
        header_bar.fill.fore_color.rgb = RGBColor.from_string(config.primary_color)
        header_bar.line.fill.background()

        # 添加左侧装饰线
        accent_line = slide.shapes.add_shape(
            1,
            Inches(0.5), Inches(0.12),
            Inches(1.5), Inches(0.06)
        )
        accent_line.fill.solid()
        accent_line.fill.fore_color.rgb = RGBColor.from_string(config.accent_color)
        accent_line.line.fill.background()

    def _add_footer_bar(self, prs, slide, config: TemplateConfig):
        """添加底部装饰条"""
        from pptx.util import Inches
        from pptx.dml.color import RGBColor

        footer_height = Inches(0.08)
        footer_bar = slide.shapes.add_shape(
            1,
            Inches(0), Inches(config.slide_height) - footer_height,
            Inches(config.slide_width), footer_height
        )
        footer_bar.fill.solid()
        footer_bar.fill.fore_color.rgb = RGBColor.from_string(config.secondary_color)
        footer_bar.line.fill.background()

    def _add_page_number(self, slide, prs, config: TemplateConfig, page_num: int, total_pages: int):
        """添加页码"""
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        page_text = slide.shapes.add_textbox(
            Inches(config.slide_width) - Inches(1.2),
            Inches(config.slide_height) - Inches(0.45),
            Inches(1.0), Inches(0.3)
        )
        tf = page_text.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = f"{page_num} / {total_pages}"
        p.font.size = Pt(config.caption_size)
        p.font.color.rgb = RGBColor.from_string(config.light_text_color)
        p.alignment = PP_ALIGN.RIGHT

    def _add_corner_decor(self, slide, prs, config: TemplateConfig):
        """添加角标装饰"""
        from pptx.util import Inches
        from pptx.dml.color import RGBColor

        decor_size = Inches(1.5)
        decor = slide.shapes.add_shape(
            1,
            Inches(config.slide_width) - decor_size,
            Inches(config.slide_height) - decor_size - Inches(0.3),
            decor_size, decor_size
        )
        decor.fill.solid()
        decor.fill.fore_color.rgb = RGBColor.from_string(config.primary_color)
        decor.fill.fore_color.brightness = 0.85  # 85% 透明度效果
        decor.line.fill.background()
