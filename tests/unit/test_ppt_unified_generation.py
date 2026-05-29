"""
PPT 统一渲染管线测试

测试 generate_pptx_file_enhanced 使用 PptGenerator 引擎的完整流程。
不需要 LLM，使用 mock 大纲数据。
"""
import pytest
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.api.v1.aiGeneratorPptx import (
    generate_pptx_file_enhanced,
    PPT_TEMPLATES,
)


class TestTemplateMapping:
    """测试 API 模板配置"""

    def test_all_api_templates_exist(self):
        """所有 API 模板都存在"""
        expected_templates = ["modern", "business", "creative", "minimal", "academic", "tech", "education", "medical"]
        for tpl in expected_templates:
            assert tpl in PPT_TEMPLATES, f"Missing template: {tpl}"

    def test_template_has_required_fields(self):
        """每个模板都有必需的字段"""
        required_fields = ["name", "primary_color", "secondary_color", "font_family", "background"]
        for tpl_name, tpl_config in PPT_TEMPLATES.items():
            for field in required_fields:
                assert field in tpl_config, f"Template '{tpl_name}' missing field: {field}"

    def test_template_colors_are_valid_hex(self):
        """模板颜色是有效的十六进制格式"""
        for tpl_name, tpl_config in PPT_TEMPLATES.items():
            for color_field in ["primary_color", "secondary_color", "background"]:
                color = tpl_config[color_field]
                assert color.startswith("#"), f"Template '{tpl_name}' {color_field} should start with #"
                assert len(color) == 7, f"Template '{tpl_name}' {color_field} should be 7 chars"


