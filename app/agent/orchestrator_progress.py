import os
import time
import json
import asyncio
import logging
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass, field

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
    "cross_file_validation": "跨文件一致性检查",
    "cross_file_fix": "自动修复一致性问题",
    "architecture_review": "架构设计审查",
    "cost_tracking": "成本追踪",
    "token_usage": "Token 用量统计",
    "react_tool_call": "搜索项目文件",
    "react_tool_result": "获取搜索结果",
    "react_generating": "基于上下文生成代码",
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


@dataclass
class CostTracker:
    """成本追踪器"""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost_usd: float = 0.0
    model_costs: Dict[str, float] = field(default_factory=dict)
    model_tokens: Dict[str, Dict[str, int]] = field(default_factory=dict)
    start_time: float = 0.0

    def add_usage(self, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float = 0.0):
        """添加 token 用量"""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.total_cost_usd += cost_usd

        if model not in self.model_tokens:
            self.model_tokens[model] = {"prompt": 0, "completion": 0}
        self.model_tokens[model]["prompt"] += prompt_tokens
        self.model_tokens[model]["completion"] += completion_tokens

        if model not in self.model_costs:
            self.model_costs[model] = 0.0
        self.model_costs[model] += cost_usd

    def get_summary(self) -> Dict[str, Any]:
        """获取成本摘要"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "elapsed_seconds": round(elapsed, 1),
            "tokens_per_second": round(self.total_tokens / elapsed, 1) if elapsed > 0 else 0,
            "model_costs": self.model_costs,
            "model_tokens": self.model_tokens
        }


class ProgressMixin:
    _pending_tasks: set = set()

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
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
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

    def _report_file_event(self, file_path: str, content: str, description: str = "", file_type: str = "", operation: str = "create", **kwargs):
        """增强的文件事件，包含文件大小和复杂度"""
        file_size = len(content.encode('utf-8'))
        complexity = self._estimate_complexity(content, file_type)

        event = {
            "type": "file",
            "path": file_path,
            "content": content,
            "description": description,
            "file_type": file_type,
            "operation": operation,
            "file_size": file_size,
            "file_size_human": self._humanize_size(file_size),
            "complexity": complexity,
            "line_count": content.count('\n') + 1,
            **kwargs
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"文件事件推送失败: {e}")

    def _report_file_diff_event(self, file_path: str, old_content: str, new_content: str, operation: str = "create"):
        """增强的文件差异事件"""
        changes = self._calculate_changes(old_content, new_content)
        event = {
            "type": "file_diff",
            "path": file_path,
            "old_content": old_content,
            "new_content": new_content,
            "operation": operation,
            "changes": changes,
            "old_line_count": old_content.count('\n') + 1 if old_content else 0,
            "new_line_count": new_content.count('\n') + 1 if new_content else 0,
            "size_delta": len(new_content.encode('utf-8')) - len(old_content.encode('utf-8')) if old_content else len(new_content.encode('utf-8'))
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"文件差异事件推送失败: {e}")

    def _report_model_info(self, agent: str, model: str, **kwargs):
        """增强的模型信息事件"""
        event = {
            "type": "model_info",
            "agent": agent,
            "model": model,
            "timestamp": time.time(),
            **kwargs
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"模型信息事件推送失败: {e}")

    def _report_done_event(self, result_data: dict):
        event = {
            "type": "done",
            **result_data
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"完成事件推送失败: {e}")

    def _report_thinking(self, agent: str, message: str, **kwargs):
        """增强的思考事件，支持推理步骤和置信度"""
        event = {
            "type": "thinking",
            "agent": agent,
            "message": message,
            "timestamp": time.time(),
            **kwargs
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"思考事件推送失败: {e}")

    def _report_test_results(self, test_results: Dict[str, Any]):
        """测试结果事件"""
        event = {
            "type": "test_results",
            "timestamp": time.time(),
            **test_results
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"测试结果事件推送失败: {e}")

    def _report_validation_results(self, validation_results: Dict[str, Any]):
        """验证结果事件"""
        event = {
            "type": "validation_results",
            "timestamp": time.time(),
            **validation_results
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"验证结果事件推送失败: {e}")

    def _report_cost_update(self, cost_data: Dict[str, Any]):
        """成本更新事件"""
        event = {
            "type": "cost_update",
            "timestamp": time.time(),
            **cost_data
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"成本更新事件推送失败: {e}")

    def _report_performance_metrics(self, metrics: Dict[str, Any]):
        """性能指标事件"""
        event = {
            "type": "performance_metrics",
            "timestamp": time.time(),
            **metrics
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"性能指标事件推送失败: {e}")

    def _report_warning(self, message: str, **kwargs):
        """警告事件"""
        event = {
            "type": "warning",
            "message": message,
            "timestamp": time.time(),
            **kwargs
        }
        if self.callback:
            try:
                import json as _json
                result = self.callback(_json.dumps(event, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    task = asyncio.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
            except Exception as e:
                logger.error(f"警告事件推送失败: {e}")

    def _update_phase(self, phase: str):
        self._current_phase = phase

    def _report_current_cost(self):
        """报告当前成本统计"""
        if hasattr(self, 'cost_tracker') and self.cost_tracker:
            cost_summary = self.cost_tracker.get_summary()
            self._report_cost_update(cost_summary)
            return cost_summary
        return None

    def _report_final_metrics(self):
        """报告最终性能指标"""
        if hasattr(self, '_start_time') and self._start_time:
            elapsed = time.time() - self._start_time
            files_count = len(getattr(self, 'generated_files', []))

            metrics = {
                "total_duration": round(elapsed, 1),
                "files_generated": files_count,
                "files_per_minute": round(files_count / (elapsed / 60), 1) if elapsed > 0 else 0,
                "avg_file_time": round(elapsed / files_count, 1) if files_count > 0 else 0,
                "llm_calls": getattr(self, '_llm_call_count', 0),
                "retry_count": getattr(self, '_retry_count', 0)
            }

            # 包含成本数据
            if hasattr(self, 'cost_tracker') and self.cost_tracker:
                metrics["cost"] = self.cost_tracker.get_summary()

            self._report_performance_metrics(metrics)
            return metrics
        return None

    @staticmethod
    def _estimate_complexity(content: str, file_type: str) -> Dict[str, Any]:
        """估算代码复杂度"""
        lines = content.split('\n')
        line_count = len(lines)
        avg_line_length = sum(len(line) for line in lines) / line_count if line_count > 0 else 0

        # 简单的复杂度估算
        complexity_score = 0
        complexity_factors = []

        # 1. 行数复杂度
        if line_count > 500:
            complexity_score += 3
            complexity_factors.append("large_file")
        elif line_count > 200:
            complexity_score += 2
            complexity_factors.append("medium_file")
        elif line_count > 50:
            complexity_score += 1
            complexity_factors.append("small_file")

        # 2. 嵌套复杂度（检测缩进深度）
        max_indent = 0
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                max_indent = max(max_indent, indent)
        if max_indent > 16:
            complexity_score += 2
            complexity_factors.append("deep_nesting")

        # 3. 函数/类数量
        import re
        func_count = len(re.findall(r'def \w+', content))
        class_count = len(re.findall(r'class \w+', content))
        if func_count > 20 or class_count > 5:
            complexity_score += 2
            complexity_factors.append("many_definitions")

        # 4. 注释比例
        comment_lines = sum(1 for line in lines if line.strip().startswith('#'))
        comment_ratio = comment_lines / line_count if line_count > 0 else 0
        if comment_ratio < 0.05:
            complexity_factors.append("low_comments")

        # 复杂度等级
        if complexity_score >= 5:
            level = "high"
        elif complexity_score >= 3:
            level = "medium"
        else:
            level = "low"

        return {
            "score": complexity_score,
            "level": level,
            "factors": complexity_factors,
            "line_count": line_count,
            "avg_line_length": round(avg_line_length, 1),
            "max_indent_depth": max_indent // 4,
            "function_count": func_count,
            "class_count": class_count
        }

    @staticmethod
    def _humanize_size(size_bytes: int) -> str:
        """将字节大小转换为人类可读格式"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    @staticmethod
    def _calculate_changes(old_content: str, new_content: str) -> Dict[str, int]:
        """计算文件变更统计"""
        old_lines = old_content.split('\n') if old_content else []
        new_lines = new_content.split('\n') if new_content else []

        added = len(new_lines) - len(old_lines)
        removed = max(0, -added)

        # 简单统计变更行数
        changed = 0
        min_len = min(len(old_lines), len(new_lines))
        for i in range(min_len):
            if old_lines[i] != new_lines[i]:
                changed += 1

        return {
            "added": max(0, added),
            "removed": removed,
            "modified": changed,
            "total_old": len(old_lines),
            "total_new": len(new_lines)
        }
