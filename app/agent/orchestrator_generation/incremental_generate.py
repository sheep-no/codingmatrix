import asyncio
import logging
from typing import Dict, List

from app.agent.orchestrator_progress import PROGRESS_LABELS

logger = logging.getLogger(__name__)


class IncrementalGenerateMixin:

    async def _handle_incremental_generation(
        self,
        requirement: str,
        file_plan: List[Dict],
        project_context: Dict,
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

        # 直接走 _generate_single_file，工程师自己决定用 partial_update 还是 write_file
        # 由 LLMClient 内部信号量控制并发度
        tasks = [self._generate_single_file(fi, project_context, total_files) for fi in incremental_plan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.errors.append(f"文件生成异常：{str(result)}")
            elif result is None:
                file_path = incremental_plan[i].get("path", "unknown") if i < len(incremental_plan) else "unknown"
                self.errors.append(f"文件生成失败: {file_path}（返回空内容）")
            elif result:
                self.generated_files.append(result)
