"""Filesystem locations shared across layers.

Generated project artifacts are addressed by both the Web layer and the agent
runtime. Keeping the base directory in the core layer lets both depend on it,
instead of the runtime importing the Web layer for a single path constant.
"""

from __future__ import annotations

PROJECTS_BASE_DIR = "./projects"
