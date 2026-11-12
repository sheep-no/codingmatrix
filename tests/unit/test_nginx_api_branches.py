"""Nginx 配置管理 API 全分支回归。"""

import subprocess
import builtins
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v2 import nginx_api as na
from app.schema.nginxConf import NginxDeployRequest, NginxGenerateRequest


class _Cache:
    def __init__(self):
        self.data = {}
        self.sets = []

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ttl):
        self.sets.append((key, ttl))
        self.data[key] = value


def _gen(**overrides):
    payload = {
        "platform": "linux",
        "config_type": "proxy",
        "server_name": "example.com",
        "port": 443,
    }
    payload.update(overrides)
    return NginxGenerateRequest(**payload)


def _completed(returncode=0, stderr="", stdout=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def cache(monkeypatch):
    instance = _Cache()

    async def _get_cache():
        return instance

    monkeypatch.setattr(na, "get_cache", _get_cache)
    return instance


@pytest.fixture
def allowed_dir(monkeypatch, tmp_path):
    nginx_dir = tmp_path / "nginx"
    nginx_dir.mkdir()
    monkeypatch.setattr(na, "ALLOWED_NGINX_PATHS", (nginx_dir,))
    return nginx_dir


def test_generate_config_rejects_injection():
    with pytest.raises(ValueError):
        na.generate_nginx_config(_gen(server_name="a.com; rm -rf /"))
    with pytest.raises(ValueError):
        na.generate_nginx_config(_gen(ssl_cert="$(x)"))
    with pytest.raises(ValueError):
        na.generate_nginx_config(_gen(ssl_key="a b"))
    with pytest.raises(ValueError):
        na.generate_nginx_config(_gen(upstream="ftp://x"))


@pytest.mark.parametrize("config_type", ["proxy", "loadbalancer", "static"])
def test_generate_config_types(config_type):
    config = na.generate_nginx_config(
        _gen(config_type=config_type, servers="a:1, b:2", upstream="http://u:9")
    )
    assert "server {" in config
    assert "listen 443;" in config
    if config_type == "loadbalancer":
        assert "server a:1;" in config
        assert "server b:2;" in config
    if config_type == "static":
        assert "try_files" in config


def test_generate_config_https_variants_and_gzip_toggle():
    config = na.generate_nginx_config(
        _gen(config_type="https", http2=True, gzip=False, ssl_cert=None, ssl_key=None)
    )
    assert "listen 443 ssl http2;" in config
    assert "/etc/nginx/ssl/cert.pem" in config
    assert "/etc/nginx/ssl/key.pem" in config
    assert "gzip on;" not in config

    config = na.generate_nginx_config(_gen(config_type="https"))
    assert "listen 443 ssl;" in config


def test_generate_config_loadbalancer_defaults():
    config = na.generate_nginx_config(_gen(config_type="loadbalancer"))
    assert "server localhost:3001;" in config
    assert "server localhost:3002;" in config


@pytest.mark.asyncio
async def test_generate_uses_cache_hit(cache):
    req = _gen()
    key = "nginx:generate:" + na.hashlib.md5(
        na.json.dumps(req.dict(), sort_keys=True).encode()
    ).hexdigest()
    cache.data[key] = {"config": "c", "path": "p", "message": "m"}
    result = await na.generate_nginx(req, token={"sub": "admin"})
    assert result.config == "c"
    assert cache.sets == []


@pytest.mark.asyncio
async def test_generate_linux_and_windows_paths(cache):
    result = await na.generate_nginx(_gen(nginx_path="/opt/nginx"), token={"sub": "a"})
    assert result.path == "/opt/nginx/conf.d/app.conf"
    assert cache.sets

    cache.data.clear()
    result = await na.generate_nginx(
        _gen(platform="windows", nginx_path=None, config_type="static"), token={"sub": "a"}
    )
    assert result.path == "C:/nginx/conf/app.conf"

    cache.data.clear()
    result = await na.generate_nginx(
        _gen(platform="linux", nginx_path=None), token={"sub": "a"}
    )
    assert result.path == "/etc/nginx/conf.d/app.conf"


@pytest.mark.asyncio
async def test_generate_failure_returns_500(cache, monkeypatch):
    def _boom(req):
        raise ValueError("bad")

    monkeypatch.setattr(na, "generate_nginx_config", _boom)
    with pytest.raises(HTTPException) as exc:
        await na.generate_nginx(_gen(), token={"sub": "a"})
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_check_success_removes_temp_file(monkeypatch):
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _completed(stderr="syntax is ok")

    monkeypatch.setattr(na.subprocess, "run", _run)
    payload = await na.check_nginx(
        na.NginxCheck(config="events { worker_connections 1; }"), token={"sub": "admin"}
    )
    assert payload["status"] == "ok"
    assert not Path(seen["cmd"][3]).exists()


@pytest.mark.asyncio
async def test_check_error_streams_ai_analysis(monkeypatch):
    monkeypatch.setattr(
        na.subprocess, "run", lambda *a, **k: _completed(returncode=1, stderr="bad cfg")
    )

    async def _call_llm(**kwargs):
        return "stream"

    import app.utils as app_utils

    monkeypatch.setattr(app_utils, "call_llm", _call_llm)
    response = await na.check_nginx(
        na.NginxCheck(config="events { bad; }"), token={"sub": "admin"}
    )
    assert response.media_type == "text/event-stream"
    assert response.headers["X-Error-Details"] == "bad cfg"


@pytest.mark.asyncio
async def test_check_timeout_and_missing_binary(monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="nginx", timeout=30)

    monkeypatch.setattr(na.subprocess, "run", _timeout)
    with pytest.raises(HTTPException) as exc:
        await na.check_nginx(
            na.NginxCheck(config="events { worker_connections 1; }"), token={"sub": "a"}
        )
    assert exc.value.status_code == 500
    assert "超时" in exc.value.detail

    def _missing(*a, **k):
        raise FileNotFoundError("nginx")

    monkeypatch.setattr(na.subprocess, "run", _missing)
    with pytest.raises(HTTPException) as exc:
        await na.check_nginx(
            na.NginxCheck(config="events { worker_connections 1; }"), token={"sub": "a"}
        )
    assert "未安装" in exc.value.detail


@pytest.mark.asyncio
async def test_check_generic_exception(monkeypatch):
    monkeypatch.setattr(
        na.subprocess, "run", lambda *a, **k: _completed(stderr="syntax is ok")
    )
    def _make_tmp(**kwargs):
        raise RuntimeError("x")

    monkeypatch.setattr(na.tempfile, "NamedTemporaryFile", _make_tmp)
    with pytest.raises(HTTPException) as exc:
        await na.check_nginx(
            na.NginxCheck(config="events { worker_connections 1; }"), token={"sub": "a"}
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_deploy_rejects_disallowed_path(monkeypatch):
    monkeypatch.setattr(na, "ALLOWED_NGINX_PATHS", (Path("/etc/nginx"),))
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="x", nginx_path="/tmp/evil"), token={"sub": "sa"}
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_deploy_success_with_backup(allowed_dir, monkeypatch):
    conf_d = allowed_dir / "conf.d"
    conf_d.mkdir()
    existing = conf_d / "app.conf"
    existing.write_text("old")

    monkeypatch.setattr(na.subprocess, "run", lambda *a, **k: _completed())
    result = await na.deploy_nginx(
        NginxDeployRequest(config="new", nginx_path=str(allowed_dir), backup=True),
        token={"sub": "sa"},
    )
    assert result.status == "success"
    assert existing.read_text() == "new"
    assert result.backup_path is not None
    assert Path(result.backup_path).exists()


@pytest.mark.asyncio
async def test_deploy_success_without_existing_file(allowed_dir, monkeypatch):
    monkeypatch.setattr(na.subprocess, "run", lambda *a, **k: _completed())
    result = await na.deploy_nginx(
        NginxDeployRequest(config="new", nginx_path=str(allowed_dir), backup=True),
        token={"sub": "sa"},
    )
    assert result.backup_path is None
    assert (allowed_dir / "conf.d" / "app.conf").read_text() == "new"


@pytest.mark.asyncio
async def test_deploy_test_failure_restores_backup(allowed_dir, monkeypatch):
    conf_d = allowed_dir / "conf.d"
    conf_d.mkdir()
    existing = conf_d / "app.conf"
    existing.write_text("old")
    monkeypatch.setattr(
        na.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="syntax error"),
    )
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="bad", nginx_path=str(allowed_dir)),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 400
    assert existing.read_text() == "old"


