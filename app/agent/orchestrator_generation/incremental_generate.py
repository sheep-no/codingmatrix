import asyncio
import logging
from typing import Dict, List, Any
from pathlib import Path

from app.agent.orchestrator_progress import PROGRESS_LABELS, MAX_CONCURRENT_LLM_CALLS

logger = logging.getLogger(__name__)


class IncrementalGenerateMixin:

    async def _apply_patches_incremental(
        self,
        requirement: str,
        incremental_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        """使用 Patch 模式应用增量变更"""
        if not self.code_patcher:
            logger.warning("code_patcher 未初始化，回退到完整生成模式")
            await self._generate_files_small_project(incremental_plan, project_context, total_files)
            return
        
        self._report_progress(
            PROGRESS_LABELS.get("applying_patches", "应用代码补丁"),
            0, len(incremental_plan),
            patch_mode=True
        )
        
        for i, file_info in enumerate(incremental_plan):
            file_path = self.output_dir / file_info["path"]
            
            try:
                if file_path.exists():
                    # 现有文件：使用 Patch 模式
                    original_content = file_path.read_text(encoding='utf-8')
                    
                    # 调用 CodePatcher 生成并应用 patch
                    from app.agent.code_patcher import PatchResult
                    patch_result: PatchResult = await self.code_patcher.generate_patch_from_requirement(
                        file_path=str(file_info["path"]),
                        original_content=original_content,
                        change_request=requirement,
                        project_context=project_context
                    )
                    
                    if patch_result:
                        apply_result = await self.code_patcher.apply_patch(
                            str(file_info["path"]),
                            original_content,
                            patch_result
                        )
                        
                        if apply_result.success:
                            file_path.write_text(apply_result.patched_content, encoding='utf-8')
                            self.generated_files.append({
                                "path": file_info["path"],
                                "description": "通过 Patch 更新",
                                "success": True,
                                "patch_mode": True
                            })
                            logger.info(f"Patch 应用成功：{file_info['path']}")
                        else:
                            logger.warning(f"Patch 应用失败，回退到完整生成：{file_info['path']}")
                            result = await self._generate_single_file(file_info, project_context, total_files)
                            if result:
                                self.generated_files.append(result)
                    else:
                        logger.warning(f"Patch 生成失败，回退到完整生成：{file_info['path']}")
                        result = await self._generate_single_file(file_info, project_context, total_files)
                        if result:
                            self.generated_files.append(result)
                                
                else:
                    # 新文件：直接生成
                    result = await self._generate_single_file(file_info, project_context, total_files)
                    if result:
                        self.generated_files.append(result)
                
                # 更新进度
                self._report_progress(
                    PROGRESS_LABELS.get("applying_patches", "应用代码补丁"),
                    i + 1, len(incremental_plan),
                    current_file=file_info["path"]
                )
                
            except Exception as e:
                logger.error(f"Patch 模式处理失败 {file_info['path']}: {e}", exc_info=True)
                self.errors.append(f"文件处理异常：{file_info['path']} - {str(e)}")
                # 回退到完整生成
                try:
                    result = await self._generate_single_file(file_info, project_context, total_files)
                    if result:
                        self.generated_files.append(result)
                except Exception as fallback_error:
                    self.errors.append(f"回退生成也失败：{file_info['path']} - {str(fallback_error)}")
        
        self._report_progress(
            PROGRESS_LABELS.get("patch_complete", "补丁应用完成"),
            len(incremental_plan), len(incremental_plan)
        )

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
            PROGRESS_LABELS["incremental_analysis"] if "incremental_analysis" in PROGRESS_LABELS else "分析变更内容",
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
            self._report_progress(PROGRESS_LABELS["incremental_no_changes"], 1, 1)
            return

        use_patch_mode = self._should_use_patch_mode(incremental_plan, requirement)

        if use_patch_mode and self.code_patcher:
            await self._apply_patches_incremental(
                requirement, incremental_plan, project_context, total_files
            )
        else:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

            async def generate_with_semaphore(file_info: Dict) -> Dict:
                async with semaphore:
                    return await self._generate_single_file(file_info, project_context, total_files)

            tasks = [generate_with_semaphore(fi) for fi in incremental_plan]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self.errors.append(f"文件生成异常：{str(result)}")
                elif result:
                    self.generated_files.append(result)