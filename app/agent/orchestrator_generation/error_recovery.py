import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ErrorRecoveryMixin:

    async def _try_react_auto_fix(self, failed_test_results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.error_recovery or not self.reviewer:
            return None
        failed_tests = failed_test_results.get("failed_tests", [])
        if not failed_tests:
            return None
        try:
            from app.agent.test_runner import IsolatedTestRunner
            from app.agent.react_agent import ReActAgent, ReActResult
            fallback_model = getattr(self.model_assignment, 'fallback_model', None) if hasattr(self, 'model_assignment') else None
            react_agent = ReActAgent(
                model_name=fallback_model or "Qwen/Qwen3-8B",
                max_iterations=5,
                api_key_token=getattr(self, 'api_key_token', None),
            )
            test_logs = failed_test_results.get("logs_preview", "")
            task_description = f"自动修复以下失败的测试: {', '.join(failed_tests[:5])}. 错误日志: {test_logs[:500]}"
            result: ReActResult = await react_agent.process(task_description, {"project_path": str(self.output_dir)})
            if result.success:
                test_runner = IsolatedTestRunner(self.output_dir)
                new_test_results = await self._run_dynamic_tests(test_runner)
                return {"fixed": new_test_results.get("success", False), "test_results": new_test_results}
        except Exception as e:
            logger.warning(f"ReAct 自动修复失败: {e}")
        return None
