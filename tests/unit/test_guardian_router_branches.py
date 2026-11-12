"""guardian_router 全分支回归。"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v2 import guardian_router as gr
from app.models.server_config import ServerConfig
from app.schema.guardian import StartGuard


class FakeGuardian:
    def __init__(self):
        self.config_manager = MagicMock()
        self.config_manager.configs = {}
        self.config_manager.get_enabled_services.return_value = []
        self.service_state = {}
        self.restart_count = {}
        self.is_port_open = AsyncMock(return_value=True)
        self.watch_port = AsyncMock()
        self.config_manager.get_or_create_config.return_value = {}


@pytest.fixture
def guardian(monkeypatch):
    fake = FakeGuardian()
    monkeypatch.setattr(gr, "get_guardian", lambda: fake)
    return fake


@pytest.fixture
def disabled_rate_limit(monkeypatch):
    from app.services.rate_limit_config import rate_limit_config

    monkeypatch.setattr(rate_limit_config, "set_enabled", lambda enabled: None)


class TestGuardianSingleton:
    def test_get_guardian_builds_instance(self, monkeypatch):
        gr.get_guardian.cache_clear()
        guard = MagicMock(return_value="guardian")
        monkeypatch.setattr(gr, "AsyncSmartGuardian", guard)
        assert gr.get_guardian() == "guardian"
        assert gr.get_guardian() == "guardian"
        guard.assert_called_once_with(check_interval=10)
        gr.get_guardian.cache_clear()


class TestPermissions:
    @pytest.mark.asyncio
    async def test_require_admin_rejects(self, monkeypatch):
        monkeypatch.setattr(gr, "is_admin", lambda level: False)
        with pytest.raises(HTTPException) as exc:
            await gr.require_admin({"permission_level": "user"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_admin_allows(self, monkeypatch):
        monkeypatch.setattr(gr, "is_admin", lambda level: True)
        token = await gr.require_admin({"permission_level": "admin"})
        assert token["permission_level"] == "admin"

    @pytest.mark.asyncio
    async def test_require_superadmin_rejects(self, monkeypatch):
        monkeypatch.setattr(gr, "is_superadmin", lambda level: False)
        with pytest.raises(HTTPException) as exc:
            await gr.require_superadmin({"permission_level": "admin"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_superadmin_allows(self, monkeypatch):
        monkeypatch.setattr(gr, "is_superadmin", lambda level: True)
        assert await gr.require_superadmin({"permission_level": "superadmin"})


class TestGuardEndpoints:
    @pytest.mark.asyncio
    async def test_start_guard(self, guardian, monkeypatch):
        created = []
        monkeypatch.setattr(gr.asyncio, "create_task", lambda coro: created.append(coro))
        cfg = {}
        guardian.config_manager.get_or_create_config.return_value = cfg
        result = await gr.start_guard(
            StartGuard(service_name="web", port=8000, restart_cmd="python app.py"),
            {"sub": "1"},
        )
        assert result["status"] == "success"
        assert cfg["restart_cmd"] == "python app.py"
        assert cfg["auto_start"] is True
        guardian.config_manager.save_configs.assert_called_once()
        assert created

    @pytest.mark.asyncio
    async def test_rename_service(self, guardian):
        result = await gr.rename_service(8000, "sig", "new", {"sub": "1"})
        assert result["status"] == "success"
        guardian.config_manager.update_display_name.assert_called_once_with(8000, "sig", "new")

    @pytest.mark.asyncio
    async def test_list_services(self, guardian):
        guardian.config_manager.configs = {"1_a": {"name": "a"}}
        guardian.config_manager.get_enabled_services.return_value = [{"name": "a"}]
        result = await gr.list_services({"sub": "1"})
        assert result["learned"] == 1
        assert result["enabled"] == 1


class TestFuseConfig:
    @pytest.mark.asyncio
    async def test_update_missing(self, guardian):
        result = await gr.update_fuse_config(1, "sig", token={"sub": "1"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_update_success_resets_state(self, guardian):
        cfg = {"name": "svc"}
        guardian.config_manager.configs = {"1_sig": cfg}
        guardian.service_state["svc"] = {"state": "fused", "fuse_retry_count": 5}
        result = await gr.update_fuse_config(
            1, "sig", fuse_enabled=False, fuse_cooldown=10, fuse_retry_times=2,
            token={"sub": "1"},
        )
        assert result["status"] == "success"
        assert cfg["fuse_enabled"] is False
        assert guardian.service_state["svc"]["state"] == "normal"
        guardian.config_manager.save_configs.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_success_without_state(self, guardian):
        cfg = {"name": "svc"}
        guardian.config_manager.configs = {"1_sig": cfg}
        result = await gr.update_fuse_config(1, "sig", token={"sub": "1"})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_status_missing_service(self, guardian):
        with pytest.raises(HTTPException) as exc:
            await gr.get_fuse_status("nope", {"sub": "1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_status_fused(self, guardian):
        guardian.config_manager.configs = {"1_sig": {"name": "svc", "fuse_retry_times": 3}}
        guardian.service_state["svc"] = {
            "state": "fused",
            "last_fuse_time": time.time() - 10,
            "cooldown": 100,
            "fuse_retry_count": 2,
        }
        guardian.restart_count["svc"] = 4
        result = await gr.get_fuse_status("svc", {"sub": "1"})
        assert result["state"] == "fused"
        assert result["restart_count"] == 4
        assert 80 <= result["cooldown_remaining"] <= 100

    @pytest.mark.asyncio
    async def test_status_unknown(self, guardian):
        guardian.config_manager.configs = {"1_sig": {"name": "svc"}}
        result = await gr.get_fuse_status("svc", {"sub": "1"})
        assert result["state"] == "unknown"
        assert result["cooldown_remaining"] == 0


class TestHealth:
    @pytest.mark.asyncio
    async def test_open(self, guardian):
        result = await gr.check_health(8000, {"sub": "1"})
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_closed(self, guardian):
        guardian.is_port_open.return_value = False
        result = await gr.check_health(8000, {"sub": "1"})
        assert result["status"] == "closed"


class TestConfigEndpoints:
    @pytest.mark.asyncio
    async def test_get_all_configs(self, monkeypatch):
        rcs = MagicMock()
        rcs.get_all_configs = AsyncMock(return_value={"a": "1"})
        fss = MagicMock()
        fss.get_all_feature_status = AsyncMock(return_value={"docker": True})
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        monkeypatch.setattr(gr, "feature_switch_service", fss)
        result = await gr.get_all_configs({"sub": "1"})
        assert result["configs"] == {"a": "1"}
        assert result["feature_status"] == {"docker": True}

    @pytest.mark.asyncio
    async def test_get_config_missing(self, monkeypatch):
        rcs = MagicMock()
        rcs.get_config = AsyncMock(return_value=None)
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        with pytest.raises(HTTPException) as exc:
            await gr.get_config("nope", {"sub": "1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_found(self, monkeypatch):
        rcs = MagicMock()
        rcs.get_config = AsyncMock(return_value="v")
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.get_config("k", {"sub": "1"})
        assert result["value"] == "v"

    @pytest.mark.asyncio
    async def test_batch_invalid_key(self):
        with pytest.raises(HTTPException) as exc:
            await gr.batch_update_configs(
                gr.BatchConfigUpdateRequest(configs={"bad": "1"}), {"sub": "1"}
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_batch_failure(self, monkeypatch):
        rcs = MagicMock()
        rcs.batch_update_configs = AsyncMock(return_value=False)
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        with pytest.raises(HTTPException) as exc:
            await gr.batch_update_configs(
                gr.BatchConfigUpdateRequest(configs={"db_pool_size": "3"}), {"sub": "1"}
            )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_batch_success_syncs_feature(self, monkeypatch):
        rcs = MagicMock()
        rcs.batch_update_configs = AsyncMock(return_value=True)
        fss = MagicMock()
        fss.set_feature_enabled = AsyncMock()
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        monkeypatch.setattr(gr, "feature_switch_service", fss)
        result = await gr.batch_update_configs(
            gr.BatchConfigUpdateRequest(
                configs={"feature_docker_enabled": "YES", "db_pool_size": "3"}
            ),
            {"sub": "7"},
        )
        assert result["updated_count"] == 2
        fss.set_feature_enabled.assert_awaited_once_with("docker", True, 7)

    @pytest.mark.asyncio
    async def test_update_invalid_key(self):
        with pytest.raises(HTTPException) as exc:
            await gr.update_config("bad", gr.ConfigUpdateRequest(value="1"), {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_failure(self, monkeypatch):
        rcs = MagicMock()
        rcs.set_config = AsyncMock(return_value=False)
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        with pytest.raises(HTTPException) as exc:
            await gr.update_config(
                "db_pool_size", gr.ConfigUpdateRequest(value="3"), {"sub": "1"}
            )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_update_feature_success(self, monkeypatch):
        rcs = MagicMock()
        rcs.set_config = AsyncMock(return_value=True)
        fss = MagicMock()
        fss.set_feature_enabled = AsyncMock()
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        monkeypatch.setattr(gr, "feature_switch_service", fss)
        result = await gr.update_config(
            "feature_docker_enabled",
            gr.ConfigUpdateRequest(value="off", description="d"),
            {"sub": "1"},
        )
        assert result["status"] == "success"
        fss.set_feature_enabled.assert_awaited_once_with("docker", False, 1)

    @pytest.mark.asyncio
    async def test_update_plain_config(self, monkeypatch):
        rcs = MagicMock()
        rcs.set_config = AsyncMock(return_value=True)
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.update_config(
            "db_pool_size", gr.ConfigUpdateRequest(value="3"), {"sub": "1"}
        )
        assert result["value"] == "3"

    @pytest.mark.asyncio
    async def test_server_stats(self, monkeypatch):
        rcs = MagicMock()
        rcs.get_server_stats = AsyncMock(return_value={"cpu": 1})
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.get_server_stats({"sub": "1"})
        assert result["cpu"] == 1


class TestDockerAndWs:
    @pytest.mark.asyncio
    async def test_docker_sdk_missing(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "docker":
                raise ImportError("no docker")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(HTTPException) as exc:
            await gr.list_docker_containers({"sub": "1"})
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_docker_list_success(self, monkeypatch):
        import sys
        import types

        c1 = MagicMock()
        c1.short_id = "abc"
        c1.name = "n"
        c1.image.tags = ["img:latest"]
        c1.status = "running"
        c1.attrs = {"Created": "now", "HostConfig": {"Memory": 100}}
        client = MagicMock()
        client.containers.list.return_value = [c1]
        module = types.SimpleNamespace(from_env=lambda: client)
        monkeypatch.setitem(sys.modules, "docker", module)
        rcs = MagicMock()
        rcs.get_config = AsyncMock(return_value="3")
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.list_docker_containers({"sub": "1"})
        assert result["running_count"] == 1
        assert result["containers"][0]["image"] == "img:latest"
        assert result["max_allowed"] == 3

    @pytest.mark.asyncio
    async def test_docker_list_untagged_image(self, monkeypatch):
        import sys
        import types

        c1 = MagicMock()
        c1.image.tags = []
        c1.image.short_id = "sha"
        c1.attrs = {}
        client = MagicMock()
        client.containers.list.return_value = [c1]
        monkeypatch.setitem(sys.modules, "docker", types.SimpleNamespace(from_env=lambda: client))
        rcs = MagicMock()
        rcs.get_config = AsyncMock(return_value="3")
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.list_docker_containers({"sub": "1"})
        assert result["containers"][0]["image"] == "sha"

    @pytest.mark.asyncio
    async def test_docker_error(self, monkeypatch):
        import sys
        import types

        client = MagicMock()
        client.containers.list.side_effect = RuntimeError("boom")
        monkeypatch.setitem(sys.modules, "docker", types.SimpleNamespace(from_env=lambda: client))
        monkeypatch.setattr(gr.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await gr.list_docker_containers({"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_ws_stats(self, monkeypatch):
        import app.services.websocket_manager as wsm

        manager = MagicMock()
        manager.get_connection_info = AsyncMock(
            return_value={"current": 2, "max": 10, "available": 8}
        )
        monkeypatch.setattr(wsm, "get_ws_manager", lambda: manager)
        result = await gr.get_websocket_stats({"sub": "1"})
        assert result["available"] == 8


class TestLogConfig:
    @pytest.mark.asyncio
    async def test_get_log_config(self, monkeypatch):
        service = MagicMock()
        service.get_config.return_value = {"log_level": "INFO"}
        monkeypatch.setattr(gr, "log_config_service", service)
        assert await gr.get_log_config({"sub": "1"}) == {"log_level": "INFO"}

    @pytest.mark.asyncio
    async def test_update_level_invalid(self):
        with pytest.raises(HTTPException) as exc:
            await gr.update_log_level("TRACE", token={"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_level_success(self, monkeypatch):
        service = MagicMock()
        service.set_log_level.return_value = True
        rcs = MagicMock()
        rcs.set_config = AsyncMock()
        monkeypatch.setattr(gr, "log_config_service", service)
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.update_log_level("info", "app", {"sub": "2"})
        assert result["level"] == "info"
        rcs.set_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_level_failure(self, monkeypatch):
        service = MagicMock()
        service.set_log_level.return_value = False
        monkeypatch.setattr(gr, "log_config_service", service)
        with pytest.raises(HTTPException) as exc:
            await gr.update_log_level("INFO", token={"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_update_global_invalid(self):
        with pytest.raises(HTTPException) as exc:
            await gr.update_global_log_level("BAD", {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_global_success(self, monkeypatch):
        service = MagicMock()
        service.set_global_level.return_value = True
        rcs = MagicMock()
        rcs.set_config = AsyncMock()
        monkeypatch.setattr(gr, "log_config_service", service)
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.update_global_log_level("DEBUG", {"sub": "1"})
        assert result["logger"] == "global"

    @pytest.mark.asyncio
    async def test_update_global_failure(self, monkeypatch):
        service = MagicMock()
        service.set_global_level.return_value = False
        monkeypatch.setattr(gr, "log_config_service", service)
        with pytest.raises(HTTPException) as exc:
            await gr.update_global_log_level("INFO", {"sub": "1"})
        assert exc.value.status_code == 500


class TestMemory:
    @pytest.mark.asyncio
    async def test_memory_stats(self, monkeypatch):
        info = SimpleNamespace(rss=1024 * 1024, vms=2 * 1024 * 1024)
        full = SimpleNamespace(uss=1024 * 1024)
        vm = SimpleNamespace(total=3 * 1024 * 1024, available=1024 * 1024,
                             used=2 * 1024 * 1024, percent=50.0, free=1024 * 1024)
        swap = SimpleNamespace(total=1024 * 1024, used=0, percent=0.0)
        process = MagicMock()
        process.memory_info.return_value = info
        process.memory_full_info.return_value = full
        process.memory_percent.return_value = 10.0
        psutil = SimpleNamespace(
            Process=lambda pid: process,
            virtual_memory=lambda: vm,
            swap_memory=lambda: swap,
        )
        import sys
        monkeypatch.setitem(sys.modules, "psutil", psutil)
        result = await gr.get_memory_stats({"sub": "1"})
        assert result["system"]["percent"] == 50.0
        assert result["recommendations"]["suggestions"] == ["内存使用正常"]

    def test_memory_suggestions(self):
        assert len(gr._get_memory_suggestions(95, 70)) == 2
        assert len(gr._get_memory_suggestions(85, 50)) == 2
        assert gr._get_memory_suggestions(10, 10) == ["内存使用正常"]


class TestBackups:
    @pytest.mark.asyncio
    async def test_create_backup_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(gr, "async_session", lambda: _FakeSession())
        result = await gr.create_backup({"sub": "1"})
        assert result["status"] == "success"
        assert Path(result["backup_file"]).exists()

    @pytest.mark.asyncio
    async def test_create_backup_evicts_older(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "backups"
        d.mkdir(parents=True)
        for i in range(7):
            p = d / f"config_backup_20260101_00000{i}.json"
            p.write_text("{}")
            os.utime(p, (1000 + i, 1000 + i))
        monkeypatch.setattr(gr, "async_session", lambda: _FakeSession())
        await gr.create_backup({"sub": "1"})
        assert len(list(d.glob("config_backup_*.json"))) == 5

    @pytest.mark.asyncio
    async def test_create_backup_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(gr, "async_session", _raising_session)
        monkeypatch.setattr(gr.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await gr.create_backup({"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_list_backups(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "backups"
        d.mkdir(parents=True)
        (d / "config_backup_20260101_000000.json").write_text("{}")
        result = await gr.list_backups({"sub": "1"})
        assert result["backups"][0]["filename"] == "config_backup_20260101_000000.json"
        assert result["backups"][0]["download_url"].endswith("20260101_000000")

    @pytest.mark.asyncio
    async def test_list_backups_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "glob", lambda self, pat: (_ for _ in ()).throw(RuntimeError("x")))
        monkeypatch.setattr(gr.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await gr.list_backups({"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_download_invalid_timestamp(self):
        with pytest.raises(HTTPException) as exc:
            await gr.download_backup("../../etc/passwd", {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_download_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(HTTPException) as exc:
            await gr.download_backup("20260101_000000", {"sub": "1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_bad_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "backups"
        d.mkdir(parents=True)
        (d / "config_backup_20260101_000000.json").write_text("not json")
        monkeypatch.setattr(gr.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await gr.download_backup("20260101_000000", {"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_download_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "backups"
        d.mkdir(parents=True)
        (d / "config_backup_20260101_000000.json").write_text('{"configs": {}}')
        result = await gr.download_backup("20260101_000000", {"sub": "1"})
        assert result == {"configs": {}}

    @pytest.mark.asyncio
    async def test_restore_invalid_keys(self):
        with pytest.raises(HTTPException) as exc:
            await gr.restore_backup({"configs": {"bad": {}}}, {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_restore_updates_and_inserts(self, monkeypatch):
        monkeypatch.setattr(gr, "async_session", lambda: _RestoreSession())
        rcs = MagicMock()
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.restore_backup(
            {
                "configs": {
                    "db_pool_size": {"value": "3", "description": "d"},
                    "db_max_overflow": {"value": "20"},
                }
            },
            {"sub": "1"},
        )
        assert result["restored_count"] == 2
        rcs.invalidate_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_inserts_missing(self, monkeypatch):
        session = _InsertRestoreSession()
        monkeypatch.setattr(gr, "async_session", lambda: session)
        rcs = MagicMock()
        monkeypatch.setattr(gr, "resource_config_service", rcs)
        result = await gr.restore_backup(
            {"configs": {"db_pool_size": {}}}, {"sub": "1"}
        )
        assert result["restored_count"] == 1
        assert len(session.added) == 1
        assert session.added[0].value == ""

    @pytest.mark.asyncio
    async def test_restore_error(self, monkeypatch):
        monkeypatch.setattr(gr, "async_session", _raising_session)
        monkeypatch.setattr(gr.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await gr.restore_backup({"configs": {"db_pool_size": {}}}, {"sub": "1"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_invalid_filename(self):
        with pytest.raises(HTTPException) as exc:
            await gr.delete_backup("../x.json", {"sub": "1"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(HTTPException) as exc:
            await gr.delete_backup("x.json", {"sub": "1"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "backups"
        d.mkdir(parents=True)
        target = d / "x.json"
        target.write_text("{}")
        result = await gr.delete_backup("x.json", {"sub": "1"})
        assert result["status"] == "success"
        assert not target.exists()

    @pytest.mark.asyncio
    async def test_delete_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "backups"
        d.mkdir(parents=True)
        target = d / "x.json"
        target.write_text("{}")
        monkeypatch.setattr(Path, "unlink", lambda self: (_ for _ in ()).throw(RuntimeError("x")))
        monkeypatch.setattr(gr.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await gr.delete_backup("x.json", {"sub": "1"})
        assert exc.value.status_code == 500


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_get_rate_limit(self, monkeypatch):
        import app.middleware.rate_limiter as rl

        limiter = MagicMock()
        limiter.get_stats.return_value = {"enabled": True}
        monkeypatch.setattr(rl, "rate_limiter", limiter)
        assert await gr.get_rate_limit_config({"sub": "1"}) == {"enabled": True}

    @pytest.mark.asyncio
    async def test_update_limits(self, monkeypatch):
        import app.services.rate_limit_config as rlc

        service = MagicMock()
        service.to_dict.return_value = {"enabled": True}
        monkeypatch.setattr(rlc, "rate_limit_config", service)
        cfg = gr.RateLimitUpdate(limit=5, window=10)
        await gr.update_global_rate_limit(cfg, {"sub": "1"})
        await gr.update_ip_rate_limit(cfg, {"sub": "1"})
        await gr.update_user_rate_limit(cfg, {"sub": "1"})
        service.set_global_limit.assert_called_once_with(5, 10)
        service.set_ip_limit.assert_called_once_with(5, 10)
        service.set_user_limit.assert_called_once_with(5, 10)

    @pytest.mark.asyncio
    async def test_update_endpoint_and_delete(self, monkeypatch):
        import app.services.rate_limit_config as rlc

        service = MagicMock()
        service.to_dict.return_value = {}
        monkeypatch.setattr(rlc, "rate_limit_config", service)
        cfg = gr.EndpointRateLimitUpdate(endpoint="/x", limit=5, window=10)
        await gr.update_endpoint_rate_limit(cfg, {"sub": "1"})
        service.set_endpoint_rule.assert_called_once_with("/x", 5, 10)
        await gr.delete_endpoint_rate_limit("/x", {"sub": "1"})
        service.remove_endpoint_rule.assert_called_once_with("/x")

    @pytest.mark.asyncio
    async def test_toggle(self, monkeypatch):
        import app.services.rate_limit_config as rlc

        service = MagicMock()
        monkeypatch.setattr(rlc, "rate_limit_config", service)
        result = await gr.toggle_rate_limit(False, {"sub": "1"})
        assert result["enabled"] is False
        service.set_enabled.assert_called_once_with(False)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        class _R:
            def scalars(self):
                class _S:
                    def all(self):
                        return [SimpleNamespace(key="db_pool_size", value="5", description="d")]
                return _S()
        return _R()


def _raising_session():
    class _S:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False
    return _S()


class _InsertRestoreSession:
    def __init__(self):
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        class _R:
            def scalar_one_or_none(self):
                return None
        return _R()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


class _RestoreSession:
    def __init__(self):
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        class _R:
            def __init__(self, existing):
                self._existing = existing

            def scalar_one_or_none(self):
                return self._existing
        return _R(SimpleNamespace(value="1", description="old", updated_by=0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None
