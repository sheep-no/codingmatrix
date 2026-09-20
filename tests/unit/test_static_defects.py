"""静态缺陷门禁：用 ruff 的 pyflakes 规则锁定高置信度缺陷。

本仓库不启用完整 lint，只把这组规则作为门禁。它们都对应真实缺陷或明确的
结构问题，而非风格偏好：

- F821 未定义名字（运行时 NameError，字符串注解也会让 get_type_hints 失败）
- F823 局部变量在赋值前被引用（运行时 UnboundLocalError）
- F811 重复定义未使用的名字（模块级导入被函数内导入遮蔽而死掉）
- F402 导入被循环变量遮蔽
- F841 赋值后从未使用的局部变量（死代码或失效逻辑）

`tests/unit/test_orchestration_default_engine.py` 的教训是：缺陷可以在测试
全绿时长期潜伏。这里用工具兜住这一类问题，避免靠逐个测试去发现。
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = REPO_ROOT / "app" / "agent"
RULES = "F821,F823,F811,F402,F841"


def _ruff(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_agent_has_no_high_confidence_static_defects():
    if _ruff("--version").returncode != 0:
        pytest.skip("ruff 未安装，跳过静态缺陷门禁")

    result = _ruff(
        "check",
        str(TARGET_DIR),
        "--select",
        RULES,
        "--output-format",
        "concise",
        "--no-cache",
    )
    assert result.returncode == 0, (
        "app/agent 存在静态缺陷（规则 " + RULES + "）：\n" + result.stdout + result.stderr
    )
