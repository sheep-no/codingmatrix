"""生产编排一致性回归：数据库单一来源、必需密钥显式、写入挂载点可写。

这三个问题在本地开发不会暴露，但会让生产部署静默降级或直接不可用：

- api/celery 未声明 DATABASE_URL，各自落到容器内 `/app/app.db`，而 scheduler
  指向 `/app/data/app.db`：三个进程三个库，调度任务看不到 API 数据。
- 应用以非 root 的 appuser 运行，但镜像未预建 compose 里的写入挂载点，Docker
  会创建 root 属主目录，导致上传/生成物写入失败。
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
DOCKERFILE_PATH = ROOT / "Dockerfile"
APP_SERVICES = ("api", "celery", "scheduler")
SHARED_DB_PATH = "/app/data/app.db"


def _load_services() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))["services"]


def _env_map(service: dict) -> dict:
    env = {}
    for item in service.get("environment") or []:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            env[key] = value
    return env


def test_app_services_share_single_database():
    services = _load_services()
    urls = {name: _env_map(services[name]).get("DATABASE_URL") for name in APP_SERVICES}

    assert all(urls.values()), f"以下服务未声明 DATABASE_URL: {urls}"
    assert len(set(urls.values())) == 1, f"数据库来源不一致: {urls}"

    raw = next(iter(urls.values()))
    # 缺省回退必须是共享卷上的绝对路径，而非随 CWD 漂移的 ./data
    assert f"sqlite+aiosqlite:///{SHARED_DB_PATH}" in raw, raw
    assert "/./" not in raw, raw


def test_app_services_require_secret_key_explicitly():
    services = _load_services()
    for name in APP_SERVICES:
        raw = _env_map(services[name]).get("SECRET_KEY", "")
        # compose 的 :? 语法会在缺失时直接报错，避免启动到 Python 层才抛校验失败
        assert ":?" in raw, f"{name} 未显式要求 SECRET_KEY: {raw!r}"


def test_app_write_mounts_are_created_before_chown():
    services = _load_services()
    lines = DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines()
    chown_index = next(
        index
        for index, line in enumerate(lines)
        if "chown -R appuser:appuser /app" in line
    )
    pre_chown = "\n".join(lines[:chown_index])

    mount_paths = set()
    for name in APP_SERVICES:
        for volume in services[name].get("volumes") or []:
            if ":" in volume:
                mount_paths.add(volume.split(":", 1)[1])

    missing = sorted(path for path in mount_paths if path not in pre_chown)
    assert not missing, f"以下挂载点在 chown 前未创建，appuser 将无法写入: {missing}"
