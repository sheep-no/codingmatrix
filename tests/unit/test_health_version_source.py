"""健康检查版本来源统一回归（TECH-DEBT #18）。

`/api/v1/health` 返回 `v5.10.0`、`/api/v1/health/detailed` 返回 `v3.0`，
两处各自硬编码且都与 CHANGELOG 最新版本漂移。现统一到 `app.core.version`。
"""

import re
from pathlib import Path

from app.core.version import APP_VERSION
from app.api.v1 import health as health_api
from app.services.health_checker import health_checker


def _latest_released_version() -> str:
    changelog = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    match = re.search(r"^##\s+\[(\d+\.\d+\.\d+)\]", text, flags=re.MULTILINE)
    assert match, "CHANGELOG.md 缺少已发布版本条目"
    return match.group(1)


def test_app_version_matches_changelog_latest_release():
    """版本常量必须与 CHANGELOG 最新已发布版本一致，避免再次漂移。"""
    assert APP_VERSION == f"v{_latest_released_version()}"


def test_health_endpoint_uses_shared_version_constant():
    """`/health` 不再自带一份版本常量。"""
    assert health_api.APP_VERSION is APP_VERSION


def test_health_checker_uses_shared_version_constant():
    """/health/detailed 走 health_checker，其版本同源。"""
    assert health_checker._version == APP_VERSION
