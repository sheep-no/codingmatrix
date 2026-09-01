from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import re


# ============================================================================
# 输入验证常量
# ============================================================================

# 会话 ID 格式：只允许字母、数字、下划线、连字符
SESSION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
SESSION_ID_MAX_LENGTH = 128
SESSION_ID_MIN_LENGTH = 5

# 路径安全：不允许绝对路径、父目录遍历
PATH_ABSOLUTE_PATTERN = re.compile(r'^/|^[a-zA-Z]:')
PATH_TRAVERSAL_PATTERN = re.compile(r'\.\./|\.\.\\')

# Prompt 安全最大长度（字符）
MAX_PROMPT_LENGTH = 5000


def validate_session_id(v: Optional[str], field_name: str = "session_id") -> Optional[str]:
    """验证会话 ID 格式"""
    if v is None:
        return v
    
    if len(v) < SESSION_ID_MIN_LENGTH:
        raise ValueError(f"{field_name} 长度不能少于 {SESSION_ID_MIN_LENGTH} 个字符")
    if len(v) > SESSION_ID_MAX_LENGTH:
        raise ValueError(f"{field_name} 长度不能超过 {SESSION_ID_MAX_LENGTH} 个字符")
    if not SESSION_ID_PATTERN.match(v):
        raise ValueError(f"{field_name} 只能包含字母、数字、下划线和连字符")
    
    return v


