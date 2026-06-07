"""
自定义母版解析器 - 支持用户上传 .pptx 模板文件并自动解析配色、字体、布局等信息
"""
import logging
from dataclasses import replace
from typing import Dict, List, Optional, Any

from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

from app.utils.pptx.templates import TemplateConfig, TemplateCategory

logger = logging.getLogger(__name__)


class CustomTemplateParser:
    """自定义模板解析器 - 从 .pptx 母版中提取配置"""

    def __init__(self, default_category: TemplateCategory = TemplateCategory.BUSINESS):
        self._default_category = default_category
        self._extracted_colors: Dict[str, str] = {}
        self._extracted_fonts: Dict[str, str] = {}
        self._extracted_layouts: Dict[str, Dict[str, Any]] = {}
        self._extracted_decorations: Dict[str, Any] = {}
        self._theme_colors: List[str] = []
        self._slide_width: float = 13.333
        self._slide_height: float = 7.5

    def parse_template_file(self, template_path: str) -> TemplateConfig:
        """解析模板文件，提取完整配置

        Args:
            template_path: .pptx 模板文件路径

        Returns:
            TemplateConfig 解析后的模板配置

        Raises:
            ValueError: 模板文件不存在或无效
            RuntimeError: 解析过程中发生未知错误
        """
        import os

        if not os.path.isfile(template_path):
            raise ValueError(f"模板文件不存在：{template_path}")

        try:
            prs = PptxPresentation(template_path)
        except Exception as e:
            raise ValueError(f"无法打开模板文件：{template_path}, 错误：{e}")

        try:
            self._slide_width = Emu(prs.slide_width).pt / 72.0
            self._slide_height = Emu(prs.slide_height).pt / 72.0

            if prs.slide_masters:
                master = prs.slide_masters[0]
                self._extracted_colors = self.extract_colors(master)
                self._extracted_fonts = self.extract_fonts(master)
                self._theme_colors = self.extract_theme_colors(prs)
                self._extracted_decorations = self.extract_decorations(prs)

                for layout in master.slide_layouts:
                    layout_name = layout.name.lower() if layout.name else "unknown"
                    self._extracted_layouts[layout_name] = self.analyze_slide_master(layout)

            return self.generate_template_config()

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"解析模板文件时发生错误：{template_path}, 错误：{e}")
        finally:
            try:
                prs.close()
            except Exception:
                pass

    def extract_colors(self, slide) -> Dict[str, str]:
        """从母版或幻灯片中提取配色方案

        优先从主题提取，其次从形状填充色提取。

        Args:
            slide: slide_master 或 slide 对象

        Returns:
            配色字典，包含 primary/secondary/accent/background/text 等颜色
        """
        colors: Dict[str, str] = {
            "primary_color": "1F4E79",
            "secondary_color": "2E75B6",
            "accent_color": "70AD47",
            "background_color": "FFFFFF",
            "text_color": "333333",
            "light_text_color": "666666",
        }

        try:
            self._extract_from_theme_colors(slide, colors)
        except Exception as e:
            logger.debug(f"从主题提取配色失败，回退到形状分析：{e}")

        try:
            self._extract_from_shapes(slide, colors)
        except Exception as e:
            logger.debug(f"从形状分析配色时发生异常：{e}")

        return colors

    def _extract_from_theme_colors(self, slide, colors: Dict[str, str]):
        """从主题提取颜色"""
        if hasattr(slide, "theme") and slide.theme is not None:
            tc = slide.theme.theme_colors
            if tc is not None:
                for idx, key in [
                    (0, "primary_color"),
                    (1, "text_color"),
                    (2, "secondary_color"),
                    (3, "accent_color"),
                    (4, "light_text_color"),
                    (6, "background_color"),
                    (7, "text_color"),
                ]:
                    try:
                        c = tc[idx]
                        if c is not None and hasattr(c, "rgb") and c.rgb is not None:
                            colors[key] = str(c.rgb).upper().replace("#", "")
                    except (IndexError, TypeError):
                        pass

    def _extract_from_shapes(self, slide, colors: Dict[str, str]):
        """从形状填充色和文字颜色中统计提取配色"""
        color_freq: Dict[str, int] = {}
        text_color_freq: Dict[str, int] = {}

        shapes = getattr(slide, "shapes", [])
        for shape in shapes:
            fc = self._get_fill_color(shape)
            if fc and fc != "FFFFFF" and fc != "000000":
                color_freq[fc] = color_freq.get(fc, 0) + 1

            tc = self._get_text_color(shape)
            if tc and tc != "000000":
                text_color_freq[tc] = text_color_freq.get(tc, 0) + 1

        if color_freq:
            sorted_colors = sorted(color_freq.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_colors) >= 1:
                colors["primary_color"] = sorted_colors[0][0]
            if len(sorted_colors) >= 2:
                colors["secondary_color"] = sorted_colors[1][0]
            if len(sorted_colors) >= 3:
                colors["accent_color"] = sorted_colors[2][0]

        if text_color_freq:
            sorted_text = sorted(text_color_freq.items(), key=lambda x: x[1], reverse=True)
            colors["text_color"] = sorted_text[0][0]
            if len(sorted_text) >= 2:
                colors["light_text_color"] = sorted_text[1][0]

    def _get_fill_color(self, shape) -> Optional[str]:
        """获取形状的填充色（HEX 格式）"""
        try:
            fill = shape.fill
            if fill is None:
                return None
            if not hasattr(fill, "fore_color"):
                return None
            fc = fill.fore_color
            if fc is None:
                return None
            if hasattr(fc, "rgb") and fc.rgb is not None:
                return str(fc.rgb).upper().replace("#", "")
        except (AttributeError, TypeError):
            pass
        return None

    def _get_text_color(self, shape) -> Optional[str]:
        """获取形状文字颜色（HEX 格式）"""
        try:
            if not shape.has_text_frame:
                return None
            tf = shape.text_frame
            for para in tf.paragraphs:
                for run in para.runs:
                    if hasattr(run, "font") and run.font is not None:
                        if hasattr(run.font, "color") and run.font.color is not None:
                            if hasattr(run.font.color, "rgb") and run.font.color.rgb is not None:
                                c = run.font.color.rgb
                                return str(c).upper().replace("#", "")
        except (AttributeError, TypeError):
            pass
        return None

    def extract_fonts(self, slide) -> Dict[str, str]:
        """从母版中提取字体配置

        Args:
            slide: slide_master 或 slide 对象

        Returns:
            字体配置字典，包含中英文字体
        """
        fonts: Dict[str, str] = {
            "title_font": "微软雅黑",
            "body_font": "微软雅黑",
            "title_font_en": "Arial",
            "body_font_en": "Calibri",
        }

        try:
            self._extract_from_theme_fonts(slide, fonts)
        except Exception as e:
            logger.debug(f"从主题提取字体失败，回退到形状分析：{e}")

        try:
            self._extract_from_shapes_fonts(slide, fonts)
        except Exception as e:
            logger.debug(f"从形状提取字体时发生异常：{e}")

        return fonts

    def _extract_from_theme_fonts(self, slide, fonts: Dict[str, str]):
        """从主题字体方案提取字体"""
        if hasattr(slide, "theme") and slide.theme is not None:
            theme = slide.theme
            if hasattr(theme, "_element"):
                el = theme._element
                font_scheme = el.find(qn("a:fontScheme"))
                if font_scheme is not None:
                    maj_font = font_scheme.find(qn("a:majorFont"))
                    min_font = font_scheme.find(qn("a:minorFont"))

                    if maj_font is not None:
                        latin = maj_font.find(qn("a:latin"))
                        ea = maj_font.find(qn("a:ea"))
                        if latin is not None:
                            fonts["title_font_en"] = latin.get("typeface", "Arial")
                        if ea is not None:
                            fonts["title_font"] = ea.get("typeface", "微软雅黑")

                    if min_font is not None:
                        latin = min_font.find(qn("a:latin"))
                        ea = min_font.find(qn("a:ea"))
                        if latin is not None:
                            fonts["body_font_en"] = latin.get("typeface", "Calibri")
                        if ea is not None:
                            fonts["body_font"] = ea.get("typeface", "微软雅黑")

    def _extract_from_shapes_fonts(self, slide, fonts: Dict[str, str]):
        """从形状文字属性提取字体"""
        title_fonts = []
        body_fonts = []

        shapes = getattr(slide, "shapes", [])
        for shape in shapes:
            if not shape.has_text_frame:
                continue

            for para in shape.text_frame.paragraphs:
                level = para.level if hasattr(para, "level") else -1

                for run in para.runs:
                    if run.font and run.font.name:
                        if level == 0:
                            title_fonts.append(run.font.name)
                        else:
                            body_fonts.append(run.font.name)

        if title_fonts:
            cn_fonts = [f for f in title_fonts if any(
                "\u4e00" <= c <= "\u9fff" for c in f)]
            en_fonts = [f for f in title_fonts if not any(
                "\u4e00" <= c <= "\u9fff" for c in f)]
            if cn_fonts:
                fonts["title_font"] = cn_fonts[0]
            if en_fonts:
                fonts["title_font_en"] = en_fonts[0]

        if body_fonts:
            cn_fonts = [f for f in body_fonts if any(
                "\u4e00" <= c <= "\u9fff" for c in f)]
            en_fonts = [f for f in body_fonts if not any(
                "\u4e00" <= c <= "\u9fff" for c in f)]
            if cn_fonts:
                fonts["body_font"] = cn_fonts[0]
            if en_fonts:
                fonts["body_font_en"] = en_fonts[0]

    def extract_layout_info(self, slide) -> Dict[str, Any]:
        """提取布局信息

        Args:
            slide: slide_layout 对象

        Returns:
            布局信息字典，包含 placeholders、margins 等
        """
        info: Dict[str, Any] = {
            "placeholders": [],
            "has_title": False,
            "has_content": False,
            "margins": {},
            "shape_count": 0,
        }

        try:
            shapes = getattr(slide, "shapes", [])
            info["shape_count"] = len(shapes)

            for shape in shapes:
                ph_info = self._get_placeholder_info(shape)
                if ph_info:
                    info["placeholders"].append(ph_info)
                    if ph_info.get("type") in ("title", "centerTitle", "subTitle"):
                        info["has_title"] = True
                    if ph_info.get("type") in ("body", "content", "obj"):
                        info["has_content"] = True

            margins = self._detect_margins(shapes)
            info["margins"] = margins

        except Exception as e:
            logger.debug(f"提取布局信息时发生异常：{e}")

        return info

    def _get_placeholder_info(self, shape) -> Optional[Dict[str, Any]]:
        """获取占位符信息"""
        try:
            if not shape.is_placeholder:
                return None

            ph = shape.placeholder_format
            ph_type = None
            if hasattr(ph, "type"):
                ph_type = str(ph.type) if ph.type is not None else "unknown"

            left = 0.0
            top = 0.0
            width = 0.0
            height = 0.0

            try:
                left = Inches(shape.left.inches).inches if shape.left else 0.0
                top = Inches(shape.top.inches).inches if shape.top else 0.0
                width = Inches(shape.width.inches).inches if shape.width else 0.0
                height = Inches(shape.height.inches).inches if shape.height else 0.0
            except (AttributeError, TypeError):
                pass

            return {
                "idx": ph.idx if hasattr(ph, "idx") else -1,
                "type": ph_type,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "name": shape.name,
            }

        except (AttributeError, TypeError):
            return None

    def _detect_margins(self, shapes) -> Dict[str, float]:
        """从形状位置推断边距"""
        margins: Dict[str, float] = {}

        for shape in shapes:
            try:
                if shape.is_placeholder:
                    ph = shape.placeholder_format
                    ph_type = str(ph.type) if ph.type is not None else ""

                    if ph_type in ("title", "centerTitle", "subTitle"):
                        if shape.left:
                            margins["title_margin_left"] = shape.left.inches
                        if shape.top and shape.height:
                            margins["title_margin_bottom"] = shape.top.inches + shape.height.inches + 0.2

                    if ph_type in ("body", "content"):
                        if shape.left:
                            margins["body_margin_left"] = shape.left.inches
                        if shape.top:
                            margins["body_margin_top"] = shape.top.inches

            except (AttributeError, TypeError):
                pass

        return margins

    def extract_decorations(self, prs) -> Dict[str, Any]:
        """提取装饰元素配置

        检测母版中的页眉条、页脚条、页码、角标等装饰元素。

        Args:
            prs: Presentation 对象

        Returns:
            装饰元素配置字典
        """
        decorations: Dict[str, Any] = {
            "has_header_bar": False,
            "has_footer_bar": False,
            "has_corner_decor": False,
            "has_page_number": False,
            "header_bar_color": None,
            "footer_bar_color": None,
        }

        if not prs.slide_masters:
            return decorations

        for master in prs.slide_masters:
            for shape in master.shapes:
                self._analyze_shape_for_decoration(shape, decorations)

        return decorations

    def _analyze_shape_for_decoration(self, shape, decorations: Dict[str, Any]):
        """分析形状是否为装饰元素"""
        try:
            bottom_threshold = Inches(0.15).emu
            top_threshold = Inches(0.15).emu
            corner_size = Inches(2.0).emu
            page_size = Inches(1.5).emu

            if shape.shape_type and hasattr(shape, "fill"):
                pos = shape.position if hasattr(shape, "position") else None

                if pos:
                    if pos.top < top_threshold:
                        color = self._get_fill_color(shape)
                        if color:
                            decorations["has_header_bar"] = True
                            decorations["header_bar_color"] = color

                    slide_h = Emu(int(self._slide_height * 914400))
                    if pos.top > slide_h - bottom_threshold:
                        color = self._get_fill_color(shape)
                        if color:
                            decorations["has_footer_bar"] = True
                            decorations["footer_bar_color"] = color

            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text and ("<#>" in text or "{page}" in text or "of" in text.lower() or "/" in text or "num" in text.lower()):
                    decorations["has_page_number"] = True

            if hasattr(shape, "width") and hasattr(shape, "height"):
                if shape.width < corner_size and shape.height < corner_size:
                    if hasattr(shape, "left") and hasattr(shape, "top"):
                        slide_w = int(self._slide_width * 914400)
                        slide_h = int(self._slide_height * 914400)
                        is_right_left = shape.left and abs(shape.left - slide_w) < page_size
                        is_bottom = shape.top and abs(shape.top - slide_h) < page_size
                        if is_right_left and is_bottom:
                            decorations["has_corner_decor"] = True

        except (AttributeError, TypeError):
            pass

    def extract_theme_colors(self, prs) -> List[str]:
        """提取主题色列表

        从主题中提取完整的 12 色调色板。

        Args:
            prs: Presentation 对象

        Returns:
            主题色 HEX 列表
        """
        theme_colors: List[str] = []

        if prs.slide_masters:
            master = prs.slide_masters[0]
            if hasattr(master, "theme") and master.theme is not None:
                tc = master.theme.theme_colors
                if tc is not None:
                    for i in range(12):
                        try:
                            c = tc[i]
                            if c is not None and hasattr(c, "rgb") and c.rgb is not None:
                                theme_colors.append(str(c.rgb).upper().replace("#", ""))
                            else:
                                theme_colors.append("000000")
                        except (IndexError, TypeError):
                            theme_colors.append("000000")

        if not theme_colors:
            theme_colors = ["1F4E79", "2E75B6", "70AD47", "FFFFFF", "333333", "666666"] * 2

        return theme_colors

    def analyze_slide_master(self, slide_layout) -> Dict[str, Any]:
        """分析母版布局

        Args:
            slide_layout: slide_layout 对象

        Returns:
            布局分析结果字典
        """
        result: Dict[str, Any] = {
            "name": slide_layout.name if hasattr(slide_layout, "name") else "unknown",
            "placeholders": [],
            "decoration_shapes": [],
            "recommended_type": "title_content",
        }

        try:
            shapes = getattr(slide_layout, "shapes", [])
            has_title = False
            has_body = False

            for shape in shapes:
                if shape.is_placeholder:
                    ph = self._get_placeholder_info(shape)
                    if ph:
                        result["placeholders"].append(ph)

                        if ph.get("type") in ("title", "centerTitle", "subTitle"):
                            has_title = True
                        if ph.get("type") in ("body", "content"):
                            has_body = True
                else:
                    result["decoration_shapes"].append({
                        "name": shape.name if hasattr(shape, "name") else "unknown",
                        "type": getattr(shape, "shape_type", None),
                    })

            if has_title and not has_body:
                result["recommended_type"] = "title_only"
            elif has_title and has_body:
                result["recommended_type"] = "title_content"
            elif has_body:
                result["recommended_type"] = "content_only"
            else:
                result["recommended_type"] = "blank"

        except Exception as e:
            logger.debug(f"分析母版布局时发生异常：{e}")

        return result

    def generate_template_config(self) -> TemplateConfig:
        """生成完整模板配置

        根据已提取的颜色、字体、布局和装饰信息生成 TemplateConfig。

        Returns:
            TemplateConfig 实例

        Raises:
            RuntimeError: 尚未调用 parse_template_file
        """
        if not self._extracted_colors and not self._extracted_fonts:
            raise RuntimeError("尚未解析任何模板文件，请先调用 parse_template_file()")

        colors = self._extracted_colors
        fonts = self._extracted_fonts
        decorations = self._extracted_decorations

        layouts = {}
        for layout_name, layout_info in self._extracted_layouts.items():
            rec_type = layout_info.get("recommended_type", "title_content")

            try:
                layout_enum = self._map_layout_type(rec_type)
                layouts[layout_enum] = layout_info
            except ValueError:
                pass

        spacing = decorations.get("margins", {})

        return TemplateConfig(
            template_id="custom_user_upload",
            name="Custom Template",
            name_zh="自定义模板",
            category=self._default_category,
            description="用户自定义模板，由上传的 .pptx 文件自动解析生成",
            primary_color=colors.get("primary_color", "1F4E79"),
            secondary_color=colors.get("secondary_color", "2E75B6"),
            accent_color=colors.get("accent_color", "70AD47"),
            background_color=colors.get("background_color", "FFFFFF"),
            text_color=colors.get("text_color", "333333"),
            light_text_color=colors.get("light_text_color", "666666"),
            title_font=fonts.get("title_font", "微软雅黑"),
            body_font=fonts.get("body_font", "微软雅黑"),
            title_font_en=fonts.get("title_font_en", "Arial"),
            body_font_en=fonts.get("body_font_en", "Calibri"),
            title_size=28,
            subtitle_size=20,
            heading_size=24,
            body_size=16,
            bullet_size=14,
            caption_size=12,
            slide_margin=spacing.get("body_margin_left", 0.8),
            title_margin_bottom=spacing.get("title_margin_bottom", 0.4),
            paragraph_spacing=0.15,
            bullet_indent=0.3,
            line_spacing=1.3,
            has_header_bar=decorations.get("has_header_bar", False),
            has_footer_bar=decorations.get("has_footer_bar", False),
            has_corner_decor=decorations.get("has_corner_decor", False),
            has_page_number=decorations.get("has_page_number", False),
            slide_width=self._slide_width,
            slide_height=self._slide_height,
            layouts=layouts,
        )

    def _map_layout_type(self, rec_type: str):
        """将推荐的布局类型映射到 SlideLayout 枚举"""
        from app.utils.pptx.templates import SlideLayout

        mapping = {
            "title_only": SlideLayout.TITLE_ONLY,
            "title_content": SlideLayout.TITLE_CONTENT,
            "title_image": SlideLayout.TITLE_IMAGE,
            "title_two_column": SlideLayout.TITLE_TWO_COLUMN,
            "title_bullet": SlideLayout.TITLE_BULLET,
            "title_chart": SlideLayout.TITLE_CHART,
            "full_image": SlideLayout.FULL_IMAGE,
            "end_slide": SlideLayout.END_SLIDE,
            "content_only": SlideLayout.TITLE_CONTENT,
            "blank": SlideLayout.TITLE_ONLY,
        }
        return mapping.get(rec_type, SlideLayout.TITLE_CONTENT)


