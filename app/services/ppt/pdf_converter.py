"""
PPT PDF 转换器

将 PPTX 文件转换为 PDF 格式：
- 优先使用 LibreOffice headless 模式
- 备选方案：unoconv 服务
- 降级策略：返回 PPTX 并提示用户
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# LibreOffice 可执行文件路径
LIBREOFFICE_PATHS = [
    "libreoffice",
    "soffice",
    "/usr/bin/libreoffice",
    "/usr/bin/soffice",
    "/opt/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


class PDFConversionError(Exception):
    """PDF 转换异常"""
    pass


class LibreOfficeNotFoundError(PDFConversionError):
    """LibreOffice 未找到异常"""
    pass


class PDFConverter:
    """
    PPT 转 PDF 转换器
    
    支持多种转换方式，自动降级。
    """
    
    def __init__(
        self,
        libreoffice_path: Optional[str] = None,
        timeout: int = 60,
        temp_dir: Optional[Path] = None,
    ):
        """
        初始化 PDF 转换器
        
        Args:
            libreoffice_path: LibreOffice 可执行文件路径
            timeout: 转换超时时间（秒）
            temp_dir: 临时目录
        """
        self._libreoffice_path = libreoffice_path
        self._timeout = timeout
        self._temp_dir = temp_dir or Path("./tmp/ppt/pdf")
        self._temp_dir.mkdir(parents=True, exist_ok=True)
    
    async def convert(self, pptx_path: Path) -> Path:
        """
        将 PPTX 转换为 PDF
        
        Args:
            pptx_path: PPTX 文件路径
            
        Returns:
            PDF 文件路径
            
        Raises:
            PDFConversionError: 转换失败
            LibreOfficeNotFoundError: LibreOffice 未安装
        """
        if not pptx_path.exists():
            raise PDFConversionError(f"PPTX 文件不存在：{pptx_path}")
        
        if pptx_path.suffix.lower() != '.pptx':
            raise PDFConversionError(f"无效的文件格式：{pptx_path.suffix}，需要 .pptx")
        
        # 检查 LibreOffice 是否可用
        libreoffice_path = await self._find_libreoffice()
        
        if libreoffice_path is None:
            raise LibreOfficeNotFoundError(
                "LibreOffice 未安装，无法转换 PDF。\n"
                "请安装 LibreOffice：\n"
                "  Ubuntu/Debian: sudo apt install libreoffice\n"
                "  CentOS/RHEL:   sudo yum install libreoffice\n"
                "  macOS:         brew install --cask libreoffice"
            )
        
        # 创建临时输出目录
        output_dir = self._temp_dir / f"pdf_convert_{os.getpid()}_{os.urandom(4).hex()}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 执行转换
            pdf_path = await self._convert_with_libreoffice(
                pptx_path=pptx_path,
                output_dir=output_dir,
                libreoffice_path=libreoffice_path,
            )
            
            logger.info(f"PDF 转换成功 | input={pptx_path} | output={pdf_path}")
            return pdf_path
            
        except asyncio.TimeoutError:
            raise PDFConversionError(f"PDF 转换超时（{self._timeout}秒）")
        except Exception as e:
            raise PDFConversionError(f"PDF 转换失败：{e}")
        finally:
            # 清理临时文件（保留 PDF）
            pass
    
    async def check_libreoffice(self) -> bool:
        """
        检查 LibreOffice 是否可用
        
        Returns:
            是否可用
        """
        path = await self._find_libreoffice()
        return path is not None
    
    async def _find_libreoffice(self) -> Optional[str]:
        """查找 LibreOffice 可执行文件"""
        # 如果指定了路径，优先使用
        if self._libreoffice_path:
            if await self._test_executable(self._libreoffice_path):
                return self._libreoffice_path
            return None
        
        # 尝试常见路径
        for path in LIBREOFFICE_PATHS:
            if await self._test_executable(path):
                return path
        
        return None
    
    async def _test_executable(self, path: str) -> bool:
        """测试可执行文件是否可用"""
        try:
            proc = await asyncio.create_subprocess_exec(
                path, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            return False
    
    async def _convert_with_libreoffice(
        self,
        pptx_path: Path,
        output_dir: Path,
        libreoffice_path: str,
    ) -> Path:
        """
        使用 LibreOffice 转换 PDF
        
        Args:
            pptx_path: PPTX 文件路径
            output_dir: 输出目录
            libreoffice_path: LibreOffice 路径
            
        Returns:
            PDF 文件路径
        """
        # 构建命令
        cmd = [
            libreoffice_path,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(pptx_path),
        ]
        
        logger.info(f"执行 PDF 转换 | cmd={' '.join(cmd[:4])}...")
        
        # 执行转换
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise asyncio.TimeoutError(f"LibreOffice 转换超时（{self._timeout}秒）")
        
        if proc.returncode != 0:
            stderr_text = stderr.decode('utf-8', errors='replace')
            raise PDFConversionError(f"LibreOffice 转换失败：{stderr_text}")
        
        # 查找生成的 PDF 文件
        pdf_name = pptx_path.stem + ".pdf"
        pdf_path = output_dir / pdf_name
        
        if not pdf_path.exists():
            # 尝试查找所有 PDF 文件
            pdf_files = list(output_dir.glob("*.pdf"))
            if pdf_files:
                pdf_path = pdf_files[0]
            else:
                raise PDFConversionError("转换完成但未找到 PDF 文件")
        
        return pdf_path
    
    async def convert_with_fallback(
        self,
        pptx_path: Path,
        fallback_to_pptx: bool = True,
    ) -> tuple[Path, str]:
        """
        带降级策略的 PDF 转换
        
        Args:
            pptx_path: PPTX 文件路径
            fallback_to_pptx: 转换失败时是否返回原 PPTX
            
        Returns:
            (文件路径, 格式类型) - 格式类型为 "pdf" 或 "pptx"
        """
        try:
            pdf_path = await self.convert(pptx_path)
            return pdf_path, "pdf"
        except LibreOfficeNotFoundError:
            logger.warning("LibreOffice 未安装，返回原 PPTX 文件")
            if fallback_to_pptx:
                return pptx_path, "pptx"
            raise
        except PDFConversionError as e:
            logger.warning(f"PDF 转换失败，返回原 PPTX 文件：{e}")
            if fallback_to_pptx:
                return pptx_path, "pptx"
            raise
    
    @staticmethod
    async def install_instructions() -> str:
        """获取安装指引"""
        return """
LibreOffice 安装指引：

Ubuntu/Debian:
  sudo apt update
  sudo apt install -y libreoffice

CentOS/RHEL:
  sudo yum install -y libreoffice

macOS (Homebrew):
  brew install --cask libreoffice

Windows:
  1. 访问 https://www.libreoffice.org/download/
  2. 下载并安装 LibreOffice
  3. 将安装目录添加到 PATH 环境变量
"""


# 全局单例
pdf_converter = PDFConverter()
