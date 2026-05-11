"""
AI Agent 模块

多模型 Agent 架构，提供：
- ModelRegistry: 模型注册表
- ModelRouter: 任务路由
- TaskPlanner: 任务规划
- AgentExecutor: 执行器（增强版）
- AIReviewer: AI审查器
- FileContract: 文件契约
- MultiModelAgent: 多模型Agent主类
- AgentMemory: 记忆系统
- ReActAgent: ReAct 自我反思Agent
- StreamingExecutor: 流式执行器
"""

from app.agent.multi_model_agent import (
    TaskType,
    ModelCapability,
    ModelInfo,
    ModelRegistry,
    ModelRouter,
    FileContract,
    ReviewResult,
    AIReviewer,
    TaskPlanner,
    AgentExecutor,
    MultiModelAgent,
)

from app.agent.memory import (
    AgentMemory,
    MemoryEntry,
    ConversationMemory,
    KnowledgeMemory,
    ReflectionMemory,
    BaseMemory,
)

from app.agent.executor import (
    EnhancedExecutor,
    ToolRegistry,
    ToolResult,
    ToolType,
    StreamingExecutor,
)

from app.agent.react_agent import (
    ReActAgent,
    ReActStep,
    ReActStepType,
    ReActResult,
    ReActWithFallback,
)

from app.agent.orchestrator import (
    OrchestratorAgent,
    ComplexityAnalyzer,
    ComplexityAnalysis,
    ProjectComplexity,
    LayeredModelRouter,
    ModelAssignment,
    CodeValidator,
    ErrorRecoveryLoop,
    Architect,
    FrontendEngineer,
    BackendEngineer,
    CodeReviewer,
    GenerationProgress,
)

__all__ = [
    # Multi-model Agent
    "TaskType",
    "ModelCapability",
    "ModelInfo",
    "ModelRegistry",
    "ModelRouter",
    "FileContract",
    "ReviewResult",
    "AIReviewer",
    "TaskPlanner",
    "AgentExecutor",
    "MultiModelAgent",

    # Memory System
    "AgentMemory",
    "MemoryEntry",
    "ConversationMemory",
    "KnowledgeMemory",
    "ReflectionMemory",
    "BaseMemory",

    # Executor
    "EnhancedExecutor",
    "ToolRegistry",
    "ToolResult",
    "ToolType",
    "StreamingExecutor",

    # ReAct Agent
    "ReActAgent",
    "ReActStep",
    "ReActStepType",
    "ReActResult",
    "ReActWithFallback",

    # Orchestrator Agent
    "OrchestratorAgent",
    "ComplexityAnalyzer",
    "ComplexityAnalysis",
    "ProjectComplexity",
    "LayeredModelRouter",
    "ModelAssignment",
    "CodeValidator",
    "ErrorRecoveryLoop",
    "Architect",
    "FrontendEngineer",
    "BackendEngineer",
    "CodeReviewer",
    "GenerationProgress",
]
