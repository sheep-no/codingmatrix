from pathlib import Path
import os
import secrets

from pydantic import Field, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

BASE_DIR = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENV: str = "development"

    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/app.db"

    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 10
    DB_POOL_RECYCLE: int = 1800

    REDIS_URL: str = ""

    LOG_LEVEL: str = "INFO"
    LOG_RETENTION_DAYS: int = 30
    LOG_COMPRESS_OLD_LOGS: bool = True
    LOG_CLEANUP_SCHEDULE: str = "weekly"

    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v):
        if not v:
            # 开发环境自动生成临时密钥，生产环境必须设置
            if os.getenv("ENV", "development") == "production":
                raise ValueError("生产环境必须设置 SECRET_KEY")
            return secrets.token_hex(32)
        if len(v) < 16:
            raise ValueError("SECRET_KEY 长度不能小于 16 字符")
        return v

    @field_validator("DB_POOL_SIZE")
    @classmethod
    def validate_db_pool_size(cls, v):
        if v < 1:
            raise ValueError("DB_POOL_SIZE 必须 >= 1")
        if v > 100:
            raise ValueError("DB_POOL_SIZE 不能超过 100")
        return v

    @field_validator("DB_MAX_OVERFLOW")
    @classmethod
    def validate_db_max_overflow(cls, v):
        if v < 0:
            raise ValueError("DB_MAX_OVERFLOW 必须 >= 0")
        return v

    SILICONFLOW_API_KEY: str = ""
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"

    # 多供应商支持
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    ZHIPU_API_KEY: str = ""
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    ALLOWED_MODELS: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B,deepseek-ai/DeepSeek-OCR,Qwen/Qwen3.5-4B,Qwen/Qwen3-8B,Qwen/Qwen2.5-7B-Instruct,BAAI/bge-m3,BAAI/bge-reranker-v2-m3,Kwai-Kolors/Kolors,THUDM/GLM-4-9B-0414,THUDM/GLM-Z1-9B-0414,BAAI/bge-large-zh-v1.5,PaddlePaddle/PaddleOCR-VL-1.5,XingChenAGI/XingChenASR-V3.2-Ultra,XingChenAGI/XingChenGSR-V1.0,XingChenAGI/XingChenASR-Diarize-V3.0,FunAudioLLM/SenseVoiceSmall,TeleAI/TeleSpeechASR,tencent/Hunyuan-MT-7B"

    ALLOWED_HOSTS: str = "localhost,127.0.0.1,0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    MAX_UPLOAD_SIZE_MB: int = 100
    MAX_ACTIVE_REQUESTS: int = 100
    ALLOWED_FILE_TYPES: str = "image,document,code,archive"

    WS_MAX_CONNECTIONS: int = 50

    # 项目生成会话限制（默认 2 = 允许 2 个并发会话，管理员可通过环境变量调整）
    MAX_PROJECT_SESSIONS_PER_USER: int = 2

    # ==================== Agent 行为配置（P1） ====================

    # Agent 自动修复最大重试次数
    MAX_RETRY_LOOPS: int = 3

    # 自动确认阈值（测试通过率 >= 此值时自动确认）
    AUTO_CONFIRM_THRESHOLD: float = 0.8

    # Agent 是否启用影响分析（修改类任务强制查依赖图谱）
    ENABLE_IMPACT_ANALYSIS: bool = True

    # Agent 是否启用多角度审查
    ENABLE_MULTI_REVIEW: bool = True

    # Agent 是否启用反面自查（修改后自动检查常见错误模式）
    ENABLE_ANTI_PATTERN_CHECK: bool = True

    # 代码沙箱配置（工程师可在生成后验证代码）
    ENABLE_CODE_SANDBOX: bool = True  # 是否启用代码沙箱
    SANDBOX_LANGUAGES: str = "python,javascript"  # 支持沙箱的语言，逗号分隔

    # Agent 是否启用关键词触发追问
    ENABLE_KEYWORD_TRIGGERS: bool = True

    # 依赖图谱路径
    DEPENDENCY_GRAPH_PATH: str = "data/dependency_graph.json"

    # 文件到测试映射路径
    FILE_TO_TEST_MAP_PATH: str = "configs/file_to_test_map.yaml"

    # 规格书模板路径
    SPEC_TEMPLATE_PATH: str = "configs/spec_template.yaml"

    # 关键词触发配置路径
    KEYWORD_TRIGGERS_PATH: str = "configs/keyword_triggers.yaml"

    # 常见错误模式库路径
    ANTI_PATTERNS_PATH: str = "configs/anti_patterns.yaml"

    # 审查清单路径
    REVIEW_CHECKLIST_PATH: str = "configs/review_checklist.yaml"

    @property
    def max_upload_size_mb(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB
    
    def get_provider_registry(self) -> "ProviderRegistry":
        """从配置构建供应商注册表"""
        from app.utils.aicloud.providers import ModelProvider, ProviderConfig, ProviderRegistry
        
        registry = ProviderRegistry()
        
        provider_configs = [
            (ModelProvider.SILICONFLOW, self.SILICONFLOW_API_KEY, self.SILICONFLOW_BASE_URL),
            (ModelProvider.DASHSCOPE, self.DASHSCOPE_API_KEY, self.DASHSCOPE_BASE_URL),
            (ModelProvider.ZHIPU, self.ZHIPU_API_KEY, self.ZHIPU_BASE_URL),
            (ModelProvider.DEEPSEEK, self.DEEPSEEK_API_KEY, self.DEEPSEEK_BASE_URL),
            (ModelProvider.OPENAI, self.OPENAI_API_KEY, self.OPENAI_BASE_URL),
            (ModelProvider.ANTHROPIC, self.ANTHROPIC_API_KEY, self.ANTHROPIC_BASE_URL),
            (ModelProvider.OLLAMA, "", self.OLLAMA_BASE_URL),
        ]
        
        for provider, api_key, base_url in provider_configs:
            config = ProviderConfig(
                provider=provider,
                api_key=api_key,
                base_url=base_url,
            )
            registry.register(config)
        
        return registry


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
