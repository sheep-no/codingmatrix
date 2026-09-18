"""启动脚本回归测试。

覆盖 docs/evolution/modules/startup_scripts.md 中核实的 SS1：
start.sh 曾把脚本自身目录（scripts/）当作项目根，导致前端构建、app.main 导入、
nginx 配置与 logs/data 目录全部落在错误位置。
"""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
START_SH = REPO_ROOT / "scripts" / "start.sh"


def test_project_dir_resolves_to_repo_root(tmp_path):
    """从任意 CWD 解析 PROJECT_DIR，都应指向仓库根"""
    content = START_SH.read_text(encoding="utf-8")
    assignment = next(
        line for line in content.splitlines() if line.startswith("PROJECT_DIR=")
    )
    expr = assignment.split("=", 1)[1].replace("${BASH_SOURCE[0]}", str(START_SH))

    result = subprocess.run(
        ["bash", "-c", f'PROJECT_DIR={expr}; echo "$PROJECT_DIR"'],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(REPO_ROOT)


def test_project_dir_anchored_resources_exist():
    """脚本以 PROJECT_DIR 定位的资源应真实存在于仓库根"""
    for relative in ("app/main.py", "src/package.json", "configs/nginx.conf"):
        assert (REPO_ROOT / relative).exists(), relative
