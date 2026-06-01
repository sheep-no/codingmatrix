import time
import asyncio
import logging
from typing import Optional, Dict, Any, Callable, List

from app.agent.complexity import ComplexityAnalyzer
from app.agent.specialists import Specialist, Architect, FrontendEngineer, BackendEngineer, CodeReviewer
from app.agent.error_recovery import ErrorRecoveryLoop
from app.agent.code_validator import CodeValidator
from app.agent.api_contract_checker import APIContractChecker
from app.agent.code_patcher import CodePatcher, CrossFilePatcher
from app.agent.dynamic_model_router import LayeredModelRouter
from app.agent.tracing import traced
from app.agent.orchestrator_progress import PROGRESS_LABELS, MAX_CONCURRENT_LLM_CALLS

from .coverage_checker import check_requirement_coverage
from .feature_extractor import extract_and_save_feature_list
from .error_recovery import ErrorRecoveryMixin
from .traditional_generate import TraditionalGenerateMixin
from .spec_first_generate import SpecFirstGenerateMixin
from .incremental_generate import IncrementalGenerateMixin
from .evaluate_mixin import EvaluationMixin

logger = logging.getLogger(__name__)


class GenerationMixin(
    ErrorRecoveryMixin,
    TraditionalGenerateMixin,
    SpecFirstGenerateMixin,
    IncrementalGenerateMixin,
    EvaluationMixin,
):

    @traced("orchestrator.initialize_components", attributes={"component": "orchestrator"})
    async def _initialize_components(self, requirement: str):
        self._start_time = time.time()
        self._update_phase("analyzing")
        
        # 初始化成本追踪器
        if hasattr(self, 'cost_tracker'):
            self.cost_tracker.start_time = time.time()

        self.analyzer = ComplexityAnalyzer()
        self.complexity = await self.analyzer.analyze_with_llm(requirement)

        self._report_progress(
            PROGRESS_LABELS["analyzing_complexity"],
            1, 5,
            complexity=self.complexity.level.value,
            estimated_files=self.complexity.estimated_files,
            tech_stack=self.complexity.key_technologies
        )

        if getattr(self, 'use_dynamic_topology', True):
            self.model_router = LayeredModelRouter()
            self.model_assignment = self.model_router.get_assignment(self.complexity.level)
        else:
            self.model_router = None
            self.model_assignment = None

        self._report_progress(
            PROGRESS_LABELS["assigning_models"],
            2, 5,
            architect=self.model_assignment.architect_model,
            frontend=self.model_assignment.frontend_model,
            backend=self.model_assignment.backend_model,
            reviewer=self.model_assignment.reviewer_model
        )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        Specialist.set_semaphore(semaphore)

        self.architect = Architect("架构师", self.model_assignment.architect_model, task_type="generate", api_key_token=self.api_key_token, provider_id=self.provider_id)
        self.frontend_engineer = FrontendEngineer("前端工程师", self.model_assignment.frontend_model, task_type="generate", api_key_token=self.api_key_token, provider_id=self.provider_id)
        self.backend_engineer = BackendEngineer("后端工程师", self.model_assignment.backend_model, task_type="generate", api_key_token=self.api_key_token, provider_id=self.provider_id)
        self.reviewer = CodeReviewer("审查员", self.model_assignment.reviewer_model, task_type="review", api_key_token=self.api_key_token, provider_id=self.provider_id)
        self.validator = CodeValidator(self.output_dir)
        self.error_recovery = ErrorRecoveryLoop(self.validator, self.reviewer)
        self.api_contract_checker = APIContractChecker()
        self.code_patcher = CodePatcher(llm_call_fn=self._call_llm_for_patch)
        self.cross_file_patcher = CrossFilePatcher(self.code_patcher)

        self._report_progress(
            PROGRESS_LABELS["initializing_roles"],
            3, 5,
            roles=["架构师", "前端工程师", "后端工程师", "审查员"]
        )

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