# 保留原有导出
from app.agent.failure_clusterer import FailureCluster, FailureClusterer
from app.agent.feedback_learner import FeedbackLearner

# 新增智能修改优化模块导出
from app.agent.impact_analyzer import ChangeSummary, ImpactAnalyzer
from app.agent.multi_model_agent import MultiModelAgent
from app.agent.orchestrator import OrchestratorAgent
from app.agent.project_profiler import ProjectProfile, ProjectProfiler
from app.agent.react_agent import ReActAgent
from app.agent.session_manager import SessionManager
from app.agent.spec_cache import SpecCache
from app.agent.test_selector import TestSelector

__all__ = [
    'ChangeSummary',
    'FailureCluster',
    'FailureClusterer',
    'FeedbackLearner',
    # 新增模块
    'ImpactAnalyzer',
    'MultiModelAgent',
    # 原有模块
    'OrchestratorAgent',
    'ProjectProfile',
    'ProjectProfiler',
    'ReActAgent',
    'SessionManager',
    'SpecCache',
    'TestSelector',
]
