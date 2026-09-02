import time
import logging
from typing import Optional, Dict, Any, List

from app.agent.complexity import ComplexityAnalyzer
from app.agent.specialists import Architect, FrontendEngineer, BackendEngineer, CodeReviewer
from app.agent.error_recovery import ErrorRecoveryLoop
from app.agent.code_validator import CodeValidator
from app.agent.api_contract_checker import APIContractChecker
from app.agent.code_patcher import CodePatcher, CrossFilePatcher
from app.agent.dynamic_model_router import LayeredModelRouter
from app.agent.tracing import traced
from app.agent.orchestrator_progress import PROGRESS_LABELS
from app.agent.specialist_base import get_global_llm_semaphore
from app.agent.models import DEFAULT_ARCHITECT_MODEL, DEFAULT_CODE_MODEL, DEFAULT_REASONING_MODEL

from .coverage_checker import check_requirement_coverage
from .feature_extractor import extract_and_save_feature_list
from .error_recovery import ErrorRecoveryMixin
from .traditional_generate import TraditionalGenerateMixin
from .spec_first_generate import SpecFirstGenerateMixin
from .incremental_generate import IncrementalGenerateMixin
from .incremental_modify import IncrementalModifyMixin
from .evaluate_mixin import EvaluationMixin

logger = logging.getLogger(__name__)


class GenerationMixin(
    ErrorRecoveryMixin,
    TraditionalGenerateMixin,
    SpecFirstGenerateMixin,
    IncrementalGenerateMixin,
    IncrementalModifyMixin,
    EvaluationMixin,
):

    @traced("orchestrator.initialize_components", attributes={"component": "orchestrator"})
    async def _initialize_components(self, requirement: str):
        self._start_time = time.time()
        self._update_phase("analyzing")

        # 初始化成本追踪器
        if hasattr(self, 'cost_tracker'):
            self.cost_tracker.start_time = time.time()

        # 初始化 MCP 工具（如果配置了 MCP Server）
        await self._init_mcp_tools()

        self.analyzer = ComplexityAnalyzer()
        self.complexity = self.analyzer.analyze(requirement)

        self._report_progress(
            PROGRESS_LABELS["analyzing_complexity"],
            1, 5,
            complexity=self.complexity.level.value,
            estimated_files=self.complexity.estimated_files,
            tech_stack=self.complexity.key_technologies
        )

        if getattr(self, 'use_dynamic_topology', True):
            self.model_router = LayeredModelRouter()
            self.model_assignment = self.model_router.get_assignment()
        else:
            self.model_router = None
            self.model_assignment = None

        # 安全获取模型名称（model_assignment 可能为 None）
        def _get_model(attr: str, default: str) -> str:
            return getattr(self.model_assignment, attr, default) if self.model_assignment else default

        self._report_progress(
            PROGRESS_LABELS["assigning_models"],
            2, 5,
            architect=_get_model("architect_model", DEFAULT_ARCHITECT_MODEL),
            frontend=_get_model("frontend_model", DEFAULT_CODE_MODEL),
            backend=_get_model("backend_model", DEFAULT_CODE_MODEL),
            reviewer=_get_model("reviewer_model", DEFAULT_ARCHITECT_MODEL)
        )

        semaphore = get_global_llm_semaphore()
        cost_tracker = getattr(self, 'cost_tracker', None)
        complexity_level = self.complexity.level.value if self.complexity else "medium"

        self.architect = Architect("架构师", _get_model("architect_model", DEFAULT_ARCHITECT_MODEL), task_type="generate", api_key_token=self.api_key_token, provider_id=self.provider_id, semaphore=semaphore, cost_tracker=cost_tracker, complexity=complexity_level, cancel_event=self.cancel_event)
        self.frontend_engineer = FrontendEngineer("前端工程师", _get_model("frontend_model", DEFAULT_CODE_MODEL), task_type="generate", api_key_token=self.api_key_token, provider_id=self.provider_id, semaphore=semaphore, cost_tracker=cost_tracker, complexity=complexity_level, cancel_event=self.cancel_event)
        self.backend_engineer = BackendEngineer("后端工程师", _get_model("backend_model", DEFAULT_CODE_MODEL), task_type="generate", api_key_token=self.api_key_token, provider_id=self.provider_id, semaphore=semaphore, cost_tracker=cost_tracker, complexity=complexity_level, cancel_event=self.cancel_event)
        self.reviewer = CodeReviewer("审查员", _get_model("reviewer_model", DEFAULT_ARCHITECT_MODEL), task_type="review", api_key_token=self.api_key_token, provider_id=self.provider_id, semaphore=semaphore, cost_tracker=cost_tracker, complexity=complexity_level, cancel_event=self.cancel_event)
        self.validator = CodeValidator(self.output_dir)
        self.error_recovery = ErrorRecoveryLoop(self.validator, self.reviewer, api_key_token=self.api_key_token, cancel_event=self.cancel_event)
        self.api_contract_checker = APIContractChecker()
        self.code_patcher = CodePatcher(llm_call_fn=self._call_llm_for_patch)
        self.cross_file_patcher = CrossFilePatcher(self.code_patcher)

        self._report_progress(
            PROGRESS_LABELS["initializing_roles"],
            3, 5,
            roles=["架构师", "前端工程师", "后端工程师", "审查员"]
        )

    async def _init_mcp_tools(self):
        """初始化 MCP 工具（如果配置了 MCP Server）"""
        try:
            from app.agent.mcp_client import MCPClientManager
            manager = MCPClientManager()
            connected = await manager.load_servers()
            if connected > 0:
                tool_names = manager.get_tool_names()
                logger.info(f"MCP 工具已加载: {tool_names}")
                self._report_progress("mcp_tools_loaded", 1, 5, mcp_tools=tool_names)
        except Exception as e:
            logger.debug(f"MCP 初始化跳过（未配置或加载失败）: {e}")

    @traced("orchestrator.generate", attributes={"component": "orchestrator"})
    async def generate(self, requirement: str) -> Dict[str, Any]:
        if self.evaluation_only:
            return await self.evaluate(requirement)

        if self.spec_first:
            return await self.generate_with_spec_first(requirement, self.callback)

        try:
            return await self._generate_traditional(requirement)
        except AttributeError as e:
            logger.error(f"_generate_traditional AttributeError: {e}")
            raise
        except Exception as e:
            logger.error(f"项目生成失败: {e}")
            raise RuntimeError(f"项目生成失败: {str(e)[:200]}") from e

    def _check_requirement_coverage(
        self, requirement: str,
        architecture: Dict, file_plan: List[Dict]
    ) -> Dict[str, Any]:
        return check_requirement_coverage(
            requirement, architecture, file_plan, self._association_result
        )

    async def _extract_and_save_feature_list(
        self, requirement: str,
        generated_files: List[Dict],
        domain: str = ""
    ) -> Optional[Dict]:
        return await extract_and_save_feature_list(
            requirement, generated_files, domain
        )