def validate_path_safety(v: Optional[str], field_name: str = "path") -> Optional[str]:
    """验证路径安全性"""
    if v is None:
        return v
    
    if PATH_ABSOLUTE_PATTERN.match(v):
        raise ValueError(f"{field_name} 不能是绝对路径")
    if PATH_TRAVERSAL_PATTERN.search(v):
        raise ValueError(f"{field_name} 不能包含父目录遍历 (../)")
    if ".." in v:
        raise ValueError(f"{field_name} 不能包含 .. 路径组件")
    
    return v


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    task: str = Field(..., description="任务描述", min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")
    task_type: Optional[str] = Field(None, description="任务类型：general, code_generation, code_review, file_operation, visual, reasoning, fast_response")
    files: Optional[List[str]] = Field(None, description="附加文件列表", max_items=100)
    prefer_fast: bool = Field(False, description="是否优先快速模型")

    @field_validator('task')
    @classmethod
    def validate_task(cls, v):
        if not v.strip():
            raise ValueError("任务描述不能为空")
        return v.strip()


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    success: bool
    task_type: str
    model_used: str
    steps: int
    results: List[Any]
    issues: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None


class FileOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    operation: str = Field(..., description="操作类型：read, write, delete, create")
    path: str = Field(..., description="文件路径", min_length=1, max_length=1000)
    content: Optional[str] = Field(None, description="文件内容（write 时需要）")
    require_review: bool = Field(True, description="是否需要 AI 审查")

    @field_validator('operation')
    @classmethod
    def validate_operation(cls, v):
        allowed = {"read", "write", "delete", "create"}
        if v not in allowed:
            raise ValueError(f"不支持的操作：{v}")
        return v

    @field_validator('path')
    @classmethod
    def validate_path(cls, v):
        resolved = str(Path(v).resolve())
        if ".." in v or v.startswith("/"):
            raise ValueError("路径格式不正确")
        if "\\" in v:
            raise ValueError("路径格式不正确")
        return v


class ModelListResponse(BaseModel):
    models: List[Dict[str, Any]]


class ReviewRequest(BaseModel):
    content: str = Field(..., description="待审查内容")
    content_type: str = Field(..., description="内容类型: code, plan, file")
    context: Optional[str] = Field(None, description="上下文")


class ReviewResponse(BaseModel):
    approved: bool
    issues: List[str]
    suggestions: List[str]
    risk_level: str


class ReActRequest(BaseModel):
    task: str = Field(..., description="任务描述", min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")
    enable_streaming: bool = Field(True, description="是否启用流式输出")
    max_iterations: int = Field(10, description="最大迭代次数", ge=1, le=50)
    use_fallback: bool = Field(True, description="失败时是否使用降级模型")


class CreateSessionRequest(BaseModel):
    session_type: str = Field("general", description="会话类型: general, react, code, visual")
    model_key: str = Field("deepseek-r1-qwen3-8b", description="模型键")


class SessionResponse(BaseModel):
    session_id: str
    session_type: str
    model_key: str
    created_at: Optional[str] = None


class SessionDetailResponse(BaseModel):
    session_id: str
    session_type: str
    model_key: str
    context_summary: Optional[str] = None
    total_steps: int
    total_tokens: int
    success: bool
    memory_entries: int
    reflections: int
    created_at: Optional[str] = None
    ended_at: Optional[str] = None


class KnowledgeRequest(BaseModel):
    content: str = Field(..., description="知识内容", min_length=1)
    knowledge_key: Optional[str] = Field(None, description="知识关键词")
    category: str = Field("general", description="分类")
    importance: float = Field(0.5, description="重要性", ge=0.0, le=1.0)
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")


class KnowledgeResponse(BaseModel):
    id: str
    content: str
    knowledge_key: Optional[str]
    category: str
    importance: float
    usage_count: int
    created_at: Optional[str] = None
    tags: Optional[List[str]] = None


class ModelStatsResponse(BaseModel):
    model_key: str
    model_name: Optional[str]
    request_count: int
    total_tokens: int
    success_count: int
    failure_count: int
    avg_execution_time: float
    last_used_at: Optional[str] = None


class SaveProjectRequest(BaseModel):
    name: str = Field(..., max_length=200, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    project_path: Optional[str] = Field(None, description="磁盘项目路径")
    project_data: str = Field(..., description="项目数据 (JSON 字符串)")


class SaveProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    project_path: Optional[str]
    created_at: datetime
    message: str


class ProjectListResponse(BaseModel):
    projects: list
    total: int
    max_allowed: int


class LoadProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    project_path: Optional[str]
    project_data: str
    created_at: datetime
    updated_at: Optional[datetime]


class OrchestratorRequest(BaseModel):
    requirement: str = Field(..., description="项目需求描述", min_length=1, max_length=MAX_PROMPT_LENGTH)
    project_name: Optional[str] = Field(None, description="项目名称（可选，自动生成）", max_length=50)
    output_dir: Optional[str] = Field(None, description="输出目录（可选）", max_length=500)
    enable_review: bool = Field(True, description="是否启用代码审查")
    enable_validation: bool = Field(True, description="是否启用代码验证")
    enable_error_recovery: bool = Field(True, description="是否启用错误恢复")
    enable_memory: bool = Field(True, description="是否启用记忆系统")
    spec_first: bool = Field(True, description="是否启用 Spec-First 模式")
    dependency_graph: bool = Field(True, description="是否启用依赖图分层生成")
    session_id: Optional[str] = Field(None, description="会话ID（用于增量生成/续传）")
    incremental: bool = Field(False, description="是否启用增量生成")
    require_approval: bool = Field(False, description="是否要求关键文件人工审批")
    evaluation_only: bool = Field(False, description="只评价不修改 - 输出分析报告和改进建议，不生成代码文件")
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token（用于从 Redis 获取用户自定义 Key）")
    provider_id: Optional[str] = Field(None, description="动态供应商 ID（使用用户自定义 API 端点）")
    project_path: Optional[str] = Field(
        None,
        description="前端传来的项目路径（增量模式用，兼容旧时间戳目录）",
        max_length=500
    )

    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v):
        return validate_session_id(v, "session_id")

    @field_validator('project_name')
    @classmethod
    def validate_project_name(cls, v):
        if v is None:
            return v
        # 只允许字母、数字、下划线、连字符
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("项目名称只能包含字母、数字、下划线和连字符")
        if len(v) > 50:
            raise ValueError("项目名称长度不能超过50个字符")
        return v

    @field_validator('requirement')
    @classmethod
    def validate_requirement(cls, v):
        if not v.strip():
            raise ValueError("需求描述不能为空")
        # 检查是否包含过多的连续换行（可能是注入尝试）
        if '\n\n\n\n' in v:
            raise ValueError("需求描述格式异常")
        return v.strip()

    @field_validator('project_path')
    @classmethod
    def validate_project_path(cls, v):
        """项目路径安全校验（增量模式）"""
        return validate_path_safety(v, "project_path")


class SessionActionRequest(BaseModel):
    action: str = Field(..., description="操作类型: resume, cancel, approve, reject")
    approved: bool = Field(True, description="是否批准（用于 approve/reject 操作）")


class OrchestratorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    success: bool
    output_dir: str
    total_files_created: int
    total_files_failed: Optional[int] = 0
    complexity: str
    models_used: Dict[str, str]
    files: List[Dict[str, Any]]
    validation: Dict[str, Any]
    test_results: Optional[Dict[str, Any]] = None
    specs_generated: Optional[List[str]] = None
    context_summary: Optional[str] = None
    context_full: Optional[Dict[str, Any]] = None
    errors: List[str]
    warnings: List[str]
    elapsed_time: float
    fix_attempts: List[Dict[str, Any]]
    session_id: Optional[str] = None


class ModifyRequest(BaseModel):
    requirement: Optional[str] = Field(None, description="修改需求描述（分析类请求必填，修改类可选）", max_length=5000)
    project_path: Optional[str] = Field(None, description="已有项目路径（相对于 projects 目录）")
    output_dir: Optional[str] = Field(None, description="输出目录（绝对路径或相对于 projects 目录）")
    session_id: Optional[str] = Field(None, description="已有会话 ID")
    enable_review: bool = Field(True, description="是否启用代码审查")
    enable_validation: bool = Field(True, description="是否启用代码验证")
    enable_error_recovery: bool = Field(True, description="是否启用错误恢复")
    enable_memory: bool = Field(True, description="是否启用记忆系统")
    dependency_graph: bool = Field(True, description="是否启用依赖图")
    enable_cross_file_analysis: bool = Field(True, description="是否启用跨文件依赖分析（v4.8.0）")
    max_dependency_depth: int = Field(3, description="最大传递依赖深度（v4.8.0）", ge=1, le=10)
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token（用于从 Redis 获取用户自定义 Key）")
    incremental: bool = Field(True, description="是否增量修改")


class ComplexityAnalysisRequest(BaseModel):
    requirement: str = Field(..., description="项目需求描述", min_length=1, max_length=5000)


class ComplexityAnalysisResponse(BaseModel):
    level: str
    estimated_files: int
    has_frontend: bool
    has_backend: bool
    has_database: bool
    key_technologies: List[str]
    risk_factors: List[str]
    model_assignment: Dict[str, str]


class ModelAssignmentContext(BaseModel):
    model: str = ""
    calls: int = Field(0, ge=0)
    success_rate: float = Field(100.0, ge=0, le=100)


class ModelFallbackEvent(BaseModel):
    from_model: Optional[str] = None
    to_model: str
    reason: Optional[str] = None
    timestamp: Optional[str] = None


class AgentModelContextUpdate(BaseModel):
    expected_revision: int = Field(..., ge=0)
    config_version: Optional[str] = None
    roles: Optional[Dict[str, str]] = None
    current_model: Optional[str] = None
    current_agent: Optional[str] = None
    assignments: Optional[Dict[str, ModelAssignmentContext]] = None
    fallback_history: Optional[List[ModelFallbackEvent]] = Field(None, max_length=50)


class AgentModelContextResponse(BaseModel):
    found: bool
    revision: int = Field(0, ge=0)
    context: Dict[str, Any]


class ProjectSessionConfigRequest(BaseModel):
    max_sessions_per_user: int = Field(..., ge=1, le=100, description="每用户最大活跃项目会话数")


class RequirementAssociationRequest(BaseModel):
    requirement: str = Field(..., description="项目需求描述", min_length=1, max_length=5000)
    complexity_level: Optional[str] = Field(None, description="项目复杂度等级 (simple/small/medium/large/enterprise)")
    skip_association: bool = Field(False, description="是否跳过联想环节")


class RequirementAssociationConfirmRequest(BaseModel):
    association_id: int = Field(..., description="确认的联想项 ID")


class RequirementAssociationHelpfulnessRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    requirement: str = Field(..., description="原始需求描述")
    helpfulness: str = Field(..., description="整体反馈: very_helpful / somewhat_helpful / not_helpful")


class RequirementAssociationResponse(BaseModel):
    skipped: bool = False
    skip_reason: Optional[str] = None
    domain_matched: Optional[str] = None
    domains_matched: List[str] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    classified_items: Dict[str, Any] = Field(default_factory=dict)
    enhanced_requirement: Optional[str] = None
    devil_review_items: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_seconds: float = 0.0


class EvaluateRequest(BaseModel):
    requirement: str = Field(..., description="项目需求描述", min_length=1, max_length=5000)
    output_dir: Optional[str] = Field(None, description="输出目录 (可选)")
    session_id: Optional[str] = Field(None, description="会话 ID")
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token（用于从 Redis 获取用户自定义 Key）")


class EvaluateResponse(BaseModel):
    mode: str = "evaluation_only"
    requirement: str
    complexity: Dict[str, Any] = Field(default_factory=dict)
    architecture: Dict[str, Any] = Field(default_factory=dict)
    association_result: Dict[str, Any] = Field(default_factory=dict)
    requirement_evaluation: Dict[str, Any] = Field(default_factory=dict)
    architecture_evaluation: Dict[str, Any] = Field(default_factory=dict)
    risk_evaluation: Dict[str, Any] = Field(default_factory=dict)
    overall_assessment: Dict[str, Any] = Field(default_factory=dict)
    elapsed_seconds: float = 0.0
    success: bool = True
    models_used: Dict[str, str] = Field(default_factory=dict)


class TokenUsageStatsResponse(BaseModel):
    """Token 使用统计响应"""
    total_tokens: int = Field(0, description="总 token 使用量")
    prompt_tokens: int = Field(0, description="输入 token 数")
    completion_tokens: int = Field(0, description="输出 token 数")
    total_messages: int = Field(0, description="总消息数")
    today_tokens: int = Field(0, description="今日 token 使用量")
    this_month_tokens: int = Field(0, description="本月 token 使用量")
    by_model: Dict[str, int] = Field(default_factory=dict, description="按模型统计")


# ==================== 方案 3：Agent 工具 - 会话搜索 ====================

class SearchSessionsRequest(BaseModel):
    """搜索历史会话请求"""
    query: str = Field(..., description="搜索查询，用于语义匹配历史会话")
    limit: int = Field(10, ge=1, le=50, description="返回结果数量")


class SessionMatch(BaseModel):
    """匹配的会话"""
    session_id: str = Field(..., description="会话 ID")
    requirement_preview: str = Field(..., description="需求摘要")
    status: str = Field(..., description="会话状态")
    created_at: str = Field(..., description="创建时间")
    files_generated: int = Field(0, description="已生成文件数")
    files_total: int = Field(0, description="总文件数")
    relevance_score: float = Field(0.0, ge=0, le=1, description="匹配度 0-1")


class SearchSessionsResponse(BaseModel):
    """搜索会话响应"""
    query: str = Field(..., description="搜索查询")
    matches: List[SessionMatch] = Field(default_factory=list, description="匹配结果列表")
