"""
ConsistencyChecker - 简化版一致性检查

v4.7.0 新增：
- 检查 OpenAPI schema 是否漂移
- 检查导出函数签名是否变化
- 检查配置文件是否被意外修改
- 只记录不阻断（低风险）

使用场景：
- 增量修改后确认"旧行为没被破坏"
- 文件生成后快速验证
"""

import ast
import re
import json
import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SchemaDrift:
    """Schema 漂移记录"""
    file_path: str
    drift_type: str  # 'signature', 'schema', 'config', 'import'
    old_value: str
    new_value: str
    severity: str = "warning"  # 'error', 'warning', 'info'


class ConsistencyChecker:
    """简化版一致性检查器"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.drift_records: List[SchemaDrift] = []

    def check_all(self, original_dir: Optional[Path] = None) -> List[SchemaDrift]:
        """执行所有一致性检查"""
        self.drift_records = []

        if not original_dir:
            logger.info("无原始项目目录，跳过一致性检查")
            return []

        # 1. 检查导出函数签名
        self._check_signature_drift(original_dir)

        # 2. 检查配置文件
        self._check_config_drift(original_dir)

        # 3. 检查 OpenAPI schema（如果有）
        self._check_openapi_drift(original_dir)

        if self.drift_records:
            logger.warning(f"发现 {len(self.drift_records)} 处一致性漂移")
            for drift in self.drift_records:
                logger.warning(f"  [{drift.severity}] {drift.drift_type}: {drift.file_path}")

        return self.drift_records

    def _check_signature_drift(self, original_dir: Path):
        """检查导出函数签名是否变化"""
        original_signatures = self._extract_signatures(original_dir)
        new_signatures = self._extract_signatures(self.output_dir)

        for func_key, old_sig in original_signatures.items():
            if func_key not in new_signatures:
                self.drift_records.append(SchemaDrift(
                    file_path=func_key.split("::")[0],
                    drift_type="signature",
                    old_value=old_sig,
                    new_value="[已删除]",
                    severity="error"
                ))
            elif new_signatures[func_key] != old_sig:
                self.drift_records.append(SchemaDrift(
                    file_path=func_key.split("::")[0],
                    drift_type="signature",
                    old_value=old_sig,
                    new_value=new_signatures[func_key],
                    severity="warning"
                ))

    def _extract_signatures(self, directory: Path) -> Dict[str, str]:
        """从 Python 文件中提取函数签名"""
        signatures = {}
        for py_file in directory.rglob("*.py"):
            try:
                content = py_file.read_text(encoding='utf-8')
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # 只记录导出函数（不以 _ 开头）
                        if not node.name.startswith('_'):
                            func_key = f"{py_file.relative_to(directory)}::{node.name}"
                            args = [arg.arg for arg in node.args.args]
                            sig = f"{node.name}({', '.join(args)})"
                            signatures[func_key] = sig
            except SyntaxError:
                continue
            except Exception as e:
                logger.debug(f"提取签名失败 {py_file}: {e}")
        return signatures

    def _check_config_drift(self, original_dir: Path):
        """检查配置文件是否被意外修改"""
        config_files = ['requirements.txt', 'package.json', 'Dockerfile', '.env.example']

        for config_name in config_files:
            original_file = original_dir / config_name
            new_file = self.output_dir / config_name

            if original_file.exists() and new_file.exists():
                try:
                    original_content = original_file.read_text()
                    new_content = new_file.read_text()

                    # 检查关键依赖是否被删除
                    if config_name == 'requirements.txt':
                        original_deps = set(self._extract_dependencies(original_content))
                        new_deps = set(self._extract_dependencies(new_content))
                        removed = original_deps - new_deps
                        if removed:
                            self.drift_records.append(SchemaDrift(
                                file_path=config_name,
                                drift_type="config",
                                old_value=f"依赖: {', '.join(removed)}",
                                new_value="[已删除]",
                                severity="error"
                            ))
                except Exception as e:
                    logger.debug(f"检查配置漂移失败 {config_name}: {e}")

    def _extract_dependencies(self, content: str) -> List[str]:
        """从 requirements.txt 提取依赖名"""
        deps = []
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # 提取包名（忽略版本号）
                dep = re.split(r'[=<>!~]', line)[0].strip()
                if dep:
                    deps.append(dep)
        return deps

    def _check_openapi_drift(self, original_dir: Path):
        """检查 OpenAPI schema 是否漂移"""
        openapi_files = ['openapi.json', 'openapi.yaml', 'swagger.json']

        for openapi_name in openapi_files:
            original_file = original_dir / openapi_name
            new_file = self.output_dir / openapi_name

            if original_file.exists() and new_file.exists():
                try:
                    original_schema = self._load_openapi(original_file)
                    new_schema = self._load_openapi(new_file)

                    if original_schema and new_schema:
                        original_paths = set(original_schema.get('paths', {}).keys())
                        new_paths = set(new_schema.get('paths', {}).keys())

                        removed_paths = original_paths - new_paths
                        if removed_paths:
                            self.drift_records.append(SchemaDrift(
                                file_path=openapi_name,
                                drift_type="schema",
                                old_value=f"端点: {', '.join(removed_paths)}",
                                new_value="[已删除]",
                                severity="error"
                            ))
                except Exception as e:
                    logger.debug(f"检查 OpenAPI 漂移失败 {openapi_name}: {e}")

    def _load_openapi(self, file_path: Path) -> Optional[Dict]:
        """加载 OpenAPI 文件"""
        try:
            content = file_path.read_text()
            if file_path.suffix == '.json':
                return json.loads(content)
            else:
                # 简化处理：只提取 paths
                import yaml
                return yaml.safe_load(content)
        except Exception:
            return None

    def get_drift_report(self) -> str:
        """生成漂移报告"""
        if not self.drift_records:
            return "一致性检查通过，未发现漂移"

        lines = [f"一致性检查发现 {len(self.drift_records)} 处漂移:", ""]
        for drift in self.drift_records:
            lines.append(f"[{drift.severity.upper()}] {drift.drift_type}")
            lines.append(f"  文件: {drift.file_path}")
            lines.append(f"  旧值: {drift.old_value}")
            lines.append(f"  新值: {drift.new_value}")
            lines.append("")

        return "\n".join(lines)