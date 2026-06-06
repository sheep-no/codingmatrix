# 保留原有导出
from app.agent.orchestrator import OrchestratorAgent
from app.agent.multi_model_agent import MultiModelAgent
from app.agent.react_agent import ReActAgent
from app.agent.session_manager import SessionManager
from app.agent.spec_cache import SpecCache
from app.agent.feedback_learner import FeedbackLearner

# 新增智能修改优化模块导出
from app.agent.impact_analyzer import ImpactAnalyzer, ChangeSummary
from app.agent.project_profiler import ProjectProfiler, ProjectProfile
from app.agent.test_selector import TestSelector
from app.agent.failure_clusterer import FailureClusterer, FailureCluster

__all__ = [
    # 原有模块
    'OrchestratorAgent',
    'MultiModelAgent',
    'ReActAgent',
    'SessionManager',
    'SpecCache',
    'FeedbackLearner',
    # 新增模块
    'ImpactAnalyzer',
    'ChangeSummary',
    'ProjectProfiler',
    'ProjectProfile',
    'TestSelector',
    'FailureClusterer',
    'FailureCluster',
]
