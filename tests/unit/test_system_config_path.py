"""系统配置路径必须锚定仓库根，而非进程 CWD。

原实现用 `Path("./configs/system_config.json")`，在类定义时按 CWD 解析。以不同
工作目录启动进程（例如从 src/ 或容器外的任意路径）时会指向不存在的配置，触发
默认配置回退并新建文件，形成配置漂移。这里锁定其锚定仓库根。
"""
from pathlib import Path

from app.core.config import BASE_DIR
from app.utils.system_config import SystemConfigManager


def test_config_file_is_absolute():
    assert SystemConfigManager._config_file.is_absolute()


def test_config_file_is_anchored_to_repo_root():
    assert SystemConfigManager._config_file == BASE_DIR / "configs" / "system_config.json"


def test_config_file_is_not_cwd_relative():
    # 相对路径会随 CWD 变化；绝对路径且以仓库根开头才稳定
    assert str(SystemConfigManager._config_file).startswith(str(BASE_DIR))
    assert Path(str(SystemConfigManager._config_file)) == SystemConfigManager._config_file