class TemplateValidator:
    """模板验证器 - 验证上传模板的有效性和兼容性"""

    REQUIRED_PLACEHOLDERS = ["title", "body"]
    RECOMMENDED_MAX_WIDTH = 20.0
    RECOMMENDED_MAX_HEIGHT = 15.0

    def validate_template(self, template_path: str) -> tuple[bool, List[str]]:
        """验证模板是否有效

        检查文件是否存在、是否为有效的 .pptx 文件、是否包含母版。

        Args:
            template_path: 模板文件路径

        Returns:
            (is_valid, errors) 元组
        """
        import os

        errors: List[str] = []

        if not os.path.isfile(template_path):
            err_msg = f"模板文件不存在：{template_path}"
            logger.warning(err_msg)
            errors.append(err_msg)
            return False, errors

        if not template_path.lower().endswith(".pptx"):
            err_msg = f"文件扩展名不是 .pptx：{template_path}"
            logger.warning(err_msg)
            errors.append(err_msg)
            return False, errors

        try:
            prs = PptxPresentation(template_path)
        except Exception as e:
            err_msg = f"无法打开 .pptx 文件：{template_path}, 错误：{e}"
            logger.error(err_msg)
            errors.append(err_msg)
            return False, errors

        if not prs.slide_masters:
            err_msg = f"模板文件不包含母版：{template_path}"
            logger.warning(err_msg)
            errors.append(err_msg)
            return False, errors

        return True, []

    def check_required_elements(self, template_path: str) -> List[str]:
        """检查模板是否包含必要的占位符元素

        Args:
            template_path: 模板文件路径

        Returns:
            缺失的必要元素列表，为空则说明所有必要元素都存在
        """
        missing: List[str] = list(self.REQUIRED_PLACEHOLDERS)

        try:
            prs = PptxPresentation(template_path)
        except Exception as e:
            logger.error(f"无法打开模板文件：{template_path}, 错误：{e}")
            return missing

        found_title = False
        found_body = False

        for master in prs.slide_masters:
            for layout in master.slide_layouts:
                for shape in layout.shapes:
                    if shape.is_placeholder:
                        ph = shape.placeholder_format
                        if hasattr(ph, "type") and ph.type is not None:
                            t = str(ph.type).lower()
                            if "title" in t:
                                found_title = True
                            if t in ("body", "content", "obj"):
                                found_body = True

        if found_title:
            missing.remove("title")
        if found_body:
            missing.remove("body")

        return missing

    def get_compatibility_score(self, template_path: str) -> float:
        """获取模板兼容性评分 (0.0 - 1.0)

        评分依据：
        - 文件格式有效性 (20%)
        - 母版是否存在 (20%)
        - 必要元素完整性 (30%)
        - 尺寸合理性 (15%)
        - 字体可用性 (15%)

        Args:
            template_path: 模板文件路径

        Returns:
            0.0 - 1.0 的兼容性评分
        """
        score = 0.0
        max_score = 1.0

        import os
        if not os.path.isfile(template_path):
            return 0.0

        if not template_path.lower().endswith(".pptx"):
            return 0.0

        try:
            prs = PptxPresentation(template_path)
        except Exception:
            return 0.0

        try:
            score += 0.2

            if prs.slide_masters:
                score += 0.2
                master = prs.slide_masters[0]

                has_title = False
                has_body = False
                for layout in master.slide_layouts:
                    for shape in layout.shapes:
                        if shape.is_placeholder:
                            ph = shape.placeholder_format
                            if hasattr(ph, "type") and ph.type is not None:
                                t = str(ph.type).lower()
                                if "title" in t:
                                    has_title = True
                                if t in ("body", "content", "obj"):
                                    has_body = True

                if has_title:
                    score += 0.15
                if has_body:
                    score += 0.15

                w = Emu(prs.slide_width).pt / 72.0
                h = Emu(prs.slide_height).pt / 72.0
                if w <= self.RECOMMENDED_MAX_WIDTH and h <= self.RECOMMENDED_MAX_HEIGHT:
                    score += 0.15
                elif w <= self.RECOMMENDED_MAX_WIDTH * 1.5 and h <= self.RECOMMENDED_MAX_HEIGHT * 1.5:
                    score += 0.08

                has_valid_font = False
                for layout in master.slide_layouts:
                    for shape in layout.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                for run in para.runs:
                                    if run.font and run.font.name:
                                        has_valid_font = True
                                        break
                            if has_valid_font:
                                break
                    if has_valid_font:
                        break

                if has_valid_font:
                    score += 0.15

            return min(score, max_score)
        finally:
            try:
                prs.close()
            except Exception:
                pass