@pytest.mark.asyncio
async def test_deploy_test_failure_without_backup_removes_bad_config(
    allowed_dir, monkeypatch
):
    monkeypatch.setattr(
        na.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="syntax error"),
    )
    with pytest.raises(HTTPException):
        await na.deploy_nginx(
            NginxDeployRequest(config="bad", nginx_path=str(allowed_dir), backup=False),
            token={"sub": "sa"},
        )
    assert not (allowed_dir / "conf.d" / "app.conf").exists()


@pytest.mark.asyncio
async def test_deploy_reload_failure(allowed_dir, monkeypatch):
    calls = []

    def _run(cmd, **kwargs):
        calls.append(cmd)
        if "-s" in cmd:
            return _completed(returncode=1, stderr="reload boom")
        return _completed()

    monkeypatch.setattr(na.subprocess, "run", _run)
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="new", nginx_path=str(allowed_dir), backup=False),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 500
    assert "reload boom" in exc.value.detail
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_deploy_timeout_restores_backup(allowed_dir, monkeypatch):
    conf_d = allowed_dir / "conf.d"
    conf_d.mkdir()
    existing = conf_d / "app.conf"
    existing.write_text("old")

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="nginx", timeout=10)

    monkeypatch.setattr(na.subprocess, "run", _timeout)
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="new", nginx_path=str(allowed_dir)),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 500
    assert existing.read_text() == "old"