class TestUnifiedGeneration:
    """测试统一渲染管线的完整生成流程"""

    @pytest.fixture
    def mock_request(self):
        """创建 mock PPTGenerationRequest"""
        req = MagicMock()
        req.template = "modern"
        req.language = "zh-CN"
        req.style = "professional"
        return req

    @pytest.fixture
    def sample_outline(self):
        """示例 AI 大纲"""
        return {
            "title": "AI 技术发展趋势",
            "slides": [
                {
                    "slide_type": "cover",
                    "title": "AI 技术发展趋势",
                    "subtitle": "2026 年展望",
                    "content": "",
                },
                {
                    "slide_type": "toc",
                    "title": "目录",
                    "content": "第一章：大模型\n第二章：多模态\n第三章：Agent",
                },
                {
                    "slide_type": "content",
                    "title": "大模型发展",
                    "content": "参数规模持续增长\n推理能力显著提升\n多模态融合加深",
                    "notes": "这是演讲者备注",
                },
                {
                    "slide_type": "bullet",
                    "title": "关键技术突破",
                    "content": "Transformer 架构优化\n长上下文窗口\n思维链推理\n工具使用能力",
                },
                {
                    "slide_type": "image",
                    "title": "应用场景",
                    "content": "智能客服\n代码生成\n内容创作",
                    "image_keywords": ["AI", "technology", "robot"],
                },
                {
                    "slide_type": "end",
                    "title": "感谢观看",
                    "subtitle": "Q&A",
                    "content": "",
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_generate_pptx_file_enhanced(self, mock_request, sample_outline):
        """测试增强版 PPTX 生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test_output.pptx"
            await generate_pptx_file_enhanced(filepath, sample_outline, mock_request)

            # 验证文件生成
            assert filepath.exists(), "PPTX file should be created"
            assert filepath.stat().st_size > 0, "PPTX file should not be empty"

            # 验证 JSON 快照
            json_path = filepath.parent / f"{filepath.stem}_slides.json"
            assert json_path.exists(), "JSON snapshot should be created"
            with open(json_path, "r", encoding="utf-8") as f:
                slides_data = json.load(f)
            assert len(slides_data) == 6, f"Expected 6 slides in JSON, got {len(slides_data)}"

    @pytest.mark.asyncio
    async def test_generate_with_different_templates(self, sample_outline):
        """测试不同模板的生成"""
        for template_name in PPT_TEMPLATES.keys():
            req = MagicMock()
            req.template = template_name
            req.language = "zh-CN"

            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / f"test_{template_name}.pptx"
                await generate_pptx_file_enhanced(filepath, sample_outline, req)
                assert filepath.exists(), f"PPTX should be created for template '{template_name}'"
                assert filepath.stat().st_size > 0, f"PPTX should not be empty for template '{template_name}'"

    @pytest.mark.asyncio
    async def test_generate_with_content_list(self, mock_request):
        """测试 content 为列表格式的生成"""
        outline = {
            "title": "列表内容测试",
            "slides": [
                {
                    "slide_type": "content",
                    "title": "列表页",
                    "content": ["第一项", "第二项", "第三项"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "list_content.pptx"
            await generate_pptx_file_enhanced(filepath, outline, mock_request)
            assert filepath.exists()

    @pytest.mark.asyncio
    async def test_generate_with_empty_content(self, mock_request):
        """测试空内容的生成"""
        outline = {
            "title": "空内容测试",
            "slides": [
                {
                    "slide_type": "content",
                    "title": "空页",
                    "content": "",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty_content.pptx"
            await generate_pptx_file_enhanced(filepath, outline, mock_request)
            assert filepath.exists()

    @pytest.mark.asyncio
    async def test_generate_with_unknown_slide_type(self, mock_request):
        """测试未知幻灯片类型"""
        outline = {
            "title": "未知类型测试",
            "slides": [
                {
                    "slide_type": "unknown_type",
                    "title": "未知类型页",
                    "content": "一些内容",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "unknown_type.pptx"
            await generate_pptx_file_enhanced(filepath, outline, mock_request)
            assert filepath.exists()

    @pytest.mark.asyncio
    async def test_generate_with_missing_fields(self, mock_request):
        """测试缺少字段的幻灯片"""
        outline = {
            "slides": [
                {"slide_type": "content"},  # 缺少 title 和 content
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "missing_fields.pptx"
            await generate_pptx_file_enhanced(filepath, outline, mock_request)
            assert filepath.exists()

    @pytest.mark.asyncio
    async def test_generate_with_progress_callback(self, mock_request, sample_outline):
        """测试进度回调"""
        progress_calls = []

        async def mock_progress(progress=None, message=None):
            progress_calls.append({"progress": progress, "message": message})

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "with_progress.pptx"
            await generate_pptx_file_enhanced(filepath, sample_outline, mock_request, update_progress=mock_progress)
            assert filepath.exists()
            assert len(progress_calls) >= 1, "Progress callback should be called at least once"

    @pytest.mark.asyncio
    async def test_json_snapshot_matches_outline(self, mock_request, sample_outline):
        """测试 JSON 快照与输入大纲一致"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "snapshot_test.pptx"
            await generate_pptx_file_enhanced(filepath, sample_outline, mock_request)

            json_path = filepath.parent / f"{filepath.stem}_slides.json"
            with open(json_path, "r", encoding="utf-8") as f:
                saved_slides = json.load(f)

            # 比较原始大纲的 slides
            original_slides = sample_outline["slides"]
            assert len(saved_slides) == len(original_slides)
            for orig, saved in zip(original_slides, saved_slides):
                assert orig["title"] == saved["title"]
                assert orig["slide_type"] == saved["slide_type"]


class TestEndToEndGeneration:
    """端到端生成测试（模拟完整 API 调用流程）"""

    @pytest.mark.asyncio
    async def test_full_generation_flow(self):
        """模拟完整生成流程：大纲构建 -> 渲染 -> 文件验证"""
        req = MagicMock()
        req.template = "business"
        req.language = "zh-CN"

        outline = {
            "title": "季度业务报告",
            "subtitle": "2026 Q1",
            "slides": [
                {"slide_type": "cover", "title": "季度业务报告", "subtitle": "2026 Q1"},
                {"slide_type": "toc", "title": "议程", "content": "业绩回顾\n市场分析\n下季度计划"},
                {"slide_type": "content", "title": "业绩回顾", "content": "营收增长 25%\n用户增长 30%\n新客户 15 家"},
                {"slide_type": "chart", "title": "收入趋势", "content": "Q1: 100 万\nQ2: 120 万\nQ3: 150 万"},
                {"slide_type": "bullet", "title": "关键成就", "content": "产品上线\n团队扩张\n市场拓展"},
                {"slide_type": "end", "title": "谢谢", "subtitle": "Questions?"},
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "quarterly_report.pptx"
            await generate_pptx_file_enhanced(filepath, outline, req)

            # 验证文件
            assert filepath.exists()
            file_size = filepath.stat().st_size
            assert file_size > 10000, f"PPTX file too small: {file_size} bytes"

            # 验证是有效的 PPTX (ZIP 格式)
            import zipfile
            assert zipfile.is_zipfile(filepath), "PPTX should be a valid ZIP file"

            # 验证包含必需的 PPTX 组件
            with zipfile.ZipFile(filepath) as zf:
                names = zf.namelist()
                assert "[Content_Types].xml" in names, "PPTX should contain [Content_Types].xml"
                assert any("ppt/slides/slide" in n for n in names), "PPTX should contain slide files"

            # 验证 JSON 快照
            json_path = filepath.parent / f"{filepath.stem}_slides.json"
            assert json_path.exists()
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            assert len(saved) == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
