"""
Agent 公共工具函数
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def clean_code_block(content: str) -> str:
    """从 LLM 输出中提取代码块

    支持 ```python ... ```、``` ... ``` 等格式。
    如果没有代码块标记，返回原始内容（strip 后）。
    """
    pattern = r'```(?:\w+)?\s*(.*?)\s*```'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


def extract_engineer_content(
    content: Optional[str],
    engineer,
    output_dir: Path,
    file_path: str,
    fix_imports_fn=None,
    all_files=None
) -> Optional[str]:
    """从工程师输出中提取最终文件内容

    统一处理三种情况：
    1. 工程师通过工具直接编辑了文件（get_edited_files）
    2. 工程师返回了编辑标记（JSON）
    3. 工程师返回了完整文件内容

    Args:
        content: 工程师返回的原始内容
        engineer: 工程师实例（需提供 get_edited_files 方法）
        output_dir: 项目输出目录
        file_path: 文件相对路径
        fix_imports_fn: 可选的 import 修复函数 (content, file_path, all_files) -> fixed_content
        all_files: 所有文件列表（用于 import 修复）

    Returns:
        提取后的文件内容，失败返回 None
    """
    edited_files = engineer.get_edited_files()

    if edited_files:
        full_path = output_dir / file_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            if fix_imports_fn and all_files:
                fixed = fix_imports_fn(content, file_path, all_files)
                if fixed != content:
                    full_path.write_text(fixed, encoding='utf-8')
                    content = fixed
            logger.info(f"工程师通过工具直接编辑了文件: {file_path}，跳过写入步骤")
            return content
        else:
            logger.error(f"工程师报告编辑了文件但文件不存在: {file_path}")
            return None

    if content and _is_edit_marker(content):
        full_path = output_dir / file_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            if fix_imports_fn and all_files:
                fixed = fix_imports_fn(content, file_path, all_files)
                if fixed != content:
                    full_path.write_text(fixed, encoding='utf-8')
                    content = fixed
            logger.info(f"工程师返回编辑标记: {file_path}，读取已修改文件")
            return content
        else:
            logger.error(f"工程师返回编辑标记但文件不存在: {file_path}")
            return None

    if content:
        content = clean_code_block(content)
        if fix_imports_fn and all_files:
            content = fix_imports_fn(content, file_path, all_files)
        return content

    return None


def _is_edit_marker(content: str) -> bool:
    """检查内容是否是编辑标记（JSON 格式）"""
    stripped = content.strip()
    if not stripped.startswith('{'):
        return False
    try:
        import json
        obj = json.loads(stripped)
        return isinstance(obj, dict) and ("action" in obj or "operation" in obj)
    except (json.JSONDecodeError, ValueError):
        return False


def write_file_atomic(output_dir: Path, file_path: str, content: str) -> bool:
    """原子写入文件：先写临时文件，完成后重命名

    Args:
        output_dir: 项目输出目录
        file_path: 文件相对路径
        content: 文件内容

    Returns:
        是否成功
    """
    full_path = output_dir / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = full_path.with_suffix(full_path.suffix + '.tmp')

    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        tmp_path.rename(full_path)
        return True
    except Exception as e:
        logger.error(f"原子写入失败: {file_path}, {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def cleanup_temp_files(output_dir: Path, file_path: str):
    """清理未完成的临时文件"""
    full_path = output_dir / file_path
    tmp_path = full_path.with_suffix(full_path.suffix + '.tmp')
    if tmp_path.exists():
        logger.warning(f"发现未完成的文件，删除: {tmp_path}")
        tmp_path.unlink()
