import os
import logging
from typing import Optional, Callable, List, Dict
from pathlib import Path

from app.utils.file_operator import FileOperator, PathSecurityError
from app.utils.retry import retry_on_failure
from app.utils.circuit_breaker import circuit_breaker

from app.agent.complexity import ProjectComplexity, ComplexityAnalysis, ComplexityAnalyzer
from app.agent.code_validator import CodeValidator
from app.agent.specialists import Specialist, Architect, FrontendEngineer, BackendEngineer, CodeReviewer
from app.agent.error_recovery import ErrorRecoveryLoop, FixAttempt

from app.agent.multi_model_agent import ModelRegistry, ModelInfo, ModelCapability, TaskType
from app.agent.shared_context import SharedContext
from app.agent.api_contract_checker import APIContractChecker, check_api_consistency, generate_frontend_prompt_contract
from app.agent.code_patcher import CodePatcher, apply_incremental_change, CrossFilePatcher
from app.agent.spec_first_generator import SpecFirstGenerator
from app.agent.refinement_loop import RefinementLoop, RefinementResult
from app.agent.dependency_graph import DependencyGraph
from app.agent.cross_validator import CrossValidator
from app.agent.session_manager import SessionManager
from app.agent.spec_cache import SpecCache
from app.agent.feedback_learner import FeedbackLearner
from app.agent.memory import ConversationMemory, KnowledgeMemory
from app.agent.test_runner import TestRunner, IsolatedTestRunner

from app.agent.dynamic_model_router import LayeredModelRouter, ModelAssignment

from app.agent.tracing import tracer, traced, get_current_trace_id, set_trace_id

from app.agent.orchestrator_progress import (
    PROGRESS_LABELS, GenerationProgress, ProgressMixin, CostTracker,
    MAX_CONCURRENT_LLM_CALLS, MAX_CONTENT_FOR_CONTEXT,
)
from app.agent.orchestrator_generation import GenerationMixin
from app.agent.orchestrator_files import FilesMixin
from app.agent.orchestrator_testing import TestingMixin
from app.agent.orchestrator_utils import UtilsMixin
from app.agent.orchestrator_requirements import RequirementAssociationMixin

logger = logging.getLogger(__name__)


class OrchestratorAgent(
    ProgressMixin,
    GenerationMixin,
    FilesMixin,
    TestingMixin,
    UtilsMixin,
    RequirementAssociationMixin,
):

    def __init__(
        self,
        output_dir: str = "./generated_project",
        enable_review: bool = True,
        enable_validation: bool = True,
        enable_error_recovery: bool = True,
        memory_enabled: bool = True,
        spec_first: bool = True,
        dependency_graph: bool = True,
        use_dynamic_topology: bool = True,
        callback: Optional[Callable] = None,
        session_manager: Optional[SessionManager] = None,
        session_id: Optional[str] = None,
        incremental: bool = False,
        spec_cache: Optional[SpecCache] = None,
        require_approval: bool = False,
        approval_callback: Optional[Callable] = None,
        feedback_learner: Optional[FeedbackLearner] = None,
        evaluation_only: bool = False,
        api_key_token: Optional[str] = None,
        provider_id: Optional[str] = None
    ):
        self.output_dir = Path(output_dir)
        self.enable_review = enable_review
        self.enable_validation = enable_validation
        self.enable_error_recovery = enable_error_recovery
        self.memory_enabled = memory_enabled
        self.spec_first = spec_first
        self.dependency_graph = dependency_graph
        self.use_dynamic_topology = use_dynamic_topology
        self.callback = callback

        self.session_manager = session_manager
        self.session_id = session_id
        self.incremental = incremental
        self._session_state = None

        self.spec_cache = spec_cache

        self.require_approval = require_approval
        self.approval_callback = approval_callback

        self.feedback_learner = feedback_learner

        self.evaluation_only = evaluation_only
        self.api_key_token = api_key_token
        self.provider_id = provider_id

        from app.agent.git_operations import GitOperations
        from app.agent.snapshot_manager import SnapshotManager
        self.git_ops = GitOperations()
        self.snapshot_mgr = SnapshotManager(self.git_ops)

        if memory_enabled:
            self.conversation_memory = ConversationMemory()
            self.knowledge_memory = KnowledgeMemory()

        self.analyzer: Optional[ComplexityAnalyzer] = None
        self.model_router: Optional[LayeredModelRouter] = None
        self.architect: Optional[Architect] = None
        self.frontend_engineer: Optional[FrontendEngineer] = None
        self.backend_engineer: Optional[BackendEngineer] = None
        self.reviewer: Optional[CodeReviewer] = None
        self.validator: Optional[CodeValidator] = None
        self.error_recovery: Optional[ErrorRecoveryLoop] = None
        self.api_contract_checker: Optional[APIContractChecker] = None
        self.code_patcher: Optional[CodePatcher] = None
        self.cross_file_patcher: Optional[CrossFilePatcher] = None
        self.dependency_graph_obj: Optional[DependencyGraph] = None

        self.complexity: Optional[ComplexityAnalysis] = None
        self.model_assignment: Optional[ModelAssignment] = None
        self.generated_files: List[Dict] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._start_time: Optional[float] = None
        self._current_phase: str = "initializing"
        self._generated_contents: Dict[str, str] = {}
        
        # 成本追踪器
        self.cost_tracker = CostTracker()
        Specialist.set_cost_tracker(self.cost_tracker)