class TemplateConverter:
    """模板转换器 - 在 PPTX 文件和 TemplateConfig 之间转换"""

    def convert_pptx_to_config(self, template_path: str) -> TemplateConfig:
        """将 .pptx 模板文件转换为 TemplateConfig

        Args:
            template_path: .pptx 模板文件路径

        Returns:
            解析后的 TemplateConfig 实例
        """
        parser = CustomTemplateParser()
        return parser.parse_template_file(template_path)

    def apply_config_to_presentation(self, config: TemplateConfig, prs):
        """将 TemplateConfig 应用到演示文稿

        设置幻灯片尺寸、主题颜色、字体和装饰元素。

        Args:
            config: TemplateConfig 实例
            prs: pptx Presentation 对象
        """
        try:
            prs.slide_width = Inches(config.slide_width)
            prs.slide_height = Inches(config.slide_height)
        except Exception as e:
            logger.warning(f"设置幻灯片尺寸失败：{e}")

        try:
            self._apply_colors_to_presentation(prs, config)
        except Exception as e:
            logger.warning(f"应用主题色失败：{e}")

        try:
            self._apply_default_font_to_presentation(prs, config)
        except Exception as e:
            logger.warning(f"应用默认字体失败：{e}")

        if config.has_header_bar or config.has_footer_bar or config.has_page_number:
            self._apply_decorations(prs, config)

    def _apply_colors_to_presentation(self, prs, config: TemplateConfig):
        """将主题色应用到演示文稿的母版中"""
        from pptx.oxml.ns import qn

        if not prs.slide_masters:
            return

        master = prs.slide_masters[0]
        theme_el = master.theme._element if hasattr(master.theme, "_element") else None
        if theme_el is None:
            return

        color_map = {
            0: config.primary_color,
            1: config.text_color,
            2: config.secondary_color,
            3: config.accent_color,
            4: config.light_text_color,
            6: config.background_color,
        }

        try:
            theme_colors_el = theme_el.find(qn("a:clrScheme"))
            if theme_colors_el is not None:
                colors = theme_colors_el.findall(qn("a:srgbClr"))
                for i, clr in enumerate(colors):
                    if i in color_map:
                        val_el = clr.find(qn("a:srgbClr"))
                        if val_el is not None:
                            val_el.set("val", color_map[i])
                            break
        except Exception as e:
            logger.debug(f"通过 XML 修改主题色失败：{e}")

        try:
            for slide_layout in master.slide_layouts:
                for shape in slide_layout.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            for run in para.runs:
                                run_font = run.font if run.font is not None else None
                                if run_font is not None:
                                    run_font.size = Pt(config.body_size)
        except Exception as e:
            logger.debug(f"设置母版文字属性失败：{e}")

    def _apply_default_font_to_presentation(self, prs, config: TemplateConfig):
        """设置演示文稿的默认字体"""
        from pptx.oxml.ns import qn

        if not prs.slide_masters:
            return

        master = prs.slide_masters[0]
        theme_el = master.theme._element if hasattr(master.theme, "_element") else None
        if theme_el is None:
            return

        font_scheme = theme_el.find(qn("a:fontScheme"))
        if font_scheme is None:
            return

        try:
            for tag, en_font, ea_font in [
                ("a:majorFont", config.title_font_en, config.title_font),
                ("a:minorFont", config.body_font_en, config.body_font),
            ]:
                font_el = font_scheme.find(qn(tag))
                if font_el is not None:
                    latin = font_el.find(qn("a:latin"))
                    if latin is not None:
                        latin.set("typeface", en_font)
                    ea = font_el.find(qn("a:ea"))
                    if ea is not None:
                        ea.set("typeface", ea_font)
        except Exception as e:
            logger.debug(f"通过 XML 修改字体失败：{e}")

    def _apply_decorations(self, prs, config: TemplateConfig):
        """在母版上应用装饰元素"""
        if not prs.slide_masters:
            return

        master = prs.slide_masters[0]

        for layout in master.slide_layouts:
            if config.has_header_bar:
                self._add_header_bar_on_layout(layout, config)
            if config.has_footer_bar:
                self._add_footer_bar_on_layout(layout, config)
            if config.has_page_number:
                self._add_page_number_on_layout(layout, config)
            if config.has_corner_decor:
                self._add_corner_decor_on_layout(layout, config)

    def _add_header_bar_on_layout(self, layout, config: TemplateConfig):
        """在布局上添加顶部装饰条"""
        try:
            bar_height = Inches(0.12)
            header_bar = layout.shapes.add_shape(
                1,
                Inches(0), Inches(0),
                Inches(config.slide_width), bar_height
            )
            header_bar.fill.solid()
            header_bar.fill.fore_color.rgb = RGBColor.from_string(config.primary_color)
            header_bar.line.fill.background()
        except Exception as e:
            logger.debug(f"在 layout 上添加 header bar 失败：{e}")

    def _add_footer_bar_on_layout(self, layout, config: TemplateConfig):
        """在布局上添加底部装饰条"""
        try:
            footer_height = Inches(0.08)
            footer_bar = layout.shapes.add_shape(
                1,
                Inches(0), Inches(config.slide_height) - footer_height,
                Inches(config.slide_width), footer_height
            )
            footer_bar.fill.solid()
            footer_bar.fill.fore_color.rgb = RGBColor.from_string(config.secondary_color)
            footer_bar.line.fill.background()
        except Exception as e:
            logger.debug(f"在 layout 上添加 footer bar 失败：{e}")

    def _add_page_number_on_layout(self, layout, config: TemplateConfig):
        """在布局上添加页码占位符"""
        try:
            page_text = layout.shapes.add_textbox(
                Inches(config.slide_width) - Inches(1.2),
                Inches(config.slide_height) - Inches(0.45),
                Inches(1.0), Inches(0.3)
            )
            tf = page_text.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = "<#>"
            p.font.size = Pt(config.caption_size)
            p.font.color.rgb = RGBColor.from_string(config.light_text_color)
            p.alignment = PP_ALIGN.RIGHT
        except Exception as e:
            logger.debug(f"在 layout 上添加页码失败：{e}")

    def _add_corner_decor_on_layout(self, layout, config: TemplateConfig):
        """在布局上添加角标装饰"""
        try:
            decor_size = Inches(1.5)
            decor = layout.shapes.add_shape(
                1,
                Inches(config.slide_width) - decor_size,
                Inches(config.slide_height) - decor_size - Inches(0.3),
                decor_size, decor_size
            )
            decor.fill.solid()
            decor.fill.fore_color.rgb = RGBColor.from_string(config.primary_color)
            decor.fill.fore_color.brightness = 0.85
            decor.line.fill.background()
        except Exception as e:
            logger.debug(f"在 layout 上添加角标装饰失败：{e}")

    def merge_configs(self, base: TemplateConfig, custom: TemplateConfig) -> TemplateConfig:
        """合并两个模板配置，custom 的优先级高于 base

        合并策略：
        - 基本信息使用 base
        - 配色、字体、间距使用 custom（如果 custom 有值）
        - 布局合并两者的布局定义
        - 装饰元素使用 custom 的设置

        Args:
            base: 基础模板配置
            custom: 自定义模板配置

        Returns:
            合并后的 TemplateConfig
        """
        merged_colors = {}
        for key in ["primary_color", "secondary_color", "accent_color",
                    "background_color", "text_color", "light_text_color"]:
            base_val = getattr(base, key, None)
            custom_val = getattr(custom, key, None)
            if custom_val and custom_val != getattr(TemplateConfig, key, None):
                merged_colors[key] = custom_val
            elif base_val:
                merged_colors[key] = base_val

        merged_fonts = {}
        for key in ["title_font", "body_font", "title_font_en", "body_font_en"]:
            base_val = getattr(base, key, None)
            custom_val = getattr(custom, key, None)
            if custom_val and custom_val != getattr(TemplateConfig, key, None):
                merged_fonts[key] = custom_val
            elif base_val:
                merged_fonts[key] = base_val

        default_sizes = {
            "title_size": 32, "subtitle_size": 20, "heading_size": 24,
            "body_size": 16, "bullet_size": 14, "caption_size": 12,
        }
        merged_sizes = {}
        for key, default in default_sizes.items():
            base_val = getattr(base, key, default)
            custom_val = getattr(custom, key, default)
            if custom_val != default:
                merged_sizes[key] = custom_val
            else:
                merged_sizes[key] = base_val

        default_spacings = {
            "slide_margin": 0.8, "title_margin_bottom": 0.4,
            "paragraph_spacing": 0.15, "bullet_indent": 0.3, "line_spacing": 1.3,
        }
        merged_spacings = {}
        for key, default in default_spacings.items():
            base_val = getattr(base, key, default)
            custom_val = getattr(custom, key, default)
            if custom_val != default:
                merged_spacings[key] = custom_val
            else:
                merged_spacings[key] = base_val

        merged_decorations = {}
        for key in ["has_header_bar", "has_footer_bar",
                    "has_corner_decor", "has_page_number"]:
            merged_decorations[key] = getattr(custom, key, getattr(base, key, False))

        dim_sizes = {"slide_width": 13.333, "slide_height": 7.5}
        merged_dims = {}
        for key, default in dim_sizes.items():
            custom_val = getattr(custom, key, default)
            base_val = getattr(base, key, default)
            if custom_val != default:
                merged_dims[key] = custom_val
            else:
                merged_dims[key] = base_val

        merged_layouts = dict(base.layouts)
        merged_layouts.update(custom.layouts)

        return TemplateConfig(
            template_id=custom.template_id,
            name=custom.name,
            name_zh=custom.name_zh,
            category=base.category,
            description=base.description,
            primary_color=merged_colors.get("primary_color", "1F4E79"),
            secondary_color=merged_colors.get("secondary_color", "2E75B6"),
            accent_color=merged_colors.get("accent_color", "70AD47"),
            background_color=merged_colors.get("background_color", "FFFFFF"),
            text_color=merged_colors.get("text_color", "333333"),
            light_text_color=merged_colors.get("light_text_color", "666666"),
            title_font=merged_fonts.get("title_font", "微软雅黑"),
            body_font=merged_fonts.get("body_font", "微软雅黑"),
            title_font_en=merged_fonts.get("title_font_en", "Arial"),
            body_font_en=merged_fonts.get("body_font_en", "Calibri"),
            **merged_sizes,
            **merged_spacings,
            **merged_decorations,
            **merged_dims,
            layouts=merged_layouts,
        )
