"""
GitOperations - Git 操作模块

v4.8.0 新增：
- 分支管理（创建/切换/合并）
- 快照标签（创建/列出）
- 版本回滚（revert/reset）
- 结构化提交消息
- asyncio.to_thread 避免阻塞事件循环
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SnapshotInfo:
    """快照信息"""
    tag: str
    commit_hash: str
    message: str
    timestamp: str
    files_changed: List[str] = field(default_factory=list)


class GitOperations:
    """
    Git 操作模块，支持分支管理和版本回滚

    所有 subprocess 调用通过 asyncio.to_thread 包装，避免阻塞事件循环。
    """

    async def init_repo(self, project_path: Path) -> bool:
        """初始化 git 仓库"""
        git_dir = project_path / ".git"
        if git_dir.exists():
            return True

        def _init():
            subprocess.run(
                ["git", "init"],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            gitignore = project_path / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text(
                    "__pycache__/\n*.pyc\nnode_modules/\n.env\n.venv/\n"
                )
            return True

        try:
            return await asyncio.to_thread(_init)
        except Exception as e:
            logger.error(f"Git init 失败: {e}")
            return False

    async def create_branch(
        self,
        project_path: Path,
        name: str,
        base: str = "main",
    ) -> Optional[str]:
        """创建新分支"""
        def _create():
            result = subprocess.run(
                ["git", "checkout", base],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                subprocess.run(
                    ["git", "checkout", "-b", base],
                    cwd=str(project_path),
                    capture_output=True,
                    timeout=30,
                )

            result = subprocess.run(
                ["git", "checkout", "-b", name],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"创建分支失败: {name}, stderr: {result.stderr.decode()}")
                return None
            return name

        try:
            return await asyncio.to_thread(_create)
        except Exception as e:
            logger.error(f"创建分支异常: {e}")
            return None

    async def commit_snapshot(
        self,
        project_path: Path,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """提交快照（带结构化消息）"""
        def _commit():
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(project_path),
                capture_output=True,
                timeout=60,
            )

            structured_message = message
            if metadata:
                body_lines = []
                if "files" in metadata:
                    body_lines.append(f"Files: {', '.join(metadata['files'])}")
                if "model" in metadata:
                    body_lines.append(f"Model: {metadata['model']}")
                if "duration" in metadata:
                    body_lines.append(f"Duration: {metadata['duration']}s")
                if body_lines:
                    structured_message = f"{message}\n\n{'. '.join(body_lines)}"

            result = subprocess.run(
                ["git", "commit", "-m", structured_message, "--allow-empty"],
                cwd=str(project_path),
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.debug(f"Commit 无变更或失败: {result.stderr.decode()}")
                return None

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(project_path),
                capture_output=True,
                timeout=10,
            )
            return result.stdout.decode().strip()

        try:
            return await asyncio.to_thread(_commit)
        except Exception as e:
            logger.error(f"Commit 快照异常: {e}")
            return None

    async def create_tag(
        self,
        project_path: Path,
        tag_name: str,
        message: str = "",
    ) -> Optional[str]:
        """创建标注标签"""
        def _tag():
            cmd = ["git", "tag", "-a", tag_name, "-m", message or tag_name]
            result = subprocess.run(
                cmd,
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"创建标签失败: {result.stderr.decode()}")
                return None
            return tag_name

        try:
            return await asyncio.to_thread(_tag)
        except Exception as e:
            logger.error(f"创建标签异常: {e}")
            return None

    async def merge_branch(
        self,
        project_path: Path,
        branch: str,
        target: str = "main",
    ) -> bool:
        """合并分支到目标"""
        def _merge():
            subprocess.run(
                ["git", "checkout", target],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )

            result = subprocess.run(
                ["git", "merge", branch, "--no-edit"],
                cwd=str(project_path),
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                subprocess.run(
                    ["git", "merge", "--abort"],
                    cwd=str(project_path),
                    capture_output=True,
                    timeout=30,
                )
                logger.error(f"合并失败，已中止: {branch} -> {target}")
                return False
            return True

        try:
            return await asyncio.to_thread(_merge)
        except Exception as e:
            logger.error(f"合并分支异常: {e}")
            return False

    async def delete_branch(self, project_path: Path, branch: str) -> bool:
        """删除分支"""
        def _delete():
            result = subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0

        try:
            return await asyncio.to_thread(_delete)
        except Exception as e:
            logger.error(f"删除分支异常: {e}")
            return False

    async def revert_to_commit(self, project_path: Path, commit_hash: str) -> bool:
        """回滚到指定 commit"""
        def _revert():
            result = subprocess.run(
                ["git", "reset", "--hard", commit_hash],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"回滚失败: {result.stderr.decode()}")
                return False
            return True

        try:
            return await asyncio.to_thread(_revert)
        except Exception as e:
            logger.error(f"回滚异常: {e}")
            return False

    async def list_snapshots(self, project_path: Path) -> List[SnapshotInfo]:
        """列出所有标签快照"""
        def _list():
            result = subprocess.run(
                ["git", "tag", "-l"],
                cwd=str(project_path),
                capture_output=True,
                timeout=30,
            )
            tags = result.stdout.decode().strip().split("\n")
            tags = [t.strip() for t in tags if t.strip()]

            snapshots = []
            for tag in tags:
                log_result = subprocess.run(
                    ["git", "log", "-1", "--format=%H|%s|%ci", tag],
                    cwd=str(project_path),
                    capture_output=True,
                    timeout=10,
                )
                parts = log_result.stdout.decode().strip().split("|")
                if len(parts) >= 3:
                    snapshots.append(SnapshotInfo(
                        tag=tag,
                        commit_hash=parts[0],
                        message=parts[1],
                        timestamp=parts[2],
                    ))
            return snapshots

        try:
            return await asyncio.to_thread(_list)
        except Exception as e:
            logger.error(f"列出快照异常: {e}")
            return []

    async def diff_between_commits(
        self,
        project_path: Path,
        from_commit: str,
        to_commit: str,
    ) -> str:
        """查看两个版本间的差异"""
        def _diff():
            result = subprocess.run(
                ["git", "diff", from_commit, to_commit],
                cwd=str(project_path),
                capture_output=True,
                timeout=60,
            )
            return result.stdout.decode()

        try:
            return await asyncio.to_thread(_diff)
        except Exception as e:
            logger.error(f"查看差异异常: {e}")
            return ""

    async def get_current_branch(self, project_path: Path) -> str:
        """获取当前分支名"""
        def _branch():
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(project_path),
                capture_output=True,
                timeout=10,
            )
            return result.stdout.decode().strip() or "main"

        try:
            return await asyncio.to_thread(_branch)
        except Exception:
            return "main"

    async def get_head_commit(self, project_path: Path) -> str:
        """获取当前 HEAD commit hash"""
        def _head():
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(project_path),
                capture_output=True,
                timeout=10,
            )
            return result.stdout.decode().strip()

        try:
            return await asyncio.to_thread(_head)
        except Exception:
            return ""