import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from app.agent.api_contract_checker import APIContractChecker
from app.agent.code_patcher import CodePatcher, CrossFilePatcher
from app.agent.code_validator import CodeValidator
from app.agent.complexity import ComplexityAnalysis, ComplexityAnalyzer
from app.agent.dependency_graph import DependencyGraph
from app.agent.dynamic_model_router import LayeredModelRouter, ModelAssignment
from app.agent.error_recovery import ErrorRecoveryLoop
from app.agent.feedback_learner import FeedbackLearner
from app.agent.memory import ConversationMemory, KnowledgeMemory
from app.agent.orchestrator_files import FilesMixin
from app.agent.orchestrator_generation import GenerationMixin
from app.agent.orchestrator_progress import (
    CostTracker,
    ProgressMixin,
)
from app.agent.orchestrator_requirements import RequirementAssociationMixin
from app.agent.orchestrator_testing import TestingMixin
from app.agent.orchestrator_utils import UtilsMixin
from app.agent.session_manager import SessionManager
from app.agent.spec_cache import SpecCache
from app.agent.specialists import (
    Architect,
    BackendEngineer,
    CodeReviewer,
    FrontendEngineer,
)
from app.core.paths import PROJECTS_BASE_DIR

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
        callback: Callable | None = None,
        session_manager: SessionManager | None = None,
        session_id: str | None = None,
        incremental: bool = False,
        spec_cache: SpecCache | None = None,
        require_approval: bool = False,
        approval_callback: Callable | None = None,
        feedback_learner: FeedbackLearner | None = None,
        evaluation_only: bool = False,
        api_key_token: str | None = None,
        provider_id: str | None = None,
        cancel_event: asyncio.Event | None = None,
        decision_callback: Callable | None = None,
        cross_validation_fallback: bool = False
    ):
        # 保存原始相对路径（给 LLM 看的，存到 progress 事件中）
        self._relative_output_dir = str(output_dir)
        self.output_dir = Path(output_dir)
        # 相对路径（如 "1/xxx"）解析到 PROJECTS_BASE_DIR 下，作为实际写入目录
        if not self.output_dir.is_absolute() and not str(self.output_dir).startswith("./projects"):
            self.output_dir = Path(PROJECTS_BASE_DIR) / self.output_dir
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
        self.decision_callback = decision_callback

        self.feedback_learner = feedback_learner

        self.evaluation_only = evaluation_only
        self.api_key_token = api_key_token
        self.provider_id = provider_id
        self.cancel_event = cancel_event
        self.cross_validation_fallback = cross_validation_fallback
        self.heartbeat_tracker = None

        from app.agent.git_operations import GitOperations
        from app.agent.snapshot_manager import SnapshotManager
        self.git_ops = GitOperations()
        self.snapshot_mgr = SnapshotManager(self.git_ops)

        if memory_enabled:
            self.conversation_memory = ConversationMemory()
            self.knowledge_memory = KnowledgeMemory()

        self.analyzer: ComplexityAnalyzer | None = None
        self.model_router: LayeredModelRouter | None = None
        self.architect: Architect | None = None
        self.frontend_engineer: FrontendEngineer | None = None
        self.backend_engineer: BackendEngineer | None = None
        self.reviewer: CodeReviewer | None = None
        self.validator: CodeValidator | None = None
        self.error_recovery: ErrorRecoveryLoop | None = None
        self.api_contract_checker: APIContractChecker | None = None
        self.code_patcher: CodePatcher | None = None
        self.cross_file_patcher: CrossFilePatcher | None = None
        self.dependency_graph_obj: DependencyGraph | None = None

        self.complexity: ComplexityAnalysis | None = None
        self.model_assignment: ModelAssignment | None = None
        self.generated_files: list[dict] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._start_time: float | None = None
        self._current_phase: str = "initializing"
        self._generated_contents: dict[str, str] = {}
        self.shared_context = None
        self.artifact_committer = None
        self.artifact_completion_events = []
        self.validation_report = None

        # 成本追踪器
        self.cost_tracker = CostTracker()
