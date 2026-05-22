"""
SnapshotManager - 快照管理器

v4.8.0 新增：
- 项目快照保存（分支 + 提交 + 标签）
- 版本回滚
- 会话结束自动合并
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.agent.git_operations import GitOperations, SnapshotInfo
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """回滚结果"""
    success: bool
    previous_tag: str
    current_tag: str
    files_restored: List[str] = field(default_factory=list)


@dataclass
class FinalizeResult:
    """会话结束结果"""
    merged: bool
    final_tag: str = ""
    branch_deleted: bool = False
    rollback_offered: bool = False


class SnapshotManager:
    """
    快照管理器

    管理 Agent 项目的快照保存、回滚和分支合并。
    """

    def __init__(self, git_ops: GitOperations):
        self.git_ops = git_ops
        self.snapshots: Dict[str, SnapshotInfo] = {}

    async def save_snapshot(
        self,
        project_path: Path,
        session_id: str,
        description: str,
        files_changed: List[str],
        model_used: str = "",
        duration: float = 0.0,
        branch_name: Optional[str] = None,
    ) -> Optional[SnapshotInfo]:
        """
        保存项目快照

        1. 确保仓库已初始化
        2. 如果需要，创建 feature 分支
        3. 提交变更（带结构化消息）
        4. 创建里程碑标签

        Args:
            project_path: 项目路径
            session_id: 会话 ID
            description: 变更描述
            files_changed: 变更文件列表
            model_used: 使用的模型名称
            duration: 生成耗时
            branch_name: 分支名称（可选）

        Returns:
            SnapshotInfo 或 None（失败时）
        """
        await self.git_ops.init_repo(project_path)

        if branch_name:
            current_branch = await self.git_ops.get_current_branch(project_path)
            if current_branch != branch_name:
                created = await self.git_ops.create_branch(project_path, branch_name)
                if not created:
                    logger.warning(f"分支 {branch_name} 已存在或创建失败")

        metadata = {
            "files": files_changed[:10],
            "model": model_used,
            "duration": round(duration, 2),
        }

        commit_hash = await self.git_ops.commit_snapshot(
            project_path, description, metadata
        )
        if not commit_hash:
            logger.debug("无变更需要提交")
            return None

        tag_name = f"agent-{session_id}-{datetime.now().strftime('%H%M%S')}"
        tag_result = await self.git_ops.create_tag(
            project_path, tag_name, description
        )

        snapshot = SnapshotInfo(
            tag=tag_name,
            commit_hash=commit_hash,
            message=description,
            timestamp=datetime.now().isoformat(),
            files_changed=files_changed,
        )
        self.snapshots[tag_name] = snapshot
        return snapshot

    async def rollback_to_snapshot(
        self,
        project_path: Path,
        snapshot_tag: str,
        delete_branch: bool = True,
    ) -> Optional[RollbackResult]:
        """
        回滚到指定快照

        Args:
            project_path: 项目路径
            snapshot_tag: 目标快照标签
            delete_branch: 是否删除 feature 分支

        Returns:
            RollbackResult 或 None（快照不存在时）
        """
        snapshot = self.snapshots.get(snapshot_tag)
        if not snapshot:
            snapshots = await self.git_ops.list_snapshots(project_path)
            for s in snapshots:
                if s.tag == snapshot_tag:
                    snapshot = s
                    break

        if not snapshot:
            logger.error(f"快照不存在: {snapshot_tag}")
            return None

        success = await self.git_ops.revert_to_commit(
            project_path, snapshot.commit_hash
        )

        current_branch = await self.git_ops.get_current_branch(project_path)

        if delete_branch and current_branch != "main":
            await self.git_ops.delete_branch(project_path, current_branch)

        return RollbackResult(
            success=success,
            previous_tag=snapshot_tag,
            current_tag="main",
            files_restored=snapshot.files_changed,
        )

    async def finalize_session(
        self,
        project_path: Path,
        session_id: str,
        success: bool,
        branch_name: Optional[str] = None,
    ) -> FinalizeResult:
        """
        结束会话

        - 成功: 合并 feature 分支到 main，创建最终标签
        - 失败: 提议回滚到上一个稳定快照

        Args:
            project_path: 项目路径
            session_id: 会话 ID
            success: 生成是否成功
            branch_name: feature 分支名称

        Returns:
            FinalizeResult
        """
        if success and branch_name:
            merged = await self.git_ops.merge_branch(
                project_path, branch_name, "main"
            )
            if merged:
                final_tag = f"agent-{session_id}-final"
                await self.git_ops.create_tag(
                    project_path, final_tag,
                    f"Session {session_id} completed successfully"
                )
                await self.git_ops.delete_branch(project_path, branch_name)
                return FinalizeResult(
                    merged=True,
                    final_tag=final_tag,
                    branch_deleted=True,
                )
            else:
                logger.warning("合并失败，保留 feature 分支")
                return FinalizeResult(
                    merged=False,
                    rollback_offered=True,
                )

        if not success:
            return FinalizeResult(
                merged=False,
                rollback_offered=True,
            )

        return FinalizeResult(merged=True)