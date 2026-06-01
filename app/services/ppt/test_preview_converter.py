"""
PPTX 预览转换器单元测试

测试预览转换器的核心功能：
- 提取幻灯片内容
- 分类幻灯片类型
- 生成 HTML 预览
- 错误处理
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.ppt.preview_converter import (
    PreviewConverter,
    SlidePreview,
    PreviewConverterError,
)


@pytest.fixture
def converter(tmp_path):
    """创建预览转换器实例"""
    return PreviewConverter(output_dir=tmp_path)


@pytest.fixture
def sample_slides():
    """创建示例幻灯片数据"""
    return [
        SlidePreview(
            index=1,
            title="AI 发展趋势",
            content=["人工智能正在改变世界", "机器学习是核心驱动力"],
            slide_type="title",
        ),
        SlidePreview(
            index=2,
            title="第一章：概述",
            content=[],
            slide_type="chapter",
        ),
        SlidePreview(
            index=3,
            title="技术架构",
            content=["前端：Vue 3", "后端：FastAPI", "数据库：PostgreSQL"],
            has_image=True,
            slide_type="image",
        ),
    ]


class TestSlidePreview:
    """幻灯片预览数据测试"""
    
    def test_defaults(self):
        """测试默认值"""
        slide = SlidePreview(index=1, title="测试")
        
        assert slide.index == 1
        assert slide.title == "测试"
        assert slide.content == []
        assert slide.notes == ""
        assert slide.has_image is False
        assert slide.slide_type == "content"


class TestPreviewConverter:
    """预览转换器测试"""
    
    def test_extract_slides_from_mock(self, converter):
        """测试从模拟 PPTX 提取幻灯片"""
        mock_prs = MagicMock()
        
        # 创建标题形状
        mock_title_shape = MagicMock()
        mock_title_shape.text_frame.text = "标题页"
        mock_title_shape.has_text_frame = True
        
        # 幻灯片 1：只有标题
        mock_slide1 = MagicMock()
        mock_slide1.shapes.title = mock_title_shape
        mock_slide1.shapes.__iter__ = lambda self: iter([mock_title_shape])
        mock_slide1.has_notes_slide = False
        
        # 幻灯片 2：标题 + 内容
        mock_title_shape2 = MagicMock()
        mock_title_shape2.text_frame.text = "内容页"
        mock_title_shape2.has_text_frame = True
        
        mock_content_shape = MagicMock()
        mock_content_shape.has_text_frame = True
        mock_content_shape.text_frame.text = "要点 1"
        
        mock_slide2 = MagicMock()
        mock_slide2.shapes.title = mock_title_shape2
        mock_slide2.shapes.__iter__ = lambda self: iter([mock_title_shape2, mock_content_shape])
        mock_slide2.has_notes_slide = False
        
        mock_prs.slides = [mock_slide1, mock_slide2]
        
        with patch("app.services.ppt.preview_converter.Presentation") as mock_pres:
            mock_pres.return_value = mock_prs
            
            slides = converter._extract_slides("test.pptx", include_notes=False)
            
            assert len(slides) == 2
            assert slides[0].title == "标题页"
            assert slides[1].title == "内容页"
            assert len(slides[1].content) == 1
            assert slides[1].content[0] == "要点 1"
    
    def test_classify_slide_title(self, converter):
        """测试分类标题页"""
        slide_type = converter._classify_slide("短标题", [], False)
        assert slide_type == "title"
    
    def test_classify_slide_chapter(self, converter):
        """测试分类章节页"""
        # 章节页标题通常较长且没有内容
        slide_type = converter._classify_slide("这是一个很长的章节标题文字超过二十个字符", [], False)
        assert slide_type == "chapter"
    
    def test_classify_slide_bullet(self, converter):
        """测试分类要点页"""
        content = ["要点" + str(i) for i in range(6)]
        slide_type = converter._classify_slide("标题", content, False)
        assert slide_type == "bullet"
    
    def test_classify_slide_image(self, converter):
        """测试分类图片页"""
        slide_type = converter._classify_slide("标题", ["内容"], True)
        assert slide_type == "image"
    
    def test_classify_slide_content(self, converter):
        """测试分类内容页"""
        slide_type = converter._classify_slide("标题", ["内容 1", "内容 2"], False)
        assert slide_type == "content"
    
    def test_classify_slide_blank(self, converter):
        """测试分类空白页"""
        slide_type = converter._classify_slide("", [], False)
        assert slide_type == "blank"
    
    def test_generate_html_structure(self, converter, sample_slides):
        """测试生成 HTML 结构"""
        html = converter._generate_html(sample_slides)
        
        # 验证基本 HTML 结构
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "幻灯片 1 / 3" in html
        
        # 验证包含幻灯片数据
        assert "AI 发展趋势" in html
        assert "第一章：概述" in html
        assert "技术架构" in html
        
        # 验证包含 JavaScript
        assert "navigateSlide" in html
        assert "toggleFullscreen" in html
    
    def test_generate_thumbnails(self, converter, sample_slides):
        """测试生成缩略图"""
        thumbnails = converter._generate_thumbnails(sample_slides)
        
        assert "thumb-1" in thumbnails
        assert "thumb-2" in thumbnails
        assert "thumb-3" in thumbnails
        assert "AI 发展趋势" in thumbnails
    
    def test_generate_slide_json(self, converter, sample_slides):
        """测试生成幻灯片 JSON"""
        json_str = converter._generate_slide_json(sample_slides)
        
        import json
        data = json.loads(json_str)
        
        assert len(data) == 3
        assert data[0]["title"] == "AI 发展趋势"
        assert data[0]["slide_type"] == "title"
    
    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self, converter):
        """测试转换不存在的文件"""
        with pytest.raises(PreviewConverterError):
            await converter.convert("nonexistent.pptx")
    
    def test_parse_slide_with_notes(self, converter):
        """测试解析带备注的幻灯片"""
        # 创建标题形状
        mock_title_shape = MagicMock()
        mock_title_shape.text_frame.text = "标题页"
        mock_title_shape.has_text_frame = True
        
        mock_slide = MagicMock()
        mock_slide.shapes.title = mock_title_shape
        mock_slide.shapes.__iter__ = lambda self: iter([mock_title_shape])
        mock_slide.has_notes_slide = True
        
        mock_notes_frame = MagicMock()
        mock_notes_frame.text = "这是演讲者备注"
        mock_slide.notes_slide.notes_text_frame = mock_notes_frame
        
        slide_data = converter._parse_slide(mock_slide, 1, include_notes=True)
        
        assert slide_data.title == "标题页"
        assert slide_data.notes == "这是演讲者备注"
    
    def test_parse_slide_without_notes(self, converter):
        """测试解析不带备注的幻灯片"""
        mock_title_shape = MagicMock()
        mock_title_shape.text_frame.text = "标题页"
        mock_title_shape.has_text_frame = True
        
        mock_slide = MagicMock()
        mock_slide.shapes.title = mock_title_shape
        mock_slide.shapes.__iter__ = lambda self: iter([mock_title_shape])
        mock_slide.has_notes_slide = False
        
        slide_data = converter._parse_slide(mock_slide, 1, include_notes=True)
        
        assert slide_data.title == "标题页"
        assert slide_data.notes == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
