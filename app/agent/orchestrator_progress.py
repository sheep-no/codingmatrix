import os
import time
import json
import asyncio
import logging
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass

MAX_CONCURRENT_LLM_CALLS = int(os.environ.get("CM_MAX_CONCURRENT_LLM_CALLS", "4"))
MAX_CONTENT_FOR_CONTEXT = int(os.environ.get("CM_MAX_CONTENT_FOR_CONTEXT", "3000"))

logger = logging.getLogger(__name__)

PROGRESS_LABELS = {
    "analyzing_complexity": "分析项目复杂度",
    "assigning_models": "分配 AI 模型",
    "initializing_roles": "初始化专家角色",
    "cost_estimation": "预估生成成本",
    "dependency_graph": "构建文件依赖关系",
    "generating_file": "正在生成文件",
    "file_generated": "文件生成完成",
    "react_fallback": "启用增强生成模式",
    "pause_for_approval": "等待人工确认",
    "file_rejected": "文件已被拒绝",
    "validating_file": "验证文件内容",
    "reviewing_file": "审查代码质量",
    "api_contract_check": "检查 API 一致性",
    "final_validation": "最终项目验证",
    "dependency_graph_built": "依赖关系构建完成",
    "generating_layer": "正在生成分层文件",
    "layer_completed": "分层生成完成",
    "test_execution": "运行自动化测试",
    "test_passed": "测试全部通过",
    "test_failed": "测试存在失败",
    "auto_repair": "自动修复测试问题",
    "repair_completed": "修复完成",
    "saving_memory": "保存项目经验",
    "generation_complete": "项目生成完成",
    "incremental_analysis": "分析变更内容",
    "incremental_no_changes": "无变更，跳过生成",
    "running_tests": "运行自动化测试",
    "tests_passed": "测试全部通过",
    "tests_failed_recovering": "测试失败，正在自动修复",
    "recovery_success": "自动修复成功",
    "recovery_failed": "自动修复失败",
    "requirement_association": "需求联想增强",
}

@dataclass
class GenerationProgress:
    current_step: str
    total_steps: int
    completed_files: int
    total_files: int
    current_model: str
    errors: List[str]
    warnings: List[str]


class ProgressMixin:

    def _report_progress(self, step: str, current: int, total: int, callback: Optional[Callable] = None, **kwargs):
        percentage = round((current / total * 100) if total > 0 else 0, 1)

        elapsed = 0
        eta_seconds = 0
        if self._start_time:
            elapsed = time.time() - self._start_time
            if current > 0 and current < total:
                rate = current / elapsed
                remaining = total - current
                eta_seconds = remaining / rate if rate > 0 else 0

        progress = {
            "type": "progress",
            "step": step,
            "phase": self._current_phase,
            "current": current,
            "total": total,
            "percentage": percentage,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(eta_seconds, 1),
            **kwargs
        }
        cb = callback or self.callback
        if cb:
            try:
                result = cb(json.dumps(progress, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                logger.error(f"进度回调失败: {e}")

    def build_progress_event(self, step: str, current: int, total: int, **kwargs) -> Dict:
        percentage = round((current / total * 100) if total > 0 else 0, 1)

        elapsed = 0
        eta_seconds = 0
        if self._start_time:
            elapsed = time.time() - self._start_time
            if current > 0 and current < total:
                rate = current / elapsed
                remaining = total - current
                eta_seconds = remaining / rate if rate > 0 else 0

        return {
            "type": "progress",
            "step": step,
            "phase": self._current_phase,
            "current": current,
            "total": total,
            "percentage": percentage,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(eta_seconds, 1),
            **kwargs
        }

    def _report_thinking(self, agent: str, message: str, **kwargs):
        event = {
            "type": "thinking",
            "agent": agent,
            "message": message,
            "timestamp": time.time(),
            **kwargs
        }
        if self.callback:
            try:
                self.callback(event)
            except Exception as e:
                logger.error(f"思考事件推送失败: {e}")

    def _update_phase(self, phase: str):
        self._current_phase = phase