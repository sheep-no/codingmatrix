#!/usr/bin/env python3
"""
从后端 PROGRESS_LABELS 生成前端 agentPhases.js

用法：python3 scripts/generate_agent_phases.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agent.orchestrator_progress import PROGRESS_LABELS

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'constants', 'agentPhases.js')

js_lines = [
    '/**',
    ' * Agent phase 标签映射（自动生成）',
    ' *',
    ' * 来源：app/agent/orchestrator_progress.py PROGRESS_LABELS',
    ' * 请勿手动修改此文件，运行 scripts/generate_agent_phases.py 重新生成',
    ' */',
    'export const AGENT_PHASE_LABELS = Object.freeze({',
]

for key, value in PROGRESS_LABELS.items():
    # 转义单引号
    escaped_value = value.replace("'", "\\'")
    js_lines.append(f"  {key}: '{escaped_value}',")

js_lines.extend([
    '})',
    '',
    '/**',
    ' * 获取 phase 的中文标签',
    ' * @param {string} phaseKey - 后端推送的 phase 字段值',
    ' * @returns {string} 中文标签；如果未在映射表中，返回 phaseKey 本身',
    ' */',
    'export function getPhaseLabel(phaseKey) {',
    '  if (!phaseKey) return \'\'',
    '  return AGENT_PHASE_LABELS[phaseKey] || phaseKey',
    '}',
    '',
])

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(js_lines))

print(f"Generated {OUTPUT_PATH} with {len(PROGRESS_LABELS)} phases")
