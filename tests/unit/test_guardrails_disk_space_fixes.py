"""GRD3 回归：磁盘检查不应因目标目录尚未创建而静默放行。

原实现直接对传入路径调用 ``shutil.disk_usage``，目录不存在时抛异常并落到
``available_for_new_session=True``，磁盘门禁形同虚设。修复后先解析到最近的已存在
祖先路径再统计用量，同时用 ``check_failed`` 区分「检查失败」与「空间充足」。
"""

from __future__ import annotations

import os
import shutil

from app.utils import guardrails
from app.utils.guardrails import DiskSpaceMonitor


class TestMissingPathStillChecks:
    def test_nonexistent_dir_reports_real_usage(self, tmp_path):
        """不存在的子目录应回退到最近已存在祖先，返回真实磁盘数据。"""
        missing = tmp_path / "not" / "created" / "yet"
        status = DiskSpaceMonitor().check(str(missing))

        assert status.total_bytes > 0
        assert status.check_failed is False

    def test_nonexistent_path_matches_parent_usage(self, tmp_path):
        """不存在的路径与落盘到的祖先路径应得到同一份磁盘数据。"""
        monitor = DiskSpaceMonitor()
        status_missing = monitor.check(str(tmp_path / "ghost" / "deep"))
        status_existing = monitor.check(str(tmp_path))

        assert status_missing.total_bytes == status_existing.total_bytes
        assert status_missing.free_bytes == status_existing.free_bytes

    def test_check_failed_only_on_real_error(self, monkeypatch, tmp_path):
        """仅当底层统计真正失败时才置 check_failed。"""
        def boom(_path):
            raise OSError("simulated stat failure")

        monkeypatch.setattr(shutil, "disk_usage", boom)
        status = DiskSpaceMonitor().check(str(tmp_path))

        assert status.check_failed is True
        # 检查失败仍保持 fail-open，但状态可被消费方识别。
        assert status.available_for_new_session is True

    def test_stat_target_exists_for_missing_projects_dir(self, tmp_path, monkeypatch):
        """门禁应对存在的祖先路径做统计，而非把不存在路径喂给 disk_usage。"""
        seen: list[str] = []
        real_disk_usage = shutil.disk_usage

        def spy(path):
            seen.append(os.fspath(path))
            return real_disk_usage(path)

        monkeypatch.setattr(shutil, "disk_usage", spy)
        ctx = guardrails.get_guardrail_context()
        monkeypatch.setattr(ctx, "disk_space_monitor", DiskSpaceMonitor())

        ok, msg = guardrails.check_disk_space(str(tmp_path / "projects"))
        assert ok is True
        assert msg == ""
        assert seen and os.path.exists(seen[0])


class TestExistingPathUnchanged:
    def test_existing_dir_still_works(self, tmp_path):
        status = DiskSpaceMonitor().check(str(tmp_path))
        assert status.total_bytes > 0
        assert status.check_failed is False

    def test_default_current_directory(self):
        status = DiskSpaceMonitor().check(".")
        assert status.check_failed is False
        assert status.total_bytes > 0
