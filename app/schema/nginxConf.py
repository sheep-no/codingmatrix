"""
Nginx 配置管理 Schema
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List


class NginxConf(BaseModel):
    """Nginx 配置检查请求（旧版兼容）"""
    config: str = Field(..., description="Nginx 配置文本", min_length=10)


class NginxCheck(BaseModel):
    """Nginx 配置检查请求"""
    config: str = Field(..., description="Nginx 配置文本", min_length=10)


class NginxGenerateRequest(BaseModel):
    """Nginx 配置生成请求"""
    platform: str = Field(..., description="平台：linux/windows")
    config_type: str = Field(..., description="类型：proxy/https/loadbalancer/static")
    
    # 基本配置
    server_name: str = Field(..., description="服务器名称")
    port: int = Field(..., ge=1, le=65535, description="监听端口")
    
    # SSL 配置（HTTPS 类型需要）
    ssl_cert: Optional[str] = Field(None, description="SSL 证书路径")
    ssl_key: Optional[str] = Field(None, description="SSL 私钥路径")
    
    # 代理配置
    upstream: Optional[str] = Field(None, description="代理目标 URL")
    
    # 负载均衡配置
    servers: Optional[str] = Field(None, description="后端服务器列表（逗号分隔）")
    
    # Worker 配置
    worker_processes: str = Field("auto", description="Worker 进程数")
    worker_connections: int = Field(1024, ge=1, description="最大连接数")
    
    # 高级配置
    gzip: bool = Field(True, description="启用 Gzip 压缩")
    http2: bool = Field(False, description="启用 HTTP/2")
    log_level: str = Field("warn", description="日志级别")
    
    # Nginx 安装路径
    nginx_path: Optional[str] = Field(None, description="Nginx 安装目录")
    
    @validator('server_name')
    def validate_server_name(cls, v):
        if not v or not v.strip():
            raise ValueError('服务器名称不能为空')
        return v
    
    @validator('config_type')
    def validate_config_type(cls, v):
        allowed = ['proxy', 'https', 'loadbalancer', 'static']
        if v not in allowed:
            raise ValueError(f'配置类型必须是：{", ".join(allowed)}')
        return v
    
    @validator('platform')
    def validate_platform(cls, v):
        if v not in ['linux', 'windows']:
            raise ValueError('平台必须是 linux 或 windows')
        return v


class NginxGenerateResponse(BaseModel):
    """Nginx 配置生成响应"""
    config: str = Field(..., description="生成的 Nginx 配置文本")
    path: str = Field(..., description="建议的配置文件路径")
    message: str = Field(..., description="提示信息")


class NginxDeployRequest(BaseModel):
    """Nginx 配置部署请求"""
    config: str = Field(..., description="Nginx 配置文本")
    nginx_path: str = Field("/etc/nginx", description="Nginx 安装目录")
    backup: bool = Field(True, description="是否备份现有配置")


class NginxDeployResponse(BaseModel):
    """Nginx 配置部署响应"""
    status: str = Field(..., description="状态：success/error")
    message: str = Field(..., description="提示信息")
    backup_path: Optional[str] = Field(None, description="备份文件路径")
    config_path: str = Field(..., description="配置文件路径")
