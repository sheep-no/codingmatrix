import asyncio
import logging

from app.agent.orchestrator_files import (
    _git_stash_drop,
    _git_stash_pop,
    _git_stash_push,
)
from app.agent.orchestrator_progress import PROGRESS_LABELS

logger = logging.getLogger(__name__)


class IncrementalGenerateMixin:

    async def _handle_incremental_generation(
        self,
        requirement: str,
        file_plan: list[dict],
        project_context: dict,
        total_files: int
    ):
        if not self.session_manager or not self.session_id:
            await self._generate_files_small_project(file_plan, project_context, total_files)
            return

        result = await self.session_manager.detect_incremental_changes(
            self.session_id, requirement, self.output_dir
        )
        state = result["state"]

        incremental_plan = self.session_manager.get_file_plan_for_incremental(state)
        unchanged = state.unchanged_files

        self._report_progress(
            PROGRESS_LABELS.get("incremental_analysis", "分析变更内容"),
            0, 1,
            total_files=total_files,
            files_to_regenerate=len(incremental_plan),
            files_reusable=len(unchanged),
            changed_files=state.changed_files,
            unchanged_files=unchanged
        )

        if unchanged:
            for path in unchanged:
                self.generated_files.append({
                    "path": path,
                    "description": "复用已有文件",
                    "success": True,
                    "reused": True
                })

        if not incremental_plan:
            self._report_progress(PROGRESS_LABELS.get("incremental_no_changes", "无变更"), 1, 1)
            return

        # 取消检查
        if self.cancel_event and self.cancel_event.is_set():
            logger.info("[增量生成] 检测到取消信号，跳过生成")
            return

        # 直接走 _generate_single_file，工程师自己决定用 partial_update 还是 write_file
        # 由 LLMClient 内部信号量控制并发度
        affected_files = [fi.get("path", "") for fi in incremental_plan if fi.get("path")]
        errors_baseline = len(self.errors)
        stashed = _git_stash_push(str(self.output_dir), affected_files, "agent-backup-incremental")
        if not stashed:
            # 非 git 目录等场景下 stash 是尽力而为，失败时保留原子性缺口进报告
            self.warnings.append(
                "增量备份不可用（git stash 失败），生成失败时无法回滚已修改文件"
            )

        tasks = [self._generate_single_file(fi, project_context, total_files) for fi in incremental_plan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        has_failure = False
        cancelled = False
        applied_results = []
        for i, result in enumerate(results):
            file_path = incremental_plan[i].get("path", "unknown") if i < len(incremental_plan) else "unknown"
            if isinstance(result, asyncio.CancelledError):
                # 取消从 LLM 流内以 CancelledError 冒出（BaseException），须显式分诊，
                # 否则会被 truthy 分支误记为成功项
                self.errors.append(f"文件生成被取消: {file_path}")
                cancelled = True
                has_failure = True
            elif isinstance(result, Exception):
                self.errors.append(f"文件生成异常：{result!s}")
                has_failure = True
            elif result is None:
                self.errors.append(f"文件生成失败: {file_path}（返回空内容）")
                has_failure = True
            elif result:
                self.generated_files.append(result)
                applied_results.append(result)

        # 增量生成失败时回滚
        if has_failure:
            if stashed:
                logger.warning("[增量生成] 存在失败文件，回滚到备份版本")
                _git_stash_pop(str(self.output_dir))
                # 回滚把受影响文件（含已成功修改的）还原到备份版本，
                # 同步移除本次已记录的成功项，避免报告与磁盘状态不一致；
                # 按 path 匹配（本轮成功项均来自 incremental_plan，与复用项不相交）
                applied_paths = {r.get("path") for r in applied_results}
                self.generated_files = [
                    f for f in self.generated_files if f.get("path") not in applied_paths
                ]
            detail = "; ".join(self.errors[errors_baseline:])
            if cancelled:
                raise RuntimeError("incremental file generation cancelled: " + detail)
            raise RuntimeError("incremental file generation failed: " + detail)
        if stashed:
            _git_stash_drop(str(self.output_dir))