@pytest.mark.asyncio
async def test_deploy_generic_exception(allowed_dir, monkeypatch):
    monkeypatch.setattr(
        builtins, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
    )
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="new", nginx_path=str(allowed_dir)),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_config_success_and_guards(allowed_dir):
    conf_d = allowed_dir / "conf.d"
    conf_d.mkdir()
    target = conf_d / "app.conf"
    target.write_text("hello")

    payload = await na.get_nginx_config(config_path=str(target), token={"sub": "a"})
    assert payload["config"] == "hello"
    assert payload["size"] == 5

    with pytest.raises(HTTPException) as exc:
        await na.get_nginx_config(config_path="/tmp/other.conf", token={"sub": "a"})
    assert exc.value.status_code == 403

    txt = conf_d / "notes.txt"
    txt.write_text("x")
    with pytest.raises(HTTPException) as exc:
        await na.get_nginx_config(config_path=str(txt), token={"sub": "a"})
    assert "仅允许" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        await na.get_nginx_config(
            config_path=str(conf_d / "none.conf"), token={"sub": "a"}
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_config_read_failure(allowed_dir, monkeypatch):
    conf_d = allowed_dir / "conf.d"
    conf_d.mkdir()
    target = conf_d / "app.conf"
    target.write_text("hello")

    def _boom(*a, **k):
        raise OSError("io")

    monkeypatch.setattr(builtins, "open", _boom)
    with pytest.raises(HTTPException) as exc:
        await na.get_nginx_config(config_path=str(target), token={"sub": "a"})
    assert exc.value.status_code == 500


def test_is_allowed_path_handles_broken_paths(monkeypatch):
    assert na._is_allowed_nginx_config_path("/definitely/not/allowed/app.conf") is False

    def _boom(self):
        raise RuntimeError("loop")

    monkeypatch.setattr(na.Path, "resolve", _boom)
    assert na._is_allowed_nginx_config_path("/etc/nginx/app.conf") is False


@pytest.mark.asyncio
async def test_list_backups_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(na.Path, "is_relative_to", lambda self, other: True)
    payload = await na.list_backups(nginx_path=str(tmp_path), token={"sub": "a"})
    assert payload == {"backups": []}


@pytest.mark.asyncio
async def test_list_backups_rejects_path_outside_nginx(tmp_path):
    with pytest.raises(HTTPException) as exc:
        await na.list_backups(nginx_path=str(tmp_path), token={"sub": "a"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_backups_includes_deploy_timestamped_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(na.Path, "is_relative_to", lambda self, other: True)
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    (conf_d / "app.conf.backup.20260101_120000").write_text("b")
    (conf_d / "legacy.conf.backup").write_text("b")
    (conf_d / "app.conf").write_text("c")

    payload = await na.list_backups(nginx_path=str(tmp_path), token={"sub": "a"})
    names = {item["name"] for item in payload["backups"]}
    assert names == {"app.conf.backup.20260101_120000", "legacy.conf.backup"}
    assert [b["created_at"] for b in payload["backups"]] == sorted(
        [b["created_at"] for b in payload["backups"]], reverse=True
    )


@pytest.mark.asyncio
async def test_list_backups_failure_returns_500(tmp_path, monkeypatch):
    monkeypatch.setattr(na.Path, "is_relative_to", lambda self, other: True)
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    (conf_d / "a.backup").write_text("b")

    def _boom(path):
        raise OSError("stat")

    monkeypatch.setattr(na.os.path, "getsize", _boom)
    with pytest.raises(HTTPException) as exc:
        await na.list_backups(nginx_path=str(tmp_path), token={"sub": "a"})
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_check_temp_cleanup_failure_logs_warning(monkeypatch):
    monkeypatch.setattr(
        na.subprocess, "run", lambda *a, **k: _completed(stderr="syntax is ok")
    )
    warnings = []
    monkeypatch.setattr(
        na.logger, "warning", lambda msg, *a, **k: warnings.append(msg)
    )
    monkeypatch.setattr(
        na.Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("busy"))
    )
    with pytest.raises(HTTPException) as exc:
        await na.check_nginx(
            na.NginxCheck(config="events { worker_connections 1; }"),
            token={"sub": "a"},
        )
    assert exc.value.status_code == 500
    assert any("临时文件删除失败" in w for w in warnings)


@pytest.mark.asyncio
async def test_deploy_test_failure_cleanup_error_is_logged(allowed_dir, monkeypatch):
    monkeypatch.setattr(
        na.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="syntax error"),
    )
    errors = []
    monkeypatch.setattr(
        na.logger, "error", lambda msg, *a, **k: errors.append(msg)
    )
    monkeypatch.setattr(
        na.os, "remove", lambda path: (_ for _ in ()).throw(OSError("readonly"))
    )
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="bad", nginx_path=str(allowed_dir), backup=False),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 400
    assert any("无法清理坏配置" in e for e in errors)


