"""
精准影响分析模块

通过轻量级符号提取和文件级变更对比，准确识别受代码修改影响的文件范围。
"""
import ast
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

from app.utils.performance_metrics import metrics_collector

logger = logging.getLogger(__name__)


@dataclass
class ChangeSummary:
    """代码变更摘要"""
    modified_files: List[str] = field(default_factory=list)
    new_symbols: List[str] = field(default_factory=list)
    removed_symbols: List[str] = field(default_factory=list)
    modified_symbols: List[str] = field(default_factory=list)
    summary: str = ""
    dynamic_imports: List[str] = field(default_factory=list)
    analysis_time: float = 0.0


class ImpactAnalyzer:
    """精准影响分析器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)

    def analyze(self, modified_files: List[str], old_versions: Optional[Dict[str, str]] = None) -> ChangeSummary:
        """
        分析文件变更，提取符号级信息

        Args:
            modified_files: 修改的文件路径列表
            old_versions: 旧版本文件内容字典 {file_path: content}，用于对比差异

        Returns:
            ChangeSummary: 变更摘要
        """
        start_time = metrics_collector.start_timer('ImpactAnalyzer')

        summary = ChangeSummary(
            modified_files=modified_files,
        )

        all_new_symbols = []
        all_removed_symbols = []
        all_modified_symbols = []
        dynamic_import_files = []

        for file_path in modified_files:
            full_path = self.project_root / file_path

            if not full_path.exists():
                logger.warning(f"文件不存在，跳过：{file_path}")
                continue

            try:
                new_content = full_path.read_text(encoding='utf-8')

                # 提取新版本的符号
                new_symbols = self._extract_symbols(new_content, file_path)

                # 如果有旧版本，对比差异
                if old_versions and file_path in old_versions:
                    old_content = old_versions[file_path]
                    old_symbols = self._extract_symbols(old_content, file_path)

                    new_symbol_names = {s['name'] for s in new_symbols}
                    old_symbol_names = {s['name'] for s in old_symbols}

                    all_new_symbols.extend(
                        s for s in new_symbols if s['name'] not in old_symbol_names
                    )
                    all_removed_symbols.extend(
                        s for s in old_symbols if s['name'] not in new_symbol_names
                    )
                    all_modified_symbols.extend(
                        s for s in new_symbols if s['name'] in old_symbol_names
                    )
                # 无基线时不做新增/修改归类：无从对比的符号不应被声称为「新增」，
                # 也不该与「修改」重叠（IA1/IA7）。

                # 检测动态导入
                if self._has_dynamic_imports(new_content):
                    dynamic_import_files.append(file_path)

            except Exception as e:
                logger.error(f"分析文件失败 {file_path}: {e}")
                continue

        # 生成变更摘要
        summary.new_symbols = [s['name'] for s in all_new_symbols]
        summary.removed_symbols = [s['name'] for s in all_removed_symbols]
        summary.modified_symbols = [s['name'] for s in all_modified_symbols]
        summary.dynamic_imports = dynamic_import_files
        summary.analysis_time = time.time() - start_time
        summary.summary = self._generate_summary(summary)

        metrics_collector.end_timer('ImpactAnalyzer', start_time, 'analyze', {'file_count': len(modified_files)})

        logger.info(
            f"影响分析完成 | 文件数：{len(modified_files)} | "
            f"新增符号：{len(summary.new_symbols)} | "
            f"删除符号：{len(summary.removed_symbols)} | "
            f"修改符号：{len(summary.modified_symbols)} | "
            f"耗时：{summary.analysis_time:.2f}s"
        )

        return summary

    def _extract_symbols(self, content: str, file_path: str) -> List[Dict[str, str]]:
        """
        提取文件中的符号（函数、类）

        Args:
            content: 文件内容
            file_path: 文件路径

        Returns:
            符号列表，每个符号包含 name, type, line_number
        """
        symbols = []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f"AST 解析失败 {file_path}: {e}")
            return symbols

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({
                    'name': node.name,
                    'type': 'function',
                    'line_number': node.lineno,
                    'file': file_path
                })
            elif isinstance(node, ast.ClassDef):
                symbols.append({
                    'name': node.name,
                    'type': 'class',
                    'line_number': node.lineno,
                    'file': file_path
                })

        return symbols

    def _has_dynamic_imports(self, content: str) -> bool:
        """
        检测文件是否包含动态导入

        Args:
            content: 文件内容

        Returns:
            是否包含动态导入
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # 非 Python 内容（JS/TS/Go 等）不做动态导入判定
            return False

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "import_module":
                return True

        return False

    def _generate_summary(self, summary: ChangeSummary) -> str:
        """
        生成人类可读的变更摘要

        Args:
            summary: 变更摘要

        Returns:
            变更摘要字符串
        """
        parts = []

        if summary.modified_files:
            parts.append(f"修改了 {len(summary.modified_files)} 个文件")

        if summary.new_symbols:
            parts.append(f"新增 {len(summary.new_symbols)} 个符号：{', '.join(summary.new_symbols[:5])}{'...' if len(summary.new_symbols) > 5 else ''}")

        if summary.removed_symbols:
            parts.append(f"删除 {len(summary.removed_symbols)} 个符号：{', '.join(summary.removed_symbols[:5])}{'...' if len(summary.removed_symbols) > 5 else ''}")

        if summary.modified_symbols:
            parts.append(f"修改 {len(summary.modified_symbols)} 个符号：{', '.join(summary.modified_symbols[:5])}{'...' if len(summary.modified_symbols) > 5 else ''}")

        if summary.dynamic_imports:
            parts.append(f"检测到 {len(summary.dynamic_imports)} 个文件包含动态导入")

        return '；'.join(parts) if parts else '无变更'
