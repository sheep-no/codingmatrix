"""
PPT 生成器集成测试

测试完整 PPT 生成流程
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.pptxGenerateUtil import PptGenerator, Slide, SlideType, Presentation


class TestPptGenerator:
    """测试 PPT 生成器"""

    @pytest.fixture
    def generator(self):
        return PptGenerator()

    @pytest.fixture
    def sample_presentation(self):
        return Presentation(
            title="测试演示",
            subtitle="副标题",
            author="测试者",
            theme="business",
            slides=[
                Slide(
                    type=SlideType.TITLE,
                    title="封面标题",
                    subtitle="封面副标题"
                ),
                Slide(
                    type=SlideType.CONTENT,
                    title="内容页",
                    content=["要点一", "要点二", "要点三"]
                ),
                Slide(
                    type=SlideType.END,
                    title="感谢观看",
                    subtitle="谢谢"
                )
            ]
        )

    def test_generator_initialization(self, generator):
        """测试生成器初始化"""
        assert generator is not None
        assert hasattr(generator, 'image_search_cache')
        assert hasattr(generator, 'temp_image_dir')
        assert hasattr(generator, 'semaphore')

    def test_render_to_pptx(self, generator, sample_presentation):
        """测试渲染到 PPTX"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_output.pptx")

            result = generator.render_to_pptx(
                presentation=sample_presentation,
                output_path=output_path
            )

            assert result == output_path
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0

    def test_render_to_pptx_with_image_map(self, generator, sample_presentation):
        """测试渲染带图片映射的 PPTX"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_with_images.pptx")

            result = generator.render_to_pptx(
                presentation=sample_presentation,
                output_path=output_path,
                image_map={},
                remove_placeholders=True
            )

            assert result is not None
            assert os.path.exists(result)

    def test_count_chars(self, generator):
        """测试字符计数"""
        test_data = {"title": "测试标题", "content": "测试内容"}
        char_count = generator._count_chars(test_data)
        assert char_count > 0
        assert isinstance(char_count, int)

    def test_truncate_slide_content(self, generator):
        """测试截断幻灯片内容"""
        test_data = {
            "title": "这是一个很长的标题用于测试截断功能",
            "content": "这是一段很长的内容用于测试截断功能是否正常工作"
        }
        truncated = generator._truncate_slide_content(test_data, SlideType.CONTENT, 20)
        assert isinstance(truncated, dict)
        assert "title" in truncated

    def test_get_default_slide(self, generator):
        """测试获取默认幻灯片"""
        outline_item = {"title": "测试标题", "content": "测试内容"}
        slide = generator._get_default_slide(SlideType.CONTENT, outline_item)
        assert isinstance(slide, Slide)
        assert slide.type == SlideType.CONTENT

    def test_get_default_outline(self, generator):
        """测试获取默认大纲"""
        outline = generator._get_default_outline("测试主题", 5)
        assert isinstance(outline, list)
        assert len(outline) == 5

    def test_get_default_design_suggestions(self, generator):
        """测试获取默认设计建议"""
        suggestions = generator._get_default_design_suggestions("business")
        assert isinstance(suggestions, dict)

    def test_generate_global_design_scheme(self, generator, sample_presentation):
        """测试生成全局设计方案"""
        scheme = generator._generate_global_design_scheme("business", sample_presentation.slides)
        assert isinstance(scheme, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
