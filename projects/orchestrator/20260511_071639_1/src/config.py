import os
from pydantic import BaseModel

class Settings(BaseModel):
    # API 配置
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "FastAPI REST API Service"
    
    # 服务器配置
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "info"
    
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./test.db"
    DATABASE_ECHO: bool = False
    
    # 密码配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "mysecretkey")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 一天
    
    # 认证配置
    JWT_SECRET: str = os.getenv("JWT_SECRET", "jwtsecret")
    
    # 邮件配置
    EMAIL_BACKEND: str = "smtp"
    EMAIL_HOST: str = "smtp.example.com"
    EMAIL_PORT: int = 587
    EMAIL_USE_TLS: bool = True
    EMAIL_HOST_USER: str = "user@example.com"
    EMAIL_HOST_PASSWORD: str = "password"
    
    # 速率限制
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_PERIOD: int = 60
    
    # 静态文件配置
    STATIC_DIR: str = "static"
    MEDIA_DIR: str = "media"
    
    # OpenAPI 配置
    OPENAPI_URL: str = f"{API_V1_STR}/openapi.json"

    # 模型配置
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()