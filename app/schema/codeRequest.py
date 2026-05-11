from pydantic import BaseModel, field_validator, Field
from typing import Optional, List, Dict, Any
import re


# AI Code 可用模型（代码问答/生成/视觉理解）
ALLOWED_MODELS_LIST = [
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "deepseek-ai/DeepSeek-OCR",
    "Qwen/Qwen3.5-4B",
    "Qwen/Qwen3-8B",
    "Qwen/Qwen2.5-7B-Instruct",
    "THUDM/GLM-4.1V-9B-Thinking",
    "THUDM/GLM-4-9B-0414",
    "THUDM/GLM-Z1-9B-0414",
]


class CodeRequest(BaseModel):
    """代码生成请求"""
    prompt: str = Field(..., description="代码生成需求描述")
    model: Optional[str] = Field(None, description="指定模型（不指定则自动选择）")
    stream: Optional[bool] = Field(False, description="是否流式输出")
    use_reasoning: Optional[bool] = Field(False, description="是否启用深度推理")
    conversation_id: Optional[str] = Field(None, description="会话 ID")

    # 联网搜索配置
    enable_search: Optional[bool] = Field(None, description="是否允许联网搜索（True=允许，False=禁止，None=AI 自主决定）")
    search_count: Optional[int] = Field(5, description="搜索结果数量")
    search_timelimit: Optional[str] = Field(None, description="搜索时间范围（如'week', 'month'）")

    # 图片理解配置（UI 截图转代码等）
    enable_vision: Optional[bool] = Field(False, description="是否启用图片理解")
    image_path: Optional[str] = Field(None, description="已上传图片的路径（相对路径或文件 ID）")
    image_analysis_prompt: Optional[str] = Field("请分析这张 UI 设计图，说明界面类型，主要组件、布局结构和技术实现建议", description="图片分析提示词")


class ProjectRequest(BaseModel):
    """项目生成请求"""
    prompt: str


class FullstackRequest(BaseModel):
    """全栈项目请求"""
    requirement: str


class GenerateRequest(BaseModel):
    """项目生成请求（支持 Docker 配置）"""
    requirement: str = Field(..., description="项目需求描述（自然语言）")
    session_id: str = Field(..., description="会话 ID（用于文件锁隔离）")
    conversation_id: Optional[int] = Field(None, description="对话上下文 ID（可选，用于携带历史）")

    # 验证配置
    enable_venv_validation: bool = Field(default=False, description="是否启用 venv 隔离验证（已废弃，请使用 Docker）")
    enable_docker_validation: bool = Field(default=True, description="是否启用 Docker 容器化验证")
    docker_network_enabled: bool = Field(default=False, description="Docker 容器是否启用网络（默认禁用，更安全）")
    docker_cpu_limit: float = Field(default=2.0, ge=0.5, le=8.0, description="Docker CPU 核心数限制")
    docker_memory_limit: str = Field(default="2g", description="Docker 内存限制")
    docker_timeout: int = Field(default=300, ge=60, le=1800, description="Docker 运行超时 (秒)")
    enable_security_scan: bool = Field(default=True, description="是否启用安全扫描")

    model: str = Field(default="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", description="模型名称")
    max_thinking_tokens: int = Field(default=8192, description="最大思考 Token 数")
    max_output_tokens: int = Field(default=32768, description="最大输出 Token 数")
    temperature: float = Field(default=0.7, description="采样温度", ge=0.0, le=2.0)

    @field_validator('model')
    @classmethod
    def validate_model(cls, v):
        if v not in ALLOWED_MODELS_LIST:
            raise ValueError(f"model must be one of {ALLOWED_MODELS_LIST}, got '{v}'")
        return v


class GenerateResponse(BaseModel):
    """项目生成响应"""
    success: bool
    output_dir: str
    total_files_created: int
    steps: list
    validation: dict


class AgentConfig(BaseModel):
    """Agent 配置模型（支持 Docker 容器化验证）"""
    model: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    max_thinking_tokens: int = 8192
    max_output_tokens: int = 128000
    temperature: float = 0.1
    timeout: float = 600.0
    stream: bool = False
    enable_validation: bool = True
    enable_runtime_validation: bool = False
    auto_install_deps: bool = True
    enable_venv_validation: bool = True

    # Docker 容器化验证配置
    enable_docker_validation: bool = True
    docker_network_enabled: bool = False
    docker_cpu_limit: float = 2.0
    docker_memory_limit: str = "2g"
    docker_timeout: int = 300
    enable_security_scan: bool = True

    shared_base_venv: Optional[str] = None
    max_concurrent_validations: int = 3
    allowed_packages: Optional[List[str]] = None
    validation_level: str = "strict"
    runtime_validation_timeout: int = 10

    ALLOWED_MODELS: List[str] = ALLOWED_MODELS_LIST

    @field_validator('model')
    @classmethod
    def validate_model(cls, v):
        if v not in ALLOWED_MODELS_LIST:
            raise ValueError(f"model must be one of {ALLOWED_MODELS_LIST}, got '{v}'")
        return v

    @field_validator('temperature')
    @classmethod
    def validate_temp(cls, v):
        return max(0.0, min(2.0, float(v)))

    @field_validator('validation_level')
    @classmethod
    def validate_validation_level(cls, v):
        allowed_levels = ["basic", "standard", "strict"]
        if v not in allowed_levels:
            raise ValueError(f"validation_level must be one of {allowed_levels}, got '{v}'")
        return v

    @field_validator('enable_docker_validation')
    @classmethod
    def validate_docker_enabled(cls, v):
        if v:
            try:
                import docker
                client = docker.from_env()
                client.ping()
            except Exception:
                return False
        return v


class ToolDefinition(BaseModel):
    """工具定义模型"""
    name: str
    func: any
    description: str
    parameters: type

    model_config = {"arbitrary_types_allowed": True}
