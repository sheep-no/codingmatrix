"""Filesystem locations shared across layers.

Generated project artifacts are addressed by both the Web layer and the agent
runtime. Keeping the base directory in the core layer lets both depend on it,
instead of the runtime importing the Web layer for a single path constant.
"""

from __future__ import annotations

from pathlib import Path

# 仓库/镜像根目录（app/core/paths.py 向上三级）。
# 基于 __file__ 的绝对路径：api、scheduler、celery 多进程入口的工作目录
# 可能各不相同，相对路径（"./projects"）会随 CWD 漂移导致生成物目录不可预测。
_REPO_ROOT = Path(__file__).resolve().parents[2]

PROJECTS_BASE_DIR = str(_REPO_ROOT / "projects")
