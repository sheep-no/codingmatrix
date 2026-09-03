"""
PPT 内置模板集合 - 5 套专业模板
"""
from app.utils.pptx.templates.base import TemplateBase, TemplateConfig, TemplateCategory, SlideLayout


class BusinessReportTemplate(TemplateBase):
    """商务汇报模板"""

    @property
    def config(self) -> TemplateConfig:
        return TemplateConfig(
            template_id="business_report",
            name="Business Report",
            name_zh="商务汇报",
            category=TemplateCategory.BUSINESS,
            description="适用于企业内部汇报、工作总结、项目进度报告等专业场景。采用深蓝色系，稳重专业。",

            # 配色
            primary_color="1F4E79",       # 深蓝
            secondary_color="2E75B6",     # 中蓝
            accent_color="548235",        # 深绿
            background_color="FFFFFF",    # 白
            text_color="333333",          # 深灰
            light_text_color="666666",    # 浅灰

            # 字体
            title_font="微软雅黑",
            body_font="微软雅黑",
            title_font_en="Arial",
            body_font_en="Calibri",

            # 字号
            title_size=32,
            subtitle_size=20,
            heading_size=24,
            body_size=16,
            bullet_size=14,
            caption_size=11,

            # 间距
            slide_margin=0.8,
            title_margin_bottom=0.4,
            paragraph_spacing=0.15,
            bullet_indent=0.3,
            line_spacing=1.3,

            # 装饰
            has_header_bar=True,
            has_footer_bar=True,
            has_corner_decor=False,
            has_page_number=True,

            # 布局
            layouts={
                SlideLayout.TITLE_ONLY: {
                    "title_top": 2.5,
                    "title_left": 1.5,
                    "title_width": 10.3,
                    "subtitle_top": 3.3,
                },
                SlideLayout.TITLE_CONTENT: {
                    "title_top": 0.8,
                    "content_top": 1.6,
                    "content_left": 1.0,
                    "content_width": 11.3,
                    "content_height": 5.4,
                },
                SlideLayout.TITLE_TWO_COLUMN: {
                    "title_top": 0.8,
                    "left_column": 1.0,
                    "right_column": 7.0,
                    "column_width": 5.5,
                    "content_top": 1.6,
                    "content_height": 5.4,
                },
            }
        )


class AcademicPresetTemplate(TemplateBase):
    """学术论文模板"""

    @property
    def config(self) -> TemplateConfig:
        return TemplateConfig(
            template_id="academic",
            name="Academic",
            name_zh="学术论文",
            category=TemplateCategory.ACADEMIC,
            description="适用于学术答辩、论文展示、研究报告等学术场景。采用藏青配色，简洁庄重。",

            # 配色
            primary_color="203864",       # 藏青
            secondary_color="4472C4",     # 蓝
            accent_color="ED7D31",        # 橙
            background_color="F8F9FA",    # 浅灰
            text_color="212529",          # 深灰
            light_text_color="868E96",    # 灰

            # 字体
            title_font="宋体",
            body_font="宋体",
            title_font_en="Times New Roman",
            body_font_en="Times New Roman",

            # 字号
            title_size=28,
            subtitle_size=18,
            heading_size=22,
            body_size=15,
            bullet_size=13,
            caption_size=11,

            # 间距
            slide_margin=1.0,
            title_margin_bottom=0.5,
            paragraph_spacing=0.2,
            bullet_indent=0.4,
            line_spacing=1.5,

            # 装饰
            has_header_bar=False,
            has_footer_bar=True,
            has_corner_decor=False,
            has_page_number=True,
            slide_width=13.333,
            slide_height=7.5,

            # 布局
            layouts={
                SlideLayout.TITLE_ONLY: {
                    "title_top": 3.0,
                    "title_left": 1.5,
                    "title_width": 10.3,
                    "subtitle_top": 3.8,
                },
                SlideLayout.TITLE_CONTENT: {
                    "title_top": 0.6,
                    "content_top": 1.4,
                    "content_left": 1.2,
                    "content_width": 10.9,
                    "content_height": 5.6,
                },
                SlideLayout.TITLE_BULLET: {
                    "title_top": 0.6,
                    "bullet_top": 1.4,
                    "bullet_left": 1.5,
                    "bullet_width": 10.3,
                    "bullet_height": 5.6,
                }
            }
        )


