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
from typing import List, Optional, Dict

from app.agent.git_operations import GitOperations, SnapshotInfo, MAINLINE_BRANCHES
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """回滚结果"""
    success: bool
    previous_tag: str
    current_tag: str
    files_restored: List[str] = field(default_factory=list)
    branch_deleted: bool = False


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

        # 秒级时间戳 + commit 短哈希：同一会话同一秒内多次保存不再产生重名标签
        tag_name = (
            f"agent-{session_id}-{datetime.now().strftime('%H%M%S')}-{commit_hash[:8]}"
        )
        created_tag = await self.git_ops.create_tag(
            project_path, tag_name, description
        )
        if not created_tag:
            # 标签创建失败时不能谎报快照已保存（否则 list/rollback 都查不到该 tag）
            logger.error(f"创建快照标签失败: {tag_name}")
            return None

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

        branch_before = await self.git_ops.get_current_branch(project_path)
        pre_head = await self.git_ops.get_head_commit(project_path)

        # git 禁止删除当前检出的分支。若当前在 feature 分支上，必须在 reset
        # 之前先切到主线分支，reset 才会落在主线上（否则 reset 移动的是 feature
        # 分支指针，随后删分支必然失败且回滚内容会随分支一起被丢弃）。
        is_feature_branch = bool(branch_before) and branch_before not in MAINLINE_BRANCHES
        if delete_branch and is_feature_branch:
            switched = await self.git_ops.checkout_mainline(project_path)
            if not switched:
                logger.warning(f"无法切换到主线分支，保留 feature 分支: {branch_before}")
                is_feature_branch = False

        success = await self.git_ops.revert_to_commit(
            project_path, snapshot.commit_hash
        )

        files_restored: List[str] = []
        if success and pre_head:
            files_restored = await self.git_ops.diff_files_between_commits(
                project_path, pre_head, snapshot.commit_hash
            )

        branch_deleted = False
        if success and is_feature_branch:
            branch_deleted = await self.git_ops.delete_branch(project_path, branch_before)
            if not branch_deleted:
                logger.warning(f"feature 分支删除失败，仍残留: {branch_before}")

        # 如实返回回滚后的实际分支，不再恒报 "main"
        current_tag = await self.git_ops.get_current_branch(project_path)

        return RollbackResult(
            success=success,
            previous_tag=snapshot_tag,
            current_tag=current_tag,
            files_restored=files_restored,
            branch_deleted=branch_deleted,
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