@pytest.mark.asyncio
async def test_deploy_timeout_without_backup(allowed_dir, monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="nginx", timeout=10)

    monkeypatch.setattr(na.subprocess, "run", _timeout)
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="new", nginx_path=str(allowed_dir), backup=False),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_deploy_generic_exception_restores_backup(allowed_dir, monkeypatch):
    conf_d = allowed_dir / "conf.d"
    conf_d.mkdir()
    existing = conf_d / "app.conf"
    existing.write_text("old")

    real_makedirs = na.os.makedirs

    def _makedirs(path, **kwargs):
        if path.endswith("conf.d"):
            raise OSError("disk full")
        return real_makedirs(path, **kwargs)

    monkeypatch.setattr(na.os, "makedirs", _makedirs)
    with pytest.raises(HTTPException) as exc:
        await na.deploy_nginx(
            NginxDeployRequest(config="new", nginx_path=str(allowed_dir), backup=True),
            token={"sub": "sa"},
        )
    assert exc.value.status_code == 500
    assert existing.read_text() == "old"


@pytest.mark.asyncio
async def test_delete_backup_success_and_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(na.Path, "is_relative_to", lambda self, other: True)
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    target = conf_d / "app.conf.backup"
    target.write_text("b")

    payload = await na.delete_backup(
        backup_name="app.conf.backup", nginx_path=str(tmp_path), token={"sub": "sa"}
    )
    assert payload["status"] == "success"
    assert not target.exists()

    for bad in ["../x", "a/b", "a\\b", "bad name!"]:
        with pytest.raises(HTTPException) as exc:
            await na.delete_backup(
                backup_name=bad, nginx_path=str(tmp_path), token={"sub": "sa"}
            )
        assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await na.delete_backup(
            backup_name="none.backup", nginx_path=str(tmp_path), token={"sub": "sa"}
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_backup_rejects_outside_path_and_remove_failure(
    tmp_path, monkeypatch
):
    with pytest.raises(HTTPException) as exc:
        await na.delete_backup(
            backup_name="a.backup", nginx_path=str(tmp_path), token={"sub": "sa"}
        )
    assert exc.value.status_code == 403

    monkeypatch.setattr(na.Path, "is_relative_to", lambda self, other: True)
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    (conf_d / "a.backup").write_text("b")
    monkeypatch.setattr(
        na.os, "remove", lambda path: (_ for _ in ()).throw(OSError("nope"))
    )
    with pytest.raises(HTTPException) as exc:
        await na.delete_backup(
            backup_name="a.backup", nginx_path=str(tmp_path), token={"sub": "sa"}
        )
    assert exc.value.status_code == 500