class PitchDeckTemplate(TemplateBase):
    """产品路演模板"""

    @property
    def config(self) -> TemplateConfig:
        return TemplateConfig(
            template_id="pitch_deck",
            name="Pitch Deck",
            name_zh="产品路演",
            category=TemplateCategory.PITCH,
            description="适用于产品发布、融资路演、营销方案等商业展示。采用红黑配色，现代动感。",

            # 配色
            primary_color="C00000",       # 红
            secondary_color="FF6B6B",     # 亮红
            accent_color="FFD700",        # 金
            background_color="1A1A1A",    # 黑
            text_color="FFFFFF",          # 白
            light_text_color="CCCCCC",    # 浅灰

            # 字体
            title_font="微软雅黑",
            body_font="微软雅黑",
            title_font_en="Arial Black",
            body_font_en="Arial",

            # 字号
            title_size=36,
            subtitle_size=22,
            heading_size=26,
            body_size=17,
            bullet_size=15,
            caption_size=12,

            # 间距
            slide_margin=0.8,
            title_margin_bottom=0.5,
            paragraph_spacing=0.18,
            bullet_indent=0.35,
            line_spacing=1.4,

            # 装饰
            has_header_bar=True,
            has_footer_bar=True,
            has_corner_decor=True,
            has_page_number=True,

            # 布局
            layouts={
                SlideLayout.TITLE_ONLY: {
                    "title_top": 2.8,
                    "title_left": 1.5,
                    "title_width": 10.3,
                    "subtitle_top": 3.6,
                    "use_full_background": True,
                },
                SlideLayout.TITLE_CONTENT: {
                    "title_top": 0.7,
                    "content_top": 1.5,
                    "content_left": 0.8,
                    "content_width": 11.7,
                    "content_height": 5.5,
                },
                SlideLayout.FULL_IMAGE: {
                    "image_top": 0,
                    "image_left": 0,
                    "image_width": 13.333,
                    "image_height": 7.5,
                    "title_overlay": True,
                    "title_top": 3.0,
                }
            }
        )


class EducationTemplate(TemplateBase):
    """教育培训模板"""

    @property
    def config(self) -> TemplateConfig:
        return TemplateConfig(
            template_id="education",
            name="Education",
            name_zh="教育培训",
            category=TemplateCategory.EDUCATION,
            description="适用于课程教学、培训讲座、知识分享等教育场景。采用蓝绿配色，清新友好。",

            # 配色
            primary_color="2E75B6",       # 蓝
            secondary_color="548235",     # 绿
            accent_color="FFC000",        # 黄
            background_color="FFFFFF",    # 白
            text_color="333333",          # 深灰
            light_text_color="666666",    # 浅灰

            # 字体
            title_font="微软雅黑",
            body_font="微软雅黑",
            title_font_en="Calibri",
            body_font_en="Calibri",

            # 字号
            title_size=30,
            subtitle_size=18,
            heading_size=22,
            body_size=16,
            bullet_size=14,
            caption_size=12,

            # 间距
            slide_margin=0.8,
            title_margin_bottom=0.4,
            paragraph_spacing=0.15,
            bullet_indent=0.3,
            line_spacing=1.35,

            # 装饰
            has_header_bar=True,
            has_footer_bar=False,
            has_corner_decor=True,
            has_page_number=True,

            # 布局
            layouts={
                SlideLayout.TITLE_ONLY: {
                    "title_top": 2.5,
                    "title_left": 1.5,
                    "title_width": 10.3,
                    "subtitle_top": 3.3,
                },
                SlideLayout.TITLE_CONTENT: {
                    "title_top": 0.7,
                    "content_top": 1.5,
                    "content_left": 1.0,
                    "content_width": 11.3,
                    "content_height": 5.5,
                },
                SlideLayout.TITLE_BULLET: {
                    "title_top": 0.7,
                    "bullet_top": 1.5,
                    "bullet_left": 1.3,
                    "bullet_width": 10.7,
                    "bullet_height": 5.5,
                },
            }
        )


