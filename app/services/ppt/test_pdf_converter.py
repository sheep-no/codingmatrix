"""
PPT PDF 转换器单元测试

测试 PDF 转换器的核心功能：
- LibreOffice 检测
- 文件转换
- 超时处理
- 降级策略
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.ppt.pdf_converter import (
    PDFConverter,
    PDFConversionError,
    LibreOfficeNotFoundError,
)


@pytest.fixture
def converter(tmp_path):
    """创建 PDF 转换器实例"""
    return PDFConverter(
        temp_dir=tmp_path / "pdf_convert",
        timeout=30,
    )


@pytest.fixture
def sample_pptx(tmp_path):
    """创建示例 PPTX 文件"""
    pptx_path = tmp_path / "test_presentation.pptx"
    pptx_path.write_text("Mock PPTX content")
    return pptx_path


class TestPDFConverter:
    """PDF 转换器测试类"""
    
    @pytest.mark.asyncio
    async def test_find_libreoffice_not_found(self, converter):
        """测试找不到 LibreOffice"""
        with patch.object(converter, '_test_executable', return_value=False):
            result = await converter._find_libreoffice()
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_find_libreoffice_found(self, converter):
        """测试找到 LibreOffice"""
        async def mock_test(path):
            return path == "/usr/bin/libreoffice"
        
        with patch.object(converter, '_test_executable', side_effect=mock_test):
            result = await converter._find_libreoffice()
            
            assert result == "/usr/bin/libreoffice"
    
    @pytest.mark.asyncio
    async def test_find_libreoffice_custom_path(self, tmp_path):
        """测试使用自定义路径"""
        custom_path = str(tmp_path / "custom_libreoffice")
        converter = PDFConverter(
            libreoffice_path=custom_path,
            temp_dir=tmp_path / "pdf_convert",
        )
        
        with patch.object(converter, '_test_executable', return_value=True):
            result = await converter._find_libreoffice()
            
            assert result == custom_path
    
    @pytest.mark.asyncio
    async def test_check_libreoffice_true(self, converter):
        """测试 LibreOffice 可用"""
        with patch.object(converter, '_find_libreoffice', return_value="/usr/bin/libreoffice"):
            result = await converter.check_libreoffice()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_libreoffice_false(self, converter):
        """测试 LibreOffice 不可用"""
        with patch.object(converter, '_find_libreoffice', return_value=None):
            result = await converter.check_libreoffice()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_convert_pptx_not_exists(self, converter, tmp_path):
        """测试转换不存在的 PPTX 文件"""
        non_existent = tmp_path / "non_existent.pptx"
        
        with pytest.raises(PDFConversionError):
            await converter.convert(non_existent)
    
    @pytest.mark.asyncio
    async def test_convert_invalid_extension(self, converter, tmp_path):
        """测试转换非 PPTX 文件"""
        invalid_file = tmp_path / "test.docx"
        invalid_file.write_text("Mock DOCX")
        
        with pytest.raises(PDFConversionError):
            await converter.convert(invalid_file)
    
    @pytest.mark.asyncio
    async def test_convert_libreoffice_not_found(self, converter, sample_pptx):
        """测试 LibreOffice 未安装时抛出异常"""
        with patch.object(converter, '_find_libreoffice', return_value=None):
            with pytest.raises(LibreOfficeNotFoundError) as exc_info:
                await converter.convert(sample_pptx)
            
            assert "未安装" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_convert_success(self, converter, sample_pptx, tmp_path):
        """测试成功转换 PDF"""
        # 创建预期的 PDF 文件
        output_dir = tmp_path / "pdf_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_pdf = output_dir / "test_presentation.pdf"
        expected_pdf.write_text("Mock PDF content")
        
        # 模拟转换过程
        async def mock_convert(*args, **kwargs):
            return expected_pdf
        
        with patch.object(converter, '_find_libreoffice', return_value="/usr/bin/libreoffice"):
            with patch.object(converter, '_convert_with_libreoffice', new=mock_convert):
                result = await converter.convert(sample_pptx)
                
                assert result == expected_pdf
                assert result.exists()
    
    @pytest.mark.asyncio
    async def test_convert_timeout(self, converter, sample_pptx):
        """测试转换超时"""
        async def mock_timeout(*args, **kwargs):
            raise asyncio.TimeoutError("转换超时")
        
        with patch.object(converter, '_find_libreoffice', return_value="/usr/bin/libreoffice"):
            with patch.object(converter, '_convert_with_libreoffice', new=mock_timeout):
                with pytest.raises(PDFConversionError):
                    await converter.convert(sample_pptx)
    
    @pytest.mark.asyncio
    async def test_convert_with_fallback_success(self, converter, sample_pptx):
        """测试带降级的成功转换"""
        output_dir = converter._temp_dir / "fallback_test"
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_pdf = output_dir / "test_presentation.pdf"
        expected_pdf.write_text("Mock PDF")
        
        async def mock_convert(*args, **kwargs):
            return expected_pdf
        
        with patch.object(converter, '_find_libreoffice', return_value="/usr/bin/libreoffice"):
            with patch.object(converter, '_convert_with_libreoffice', new=mock_convert):
                result_path, result_format = await converter.convert_with_fallback(sample_pptx)
                
                assert result_format == "pdf"
                assert result_path == expected_pdf
    
    @pytest.mark.asyncio
    async def test_convert_with_fallback_libreoffice_missing(self, converter, sample_pptx):
        """测试 LibreOffice 缺失时降级"""
        with patch.object(converter, '_find_libreoffice', return_value=None):
            result_path, result_format = await converter.convert_with_fallback(sample_pptx)
            
            # 应该返回原 PPTX 文件
            assert result_format == "pptx"
            assert result_path == sample_pptx
    
    @pytest.mark.asyncio
    async def test_convert_with_fallback_no_fallback(self, converter, sample_pptx):
        """测试禁用降级时抛出异常"""
        with patch.object(converter, '_find_libreoffice', return_value=None):
            with pytest.raises(LibreOfficeNotFoundError):
                await converter.convert_with_fallback(sample_pptx, fallback_to_pptx=False)
    
    @pytest.mark.asyncio
    async def test_test_executable_success(self, converter):
        """测试可执行文件检测成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"LibreOffice 7.0", b""))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_proc):
            result = await converter._test_executable("/usr/bin/libreoffice")
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_test_executable_failure(self, converter):
        """测试可执行文件检测失败"""
        with patch('asyncio.create_subprocess_exec', side_effect=FileNotFoundError):
            result = await converter._test_executable("/nonexistent/libreoffice")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_test_executable_timeout(self, converter):
        """测试可执行文件检测超时"""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_proc):
            result = await converter._test_executable("/usr/bin/libreoffice")
            
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
