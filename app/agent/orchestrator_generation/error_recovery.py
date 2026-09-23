import asyncio
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ReAct 自动修复的总超时：engine 每轮只做心跳超时（600s），5 轮最坏可阻塞
# 近一小时，传统生成路径需要一个总时长上限。
REACT_AUTO_FIX_TIMEOUT = 900.0


class ErrorRecoveryMixin:

    async def _try_react_auto_fix(self, failed_test_results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # `self.error_recovery` 是构造出来的对象、恒为真值，真正的开关是
        # `enable_error_recovery`；只判对象存在性会让关掉开关的调用方仍走该路径。
        if (
            not getattr(self, "enable_error_recovery", True)
            or not self.error_recovery
            or not self.reviewer
        ):
            return None
        failed_tests = failed_test_results.get("failed_tests", [])
        if not failed_tests:
            return None
        assignment = getattr(self, "model_assignment", None)
        model_name = getattr(assignment, "backend_model", None) if assignment else None
        if not model_name:
            raise RuntimeError("model assignment is required for ReAct auto-fix")
        from app.agent.test_runner import IsolatedTestRunner
        from app.agent.react_agent import ReActAgent, ReActResult
        react_agent = ReActAgent(
            model_name=model_name,
            max_iterations=5,
            api_key_token=getattr(self, "api_key_token", None),
        )
        test_logs = failed_test_results.get("logs_preview", "")
        task_description = (
            f"自动修复以下失败的测试: {', '.join(failed_tests[:5])}. 错误日志: {test_logs[:500]}"
        )
        try:
            result: ReActResult = await asyncio.wait_for(
                react_agent.process(
                    task_description, {"project_path": str(self.output_dir)}
                ),
                timeout=REACT_AUTO_FIX_TIMEOUT,
            )
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"react auto-fix timed out after {REACT_AUTO_FIX_TIMEOUT:.0f}s"
            ) from e
        except Exception as e:
            raise RuntimeError(f"react auto-fix failed: {e}") from e
        if result.success:
            test_runner = IsolatedTestRunner(self.output_dir)
            new_test_results = await self._run_dynamic_tests(test_runner)
            return {"fixed": new_test_results.get("success", False), "test_results": new_test_results}
        raise RuntimeError("react auto-fix did not repair failed tests")