class MinimalTemplate(TemplateBase):
    """简约风格模板"""

    @property
    def config(self) -> TemplateConfig:
        return TemplateConfig(
            template_id="minimal",
            name="Minimal",
            name_zh="简约风格",
            category=TemplateCategory.MINIMAL,
            description="追求极简设计，大量留白，适合高端品牌展示、设计汇报等场景。",

            # 配色
            primary_color="333333",       # 深灰
            secondary_color="666666",     # 灰
            accent_color="999999",        # 浅灰
            background_color="FFFFFF",    # 白
            text_color="2C3E50",          # 深灰
            light_text_color="95A5A6",    # 浅灰

            # 字体
            title_font="微软雅黑",
            body_font="微软雅黑",
            title_font_en="Helvetica",
            body_font_en="Helvetica",

            # 字号
            title_size=34,
            subtitle_size=20,
            heading_size=24,
            body_size=16,
            bullet_size=14,
            caption_size=10,

            # 间距（大留白）
            slide_margin=1.5,
            title_margin_bottom=0.6,
            paragraph_spacing=0.25,
            bullet_indent=0.4,
            line_spacing=1.6,

            # 装饰（简洁）
            has_header_bar=False,
            has_footer_bar=False,
            has_corner_decor=False,
            has_page_number=True,

            # 布局
            layouts={
                SlideLayout.TITLE_ONLY: {
                    "title_top": 3.0,
                    "title_left": 2.0,
                    "title_width": 9.3,
                    "subtitle_top": 3.8,
                    "minimal": True,
                },
                SlideLayout.TITLE_CONTENT: {
                    "title_top": 1.0,
                    "content_top": 2.0,
                    "content_left": 1.8,
                    "content_width": 9.7,
                    "content_height": 4.5,
                    "minimal": True,
                },
            }
        )


class TechTemplate(TemplateBase):
    """深色科技演示模板。"""

    @property
    def config(self) -> TemplateConfig:
        return TemplateConfig(
            template_id="tech",
            name="Technology",
            name_zh="科技蓝调",
            category=TemplateCategory.TECH,
            description="适用于技术方案、系统架构和 AI 产品汇报，采用深色界面与高对比数据强调。",
            primary_color="3B82F6",
            secondary_color="1D4ED8",
            accent_color="F97316",
            background_color="0F172A",
            text_color="FFFFFF",
            light_text_color="93C5FD",
            title_font="微软雅黑",
            body_font="微软雅黑",
            title_font_en="Consolas",
            body_font_en="Arial",
            title_size=36,
            subtitle_size=20,
            heading_size=25,
            body_size=16,
            bullet_size=14,
            caption_size=10,
            slide_margin=0.7,
            title_margin_bottom=0.45,
            paragraph_spacing=0.16,
            bullet_indent=0.3,
            line_spacing=1.35,
            has_header_bar=True,
            has_footer_bar=False,
            has_corner_decor=False,
            has_page_number=True,
            layouts={
                SlideLayout.TITLE_ONLY: {
                    "title_top": 1.7,
                    "title_left": 0.8,
                    "title_width": 10.2,
                    "subtitle_top": 3.65,
                    "use_full_background": True,
                },
                SlideLayout.TITLE_CONTENT: {
                    "title_top": 0.7,
                    "content_top": 1.75,
                    "content_left": 0.7,
                    "content_width": 11.9,
                    "content_height": 4.9,
                },
            },
        )
