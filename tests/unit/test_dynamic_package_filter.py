"""动态包过滤的回归（DPM5）。"""
from app.utils.dynamic_package_manager import DynamicPackageManager


def test_filter_packages_rejects_unevaluated_package():
    manager = DynamicPackageManager()

    allowed, rejected = manager.filter_packages(
        ["redis", "requests2", "totally-unknown-package-xyz"]
    )

    assert "redis" in allowed
    assert "requests2" in rejected
    assert "totally-unknown-package-xyz" in rejected
