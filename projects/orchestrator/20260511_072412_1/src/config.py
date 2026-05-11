# src/config.py
from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # General Settings
    PROJECT_NAME: str = "FastAPI REST API Service"
    PROJECT_VERSION: str = "1.0.0"
    DESCRIPTION: str = "RESTful API service with user management, authentication, and data CRUD operations"
    
    # Security Settings
    SECRET_KEY: str = "your-secret-key-here"  # Should be stored in environment variables
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # Database Settings
    DB_DRIVER: str = "postgresql+psycopg2"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "fastapi_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    
    # CORS Settings
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "*"  # In production, restrict to your frontend domain
    ]
    ALLOWED_METHODS: list[str] = ["*"]
    ALLOWED_HEADERS: list[str] = ["*"]
    
    # Pagination Settings
    PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100
    
    # Email Settings (if authentication via email is needed)
    EMAIL_ENABLED: bool = False
    EMAIL_HOST: str = ""
    EMAIL_PORT: int = 587
    EMAIL_SERVER: str = ""
    EMAIL_FROM: str = ""
    
    # Testing Settings
    TESTING: bool = False
    
    # Rate Limiting
    RATE_LIMIT_MAX: int = 50
    RATE_LIMIT_WINDOW: int = 60  # In seconds
    
    # Logging
    LOG_LEVEL: str = "info"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"

# Create configuration instance
settings = Settings()

# Database connection string
SQLALCHEMY_DATABASE_URL = (
    f"{settings.DB_DRIVER}://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

# OpenAPI documentation settings
OPENAPI_URL: str = "/openapi.json"
OPENAPI_TAG_NAME: str = "tag"
OPENAPI_TAG_DESCRIPTION: str = "Description"

# API prefix
API_V1_STR: str = "/api/v1"