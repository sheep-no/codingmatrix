"""
阴影依赖扫描器

发现隐式依赖（eval/exec/dynamic import/env 反射等），只记录不阻断。
使用 asyncio.to_thread 避免大项目场景下阻塞事件循环。
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# 扫描已有项目时跳过的目录
SKIP_DIRS: Set[str] = {
    '__pycache__', 'node_modules', '.git', 'venv', '.venv',
    'dist', 'build', '.next', 'coverage', '.pytest_cache',
    'playwright-report', 'test-results', '.turbo'
}

# 阴影依赖检测模式
_SHADOW_PATTERNS = {
    'eval_exec': r'\beval\s*\(|\bexec\s*\(',
    'dynamic_import': r'importlib\.import_module|__import__\s*\(',
    'env_dependency': r'os\.environ\b|os\.getenv\s*\(',
    'dynamic_require': r'require\.context|import\s*\(',
    'getattr_dynamic': r'getattr\s*\([^,]+,\s*["\']',
}

# 支持的源码文件扩展名
_SOURCE_EXTENSIONS = frozenset({'.py', '.js', '.ts', '.jsx', '.tsx', '.vue'})


async def scan_shadow_dependencies(project_path: Path) -> Dict[str, List[str]]:
    """
    异步阴影依赖扫描入口。

    Args:
        project_path: 项目根目录

    Returns:
        {file_path: [发现的隐式依赖模式描述]}
    """
    return await asyncio.to_thread(_scan_sync, project_path)


def _scan_sync(project_path: Path) -> Dict[str, List[str]]:
    """同步版阴影依赖扫描 — 在线程池中执行"""
    shadow_deps: Dict[str, List[str]] = {}

    for file_path in project_path.rglob("*"):
        if any(part in SKIP_DIRS for part in file_path.parts):
            continue
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()
        if suffix not in _SOURCE_EXTENSIONS:
            continue

        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.debug(f"读取文件失败 {file_path}：{e}")
            continue

        rel_path = str(file_path.relative_to(project_path))
        found = []

        for pattern_name, regex in _SHADOW_PATTERNS.items():
            if re.search(regex, content):
                found.append(pattern_name)

        if found:
            shadow_deps[rel_path] = found

    if shadow_deps:
        logger.info(f"阴影依赖扫描发现 {len(shadow_deps)} 个文件含有隐式依赖（仅记录）")
        for path, patterns_found in shadow_deps.items():
            logger.info(f"  {path}: {', '.join(patterns_found)}")

    return shadow_deps
