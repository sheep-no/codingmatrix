import uvicorn
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# 初始化FastAPI应用
app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模拟数据库配置
DB_CONFIG = {
    "database": "blogcms.db",
    "tables": {
        "users": None,
        "roles": None,
        "categories": None,
        "articles": None,
        "comments": None,
        "settings": None
    }
}

# 模拟环境变量配置
ENV_CONFIG = {
    "API_KEY": "your_api_key_here",
    "DEBUG": "False",
    "JWT_SECRET_KEY": "your_jwt_secret_key_here",
    "REFRESH_TOKEN_EXPIRATION": "30d",
    "ACCESS_TOKEN_EXPIRATION": "15m",
    "SERVER_HOST": "localhost",
    "SERVER_PORT": 8000,
    "ENVIRONMENT": "development"
}

@app.get("/")
async def root():
    """返回系统信息"""
    return {
        "status": "success",
        "message": "Blog CMS API is running",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/info")
async def api_info():
    """返回API信息"""
    return {
        "status": "success",
        "message": "API endpoint information",
        "endpoints": [
            {"path": "/", "method": "GET", "description": "Root endpoint"},
            {"path": "/api/auth/register", "method": "POST", "description": "User registration"},
            {"path": "/api/auth/login", "method": "POST", "description": "User login"},
            {"path": "/api/articles", "method": "GET", "description": "Get articles"},
            {"path": "/api/categories", "method": "GET", "description": "Get categories"}
        ],
        "environment": ENV_CONFIG["ENVIRONMENT"],
        "debug": ENV_CONFIG["DEBUG"] == "True",
        "server": {
            "host": ENV_CONFIG["SERVER_HOST"],
            "port": ENV_CONFIG["SERVER_PORT"]
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/auth/health")
async def auth_health():
    """返回认证系统健康状态"""
    return {
        "status": "success",
        "message": "Authentication service is healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/db/health")
async def db_health():
    """返回数据库健康状态"""
    return {
        "status": "success",
        "message": "Database service is healthy",
        "connection_string": DB_CONFIG["database"],
        "timestamp": datetime.utcnow().isoformat()
    }

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    """自定义404错误处理"""
    return {
        "status": "error",
        "code": 404,
        "message": f"Endpoint not found: {request.url.path}",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc: HTTPException):
    """自定义500错误处理"""
    return {
        "status": "error",
        "code": 500,
        "message": "Internal server error",
        "details": str(exc),
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    # 获取环境变量
    host = ENV_CONFIG["SERVER_HOST"]
    port = int(ENV_CONFIG["SERVER_PORT"])
    
    # 启动开发服务器
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=ENV_CONFIG["DEBUG"] == "True",
        workers=1
    )