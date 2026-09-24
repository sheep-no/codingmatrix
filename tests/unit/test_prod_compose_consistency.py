"""生产编排一致性回归：数据库单一来源、必需密钥显式、写入挂载点可写。

这三个问题在本地开发不会暴露，但会让生产部署静默降级或直接不可用：

- api/celery 未声明 DATABASE_URL，各自落到容器内 `/app/app.db`，而 scheduler
  指向 `/app/data/app.db`：三个进程三个库，调度任务看不到 API 数据。
- 应用以非 root 的 appuser 运行，但镜像未预建 compose 里的写入挂载点，Docker
  会创建 root 属主目录，导致上传/生成物写入失败。

`docker-compose.yml`（单机生产模式）有同类问题：`ENV=production` 却不提供
`SECRET_KEY`，config 校验会在导入期直接抛错；celery 未挂载数据卷，与 API
落在两个库上，且 PPT/图片生成物无法被 API 读取。
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
LOCAL_COMPOSE_PATH = ROOT / "docker-compose.yml"
DOCKERFILE_PATH = ROOT / "Dockerfile"
ALEMBIC_INI_PATH = ROOT / "configs" / "alembic.ini"
ALEMBIC_ENV_PATH = ROOT / "migrations" / "env.py"
APP_SERVICES = ("api", "celery", "scheduler")
LOCAL_APP_SERVICES = ("api", "celery")
SHARED_DB_PATH = "/app/data/app.db"
SHARED_ASSET_PATHS = ("/app/uploads", "/app/pptx_output", "/app/generated_images", "/app/projects")


def _load_services(path: Path = COMPOSE_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]


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

    # 只校验目录型挂载点：文件挂载依赖父目录，由 COPY 或既有 mkdir 覆盖
    mount_paths = set()
    for name in APP_SERVICES:
        for target in _mount_targets(services[name]):
            if not Path(target).suffix:
                mount_paths.add(target)

    missing = sorted(path for path in mount_paths if path not in pre_chown)
    assert not missing, f"以下挂载点在 chown 前未创建，appuser 将无法写入: {missing}"


def test_local_compose_app_services_share_single_database():
    services = _load_services(LOCAL_COMPOSE_PATH)
    urls = {name: _env_map(services[name]).get("DATABASE_URL") for name in LOCAL_APP_SERVICES}

    assert all(urls.values()), f"以下服务未声明 DATABASE_URL: {urls}"
    assert len(set(urls.values())) == 1, f"数据库来源不一致: {urls}"

    raw = next(iter(urls.values()))
    assert f"sqlite+aiosqlite:///{SHARED_DB_PATH}" in raw, raw
    assert "/./" not in raw, raw


def test_local_compose_app_services_require_secret_key_explicitly():
    services = _load_services(LOCAL_COMPOSE_PATH)
    for name in LOCAL_APP_SERVICES:
        raw = _env_map(services[name]).get("SECRET_KEY", "")
        assert ":?" in raw, f"{name} 未显式要求 SECRET_KEY: {raw!r}"


def test_local_compose_app_services_share_writable_mounts():
    services = _load_services(LOCAL_COMPOSE_PATH)

    def mount_paths(name: str) -> set:
        return {
            volume.split(":", 1)[1]
            for volume in services[name].get("volumes") or []
            if ":" in volume
        }

    api_mounts = mount_paths("api")
    celery_mounts = mount_paths("celery")

    # celery 执行 PPT/图片生成任务，API 负责下载与预览，两者必须看到同一份产物
    for path in ("/app/data",) + SHARED_ASSET_PATHS:
        assert path in api_mounts, f"api 缺少共享挂载点 {path}"
        assert path in celery_mounts, f"celery 缺少共享挂载点 {path}"


def _mount_targets(service: dict) -> set:
    targets = set()
    for volume in service.get("volumes") or []:
        if ":" in volume:
            targets.add(volume.split(":")[1])
    return targets


REQUIRED_CONFIG_TARGETS = (
    "/app/data/unified_model_config.yaml",
    "/app/data/agent_model_config.yaml",
    "/app/configs/system_config.json",
)
RSA_KEY_TARGET = "/app/keys"


def test_prod_app_services_mount_model_and_system_configs():
    """api-data 是空卷，会遮蔽镜像内 data/；不显式挂载则模型配置静默回退默认值。"""
    services = _load_services()
    for name in APP_SERVICES:
        targets = _mount_targets(services[name])
        for target in REQUIRED_CONFIG_TARGETS:
            assert target in targets, f"{name} 未挂载配置 {target}"


def test_prod_app_services_share_rsa_key_volume():
    """各容器各自生成 RSA 密钥会导致跨进程密文无法解密，必须共享同一密钥卷。"""
    services = _load_services()
    key_dirs = {name: _env_map(services[name]).get("RSA_KEY_DIR") for name in APP_SERVICES}

    assert set(key_dirs.values()) == {RSA_KEY_TARGET}, f"RSA_KEY_DIR 不一致: {key_dirs}"
    for name in APP_SERVICES:
        assert RSA_KEY_TARGET in _mount_targets(services[name]), f"{name} 未挂载密钥卷"


def test_local_compose_shares_rsa_key_volume():
    services = _load_services(LOCAL_COMPOSE_PATH)
    key_dirs = {name: _env_map(services[name]).get("RSA_KEY_DIR") for name in LOCAL_APP_SERVICES}

    assert set(key_dirs.values()) == {RSA_KEY_TARGET}, f"RSA_KEY_DIR 不一致: {key_dirs}"
    for name in LOCAL_APP_SERVICES:
        assert RSA_KEY_TARGET in _mount_targets(services[name]), f"{name} 未挂载密钥卷"


def test_local_compose_mounts_system_config():
    services = _load_services(LOCAL_COMPOSE_PATH)
    for name in LOCAL_APP_SERVICES:
        assert "/app/configs/system_config.json" in _mount_targets(services[name]), name


def test_dockerfile_ships_system_config_default():
    """镜像需自带系统配置默认值，供未挂载该文件的运行方式兜底。"""
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "COPY configs/system_config.json ./configs/" in content


def test_production_startup_rejects_missing_config_files(tmp_path, monkeypatch):
    """生产环境缺配置时必须启动失败，而不是静默回退到硬编码默认值。"""
    from app import main as main_mod

    monkeypatch.setattr(main_mod.settings, "ENV", "production")
    monkeypatch.setattr(main_mod, "BASE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="缺少必需配置文件"):
        main_mod._validate_production_config_files()


def test_production_startup_accepts_present_config_files(tmp_path, monkeypatch):
    from app import main as main_mod

    for relative_path in main_mod._REQUIRED_PRODUCTION_CONFIGS:
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(main_mod.settings, "ENV", "production")
    monkeypatch.setattr(main_mod, "BASE_DIR", tmp_path)
    main_mod._validate_production_config_files()


def test_non_production_startup_skips_config_file_check(tmp_path, monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod.settings, "ENV", "development")
    monkeypatch.setattr(main_mod, "BASE_DIR", tmp_path)
    main_mod._validate_production_config_files()


def test_dockerfile_places_alembic_ini_under_configs():
    """alembic.ini 的 script_location 与 prepend_sys_path 均以 %(here)s 相对定位。

    镜像内 `/app` 即仓库根，ini 必须落在 `/app/configs`：此时 `%(here)s/../migrations`
    解析为 `/app/migrations`、`%(here)s/..` 解析为 `/app`，与 `COPY migrations/
    ./migrations/` 一致。若按旧实现复制到 `/app/alembic.ini`，二者会解析到
    `/migrations` 与 `/`，容器内迁移命令不可用。
    """
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "COPY configs/alembic.ini ./configs/" in content
    assert "COPY migrations/ ./migrations/" in content

    ini = ALEMBIC_INI_PATH.read_text(encoding="utf-8")
    assert "script_location = %(here)s/../migrations" in ini
    assert "prepend_sys_path = %(here)s/.." in ini


def test_alembic_env_reads_database_url_from_settings():
    """env.py 硬编码 BASE_DIR/app.db 会让容器内 alembic 迁移到与 API 不同的库。"""
    content = ALEMBIC_ENV_PATH.read_text(encoding="utf-8")

    assert "settings.DATABASE_URL" in content
    assert 'Path(BASE_DIR) / "app.db"' not in content
