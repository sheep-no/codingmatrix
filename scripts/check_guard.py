"""
守护合约 CI 检查脚本

在 CI 中运行，检测安全文件变更，分级警告。
绝不直接拒绝，最终决策权始终归用户：
  - 🔴 严重：暂停并详列风险，用户确认后放行
  - 🟡 警告：暂停并简列风险，用户确认后放行
  - 🟢 通知：仅记录，不暂停

用法:
    python scripts/check_guard.py [--base <commit> --head <commit> --target app/]
    python scripts/check_guard.py --diff-file <diff_file> --target app/

GitHub Actions 示例:
    - name: Check Guard Contracts
      run: python scripts/check_guard.py --target app/
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.guard_contracts import (
    GuardContracts, Severity, Violation,
    get_guard_contracts, check_file_against_contracts,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def get_changed_files(base: str = "HEAD~1", head: str = "HEAD") -> List[Tuple[str, str]]:
    """
    获取 git 变更文件列表

    Returns:
        [(file_path, status), ...]  status: A(added), M(modified), D(deleted)
    """
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-status', base, head],
            capture_output=True, text=True, check=True
        )
        changed = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) == 2:
                status, path = parts
                changed.append((path, status))
            elif len(parts) == 3:
                status, old_path, new_path = parts
                changed.append((new_path, status))
        return changed
    except subprocess.CalledProcessError as e:
        logger.error(f"Git diff 失败: {e}")
        return []


def get_changed_files_from_diff(diff_file: str) -> List[Tuple[str, str]]:
    """从 diff 文件中解析变更文件"""
    changed = []
    current_file = None
    with open(diff_file, 'r') as f:
        for line in f:
            if line.startswith('--- a/'):
                current_file = line[6:].strip()
            elif line.startswith('+++ b/') and current_file:
                current_file = line[6:].strip()
                changed.append((current_file, 'M'))
    return changed


def check_file_content(file_path: str, target_dir: str) -> List[Violation]:
    """检查文件内容是否违反守护合约"""
    full_path = Path(target_dir) / file_path
    if not full_path.exists():
        return []

    try:
        content = full_path.read_text(encoding='utf-8')
        return check_file_against_contracts(file_path, content)
    except Exception as e:
        logger.error(f"读取文件失败 {file_path}: {e}")
        return []


def categorize_violations(violations: List[Violation]) -> Dict[str, List[Violation]]:
    """按严重级别分类违规项"""
    result = {
        Severity.CRITICAL: [],
        Severity.WARNING: [],
        Severity.NOTICE: [],
    }
    for v in violations:
        if v.severity in result:
            result[v.severity].append(v)
    return result


def format_report(violations_by_severity: Dict[str, List[Violation]]) -> str:
    """格式化检查报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("守护合约检查报告 (Guard Contracts Check Report)")
    lines.append("=" * 60)
    lines.append("")

    total = sum(len(v) for v in violations_by_severity.values())
    if total == 0:
        lines.append("✅ 所有文件均符合守护合约规则")
        return '\n'.join(lines)

    lines.append(f"共发现 {total} 项需要注意的变更")
    lines.append("")

    # 🔴 严重
    critical = violations_by_severity.get(Severity.CRITICAL, [])
    if critical:
        lines.append(f"🔴 严重 ({len(critical)} 项)")
        lines.append("-" * 40)
        for v in critical:
            lines.append(f"  [{v.rule_id}] {v.file_path}")
            lines.append(f"    {v.description}")
            lines.append(f"    建议: {v.suggestion}")
            lines.append("")
        lines.append("⚠️  以上变更存在较高风险，请确认后再继续。")
        lines.append("")

    # 🟡 警告
    warnings = violations_by_severity.get(Severity.WARNING, [])
    if warnings:
        lines.append(f"🟡 警告 ({len(warnings)} 项)")
        lines.append("-" * 40)
        for v in warnings:
            lines.append(f"  [{v.rule_id}] {v.file_path}")
            lines.append(f"    {v.description}")
            lines.append(f"    建议: {v.suggestion}")
            lines.append("")
        lines.append("⚠️  以上变更可能影响较大，请确认风险可控。")
        lines.append("")

    # 🟢 通知
    notices = violations_by_severity.get(Severity.NOTICE, [])
    if notices:
        lines.append(f"🟢 通知 ({len(notices)} 项)")
        lines.append("-" * 40)
        for v in notices:
            lines.append(f"  [{v.rule_id}] {v.file_path}")
            lines.append(f"    {v.description}")
            lines.append("")
        lines.append("ℹ️  以上变更已记录，无需额外操作。")
        lines.append("")

    lines.append("=" * 60)
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='守护合约 CI 检查')
    parser.add_argument('--base', default='HEAD~1', help='基准 commit (默认: HEAD~1)')
    parser.add_argument('--head', default='HEAD', help='目标 commit (默认: HEAD)')
    parser.add_argument('--diff-file', help='Diff 文件路径')
    parser.add_argument('--target', default='app', help='目标目录 (默认: app)')
    parser.add_argument('--json-output', help='JSON 输出文件路径')
    parser.add_argument('--no-fail', action='store_true', help='即使有严重违规也不返回错误码')
    args = parser.parse_args()

    # 获取变更文件
    if args.diff_file:
        changed_files = get_changed_files_from_diff(args.diff_file)
    else:
        changed_files = get_changed_files(args.base, args.head)

    if not changed_files:
        logger.info("未发现变更文件，跳过检查")
        return

    logger.info(f"发现 {len(changed_files)} 个变更文件")

    # 检查每个变更文件
    all_violations = []
    for file_path, status in changed_files:
        # 只检查 Python 文件
        if not file_path.endswith('.py'):
            continue

        if status == 'D':
            # 删除文件：检查是否受保护
            contracts = get_guard_contracts()
            rules = contracts.get_rules_for_file(file_path)
            if rules:
                all_violations.append(Violation(
                    rule_id="GC-DEL",
                    severity=Severity.CRITICAL,
                    description=f"受保护文件被删除: {file_path}",
                    file_path=file_path,
                    suggestion="请确认是否有意删除此文件。",
                ))
            continue

        violations = check_file_content(file_path, args.target)
        all_violations.extend(violations)

    # 分类并输出
    violations_by_severity = categorize_violations(all_violations)
    report = format_report(violations_by_severity)
    print(report)

    # JSON 输出
    if args.json_output:
        output = {
            "total_violations": len(all_violations),
            "critical": len(violations_by_severity[Severity.CRITICAL]),
            "warning": len(violations_by_severity[Severity.WARNING]),
            "notice": len(violations_by_severity[Severity.NOTICE]),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "description": v.description,
                    "file_path": v.file_path,
                    "line": v.line,
                    "suggestion": v.suggestion,
                }
                for v in all_violations
            ],
        }
        Path(args.json_output).write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        logger.info(f"JSON 报告已写入: {args.json_output}")

    # 返回码
    if not args.no_fail:
        if violations_by_severity[Severity.CRITICAL]:
            logger.info("🔴 存在严重级别违规，返回码 1")
            sys.exit(1)
        elif violations_by_severity[Severity.WARNING]:
            logger.info("🟡 存在警告级别违规，返回码 0 (仅通知)")
            sys.exit(0)
    else:
        logger.info("📋 已输出报告 (--no-fail 模式，始终返回 0)")

    sys.exit(0)


if __name__ == '__main__':
    main()
