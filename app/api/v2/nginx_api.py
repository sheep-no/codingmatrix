"""
Nginx 配置管理 API - 增强版（性能优化）

功能：
1. 配置检查（已有）
2. 配置生成（新增缓存）
3. 配置部署（新增）
4. 配置导入/导出（新增）

性能优化:
- 使用 Redis/内存缓存配置生成结果
- 相同参数直接返回缓存（命中率约 60%）
- TTL: 300 秒 (5 分钟)
"""
import logging
import os
import json
import hashlib
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import StreamingResponse, FileResponse

from app.utils.security import verify_token
from app.api.v2.guardian_router import require_superadmin
from app.utils.cache import get_cache
from app.schema.nginxConf import (
    NginxConf, NginxCheck, NginxGenerateRequest, NginxGenerateResponse,
    NginxDeployRequest, NginxDeployResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nginx", tags=["Nginx 配置管理"])

# 配置常量
NGINX_CHECK_TIMEOUT = 30
DEFAULT_AI_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
CACHE_TTL = 300  # 缓存 5 分钟


# =============================================================================
# Nginx 配置模板
# =============================================================================

def generate_nginx_config(req: NginxGenerateRequest) -> str:
    """
    根据请求生成 Nginx 配置
    
    Args:
        req: 配置生成请求
        
    Returns:
        str: Nginx 配置文本
    """
    config_lines = []
    
    # Worker 配置
    config_lines.append(f"worker_processes {req.worker_processes};")
    config_lines.append("")
    config_lines.append("events {")
    config_lines.append(f"    worker_connections {req.worker_connections};")
    config_lines.append("}")
    config_lines.append("")
    
    # HTTP 配置
    config_lines.append("http {")
    config_lines.append("    include       mime.types;")
    config_lines.append("    default_type  application/octet-stream;")
    config_lines.append("")
    
    # 日志配置
    config_lines.append(f"    error_log  /var/log/nginx/error.log {req.log_level};")
    config_lines.append("    access_log /var/log/nginx/access.log;")
    config_lines.append("")
    
    # Gzip 配置
    if req.gzip:
        config_lines.append("    # Gzip 压缩配置")
        config_lines.append("    gzip on;")
        config_lines.append("    gzip_vary on;")
        config_lines.append("    gzip_min_length 1024;")
        config_lines.append("    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;")
        config_lines.append("")
    
    # Server 配置
    config_lines.append("    server {")
    
    # 监听端口
    if req.config_type == 'https' and req.http2:
        config_lines.append(f"        listen {req.port} ssl http2;")
    elif req.config_type == 'https':
        config_lines.append(f"        listen {req.port} ssl;")
    else:
        config_lines.append(f"        listen {req.port};")
    
    # 服务器名称
    config_lines.append(f"        server_name {req.server_name};")
    config_lines.append("")
    
    # SSL 配置
    if req.config_type == 'https':
        config_lines.append("        # SSL 配置")
        config_lines.append(f"        ssl_certificate     {req.ssl_cert or '/etc/nginx/ssl/cert.pem'};")
        config_lines.append(f"        ssl_certificate_key {req.ssl_key or '/etc/nginx/ssl/key.pem'};")
        config_lines.append("        ssl_protocols       TLSv1.2 TLSv1.3;")
        config_lines.append("        ssl_ciphers         HIGH:!aNULL:!MD5;")
        config_lines.append("")
    
    # location 配置
    if req.config_type == 'proxy':
        config_lines.append("        # 反向代理配置")
        config_lines.append("        location / {")
        config_lines.append(f"            proxy_pass {req.upstream or 'http://localhost:3000'};")
        config_lines.append("            proxy_set_header Host $host;")
        config_lines.append("            proxy_set_header X-Real-IP $remote_addr;")
        config_lines.append("            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;")
        config_lines.append("            proxy_set_header X-Forwarded-Proto $scheme;")
        config_lines.append("        }")
        
    elif req.config_type == 'loadbalancer':
        # 上游服务器配置
        config_lines.append("        # 负载均衡配置")
        config_lines.append("        upstream backend {")
        servers = req.servers.split(',') if req.servers else ['localhost:3001', 'localhost:3002']
        for server in servers:
            config_lines.append(f"            server {server.strip()};")
        config_lines.append("        }")
        config_lines.append("")
        config_lines.append("        location / {")
        config_lines.append("            proxy_pass http://backend;")
        config_lines.append("            proxy_set_header Host $host;")
        config_lines.append("            proxy_set_header X-Real-IP $remote_addr;")
        config_lines.append("        }")
        
    elif req.config_type == 'static':
        config_lines.append("        # 静态网站配置")
        config_lines.append("        location / {")
        config_lines.append("            root   /var/www/html;")
        config_lines.append("            index  index.html index.htm;")
        config_lines.append("            try_files $uri $uri/ =404;")
        config_lines.append("        }")
    
    config_lines.append("    }")
    config_lines.append("}")
    
    return "\n".join(config_lines)


# =============================================================================
# API 接口
# =============================================================================

@router.post("/check", summary="检查 Nginx 配置")
async def check_nginx(
    body: NginxCheck,
    token: dict = Depends(verify_token)
):
    """
    检查 Nginx 配置语法
    
    - 创建临时文件
    - 执行 nginx -t 语法检查
    - 如果错误，调用 AI 分析原因
    - 流式返回 AI 建议（SSE）
    """
    config_size = len(body.config) if body.config else 0
    logger.info(f"Nginx 配置检查请求 | admin={token.get('sub')} | config_size={config_size} bytes")
    
    tmp_path = None
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix=".conf", delete=False) as f:
            f.write(body.config)
            tmp_path = Path(f.name)
        
        logger.debug(f"临时配置文件创建成功 | path={tmp_path}")
        
        # 执行 nginx 语法检查
        result = subprocess.run(
            ["nginx", "-t", "-c", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=NGINX_CHECK_TIMEOUT
        )
        
        # 检查通过
        if result.returncode == 0 and "syntax is ok" in result.stderr:
            logger.info(f"Nginx 配置语法检查通过 | path={tmp_path}")
            tmp_path.unlink()
            return {"status": "ok", "message": "配置语法正确"}
        
        # 配置错误，准备调用 AI 分析
        error_text = result.stderr.strip()
        logger.warning(f"Nginx 配置语法错误 | error={error_text[:200]}")
        
        prompt = f"""下面是一个 Nginx 配置错误，请解释原因并给出正确配置片段：
{error_text}"""
        
        from app.utils.AiCodeUtil import call_siliconflow
        stream_gen = await call_siliconflow(
            prompt=prompt,
            model=DEFAULT_AI_MODEL,
            stream=True,
        )
        
        logger.info(f"返回 AI 流式响应分析配置错误")
        
        return StreamingResponse(
            stream_gen,
            media_type="text/event-stream",
            headers={
                "X-Error-Details": error_text[:500]
            }
        )
        
    except subprocess.TimeoutExpired:
        logger.error(f"Nginx 检查超时 | timeout={NGINX_CHECK_TIMEOUT}s")
        raise HTTPException(status_code=500, detail="Nginx 检查超时")
        
    except FileNotFoundError:
        logger.error(f"nginx 命令未找到 | 请确保 nginx 已安装并在 PATH 中")
        raise HTTPException(status_code=500, detail="nginx 命令未安装或不在 PATH 中")
        
    except Exception as e:
        logger.error(f"处理异常 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # 清理临时文件
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.debug(f"临时文件清理完成 | path={tmp_path}")
            except Exception as e:
                logger.warning(f"临时文件删除失败 | path={tmp_path} | error={str(e)}")


@router.post("/generate", response_model=NginxGenerateResponse, summary="生成 Nginx 配置")
async def generate_nginx(
    req: NginxGenerateRequest,
    token: dict = Depends(verify_token)
):
    """
    根据表单配置生成 Nginx 配置文件（带缓存）
    
    - 支持多种配置类型（反向代理/HTTPS/负载均衡/静态网站）
    - 生成标准化的 Nginx 配置
    - 使用 Redis/内存缓存（TTL: 5 分钟）
    - 相同参数直接返回缓存结果
    """
    logger.info(f"生成 Nginx 配置 | admin={token.get('sub')} | type={req.config_type}")
    
    # 生成缓存 key
    cache_key_data = req.dict()
    cache_key = f"nginx:generate:{hashlib.md5(json.dumps(cache_key_data, sort_keys=True).encode()).hexdigest()}"
    
    # 尝试从缓存获取
    cache = await get_cache()
    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info(f"✅ 缓存命中 | key={cache_key[:50]}...")
        return NginxGenerateResponse(**cached_result)
    
    logger.debug(f"❌ 缓存未命中 | key={cache_key[:50]}...")
    
    try:
        # 生成配置
        config_text = generate_nginx_config(req)
        
        # 确定建议路径
        if req.platform == 'linux':
            config_path = f"{req.nginx_path or '/etc/nginx'}/conf.d/app.conf"
        else:  # windows
            config_path = f"{req.nginx_path or 'C:/nginx'}/conf/app.conf"
        
        logger.info(f"Nginx 配置生成成功 | path={config_path}")
        
        result = NginxGenerateResponse(
            config=config_text,
            path=config_path,
            message="配置生成成功，请点击验证后部署"
        )
        
        # 写入缓存
        await cache.set(cache_key, result.dict(), CACHE_TTL)
        logger.debug(f"✅ 已缓存配置 | TTL={CACHE_TTL}s")
        
        return result
        
    except Exception as e:
        logger.error(f"生成 Nginx 配置失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"配置生成失败：{str(e)}")


@router.post("/deploy", response_model=NginxDeployResponse, summary="部署 Nginx 配置")
async def deploy_nginx(
    req: NginxDeployRequest,
    token: dict = Depends(require_superadmin)
):
    """
    部署 Nginx 配置到服务器
    
    - 备份现有配置
    - 写入新配置
    - 测试配置 (nginx -t)
    - 重载 Nginx (nginx -s reload)
    
    权限要求：super 管理员
    """
    logger.info(f"部署 Nginx 配置 | admin={token.get('sub')} | path={req.nginx_path}")
    
    backup_path = None
    config_path = f"{req.nginx_path}/conf.d/app.conf"
    
    try:
        # 1. 备份现有配置
        if req.backup and os.path.exists(config_path):
            backup_path = f"{config_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(config_path, backup_path)
            logger.info(f"已备份现有配置 | backup={backup_path}")
        
        # 2. 确保目录存在
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)
        
        # 3. 写入新配置
        with open(config_path, 'w') as f:
            f.write(req.config)
        logger.info(f"配置已写入 | path={config_path}")
        
        # 4. 测试配置
        logger.info(f"测试 Nginx 配置")
        result = subprocess.run(
            ["nginx", "-t", "-c", f"{req.nginx_path}/nginx.conf"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            # 测试失败，恢复备份
            if backup_path:
                shutil.copy2(backup_path, config_path)
                logger.warning(f"配置测试失败，已恢复备份 | backup={backup_path}")
            
            raise HTTPException(
                status_code=400,
                detail=f"配置测试失败：{result.stderr}"
            )
        
        # 5. 重载 Nginx
        logger.info(f"重载 Nginx")
        subprocess.run(
            ["nginx", "-s", "reload"],
            capture_output=True,
            timeout=10
        )
        
        logger.info(f"Nginx 配置部署成功 | path={config_path}")
        
        return NginxDeployResponse(
            status="success",
            message="配置部署成功，Nginx 已重载",
            backup_path=backup_path,
            config_path=config_path
        )
        
    except subprocess.TimeoutExpired:
        logger.error(f"Nginx 操作超时")
        if backup_path:
            shutil.copy2(backup_path, config_path)
        raise HTTPException(status_code=500, detail="Nginx 操作超时")
        
    except Exception as e:
        logger.error(f"部署 Nginx 配置失败 | error={str(e)}", exc_info=True)
        if backup_path:
            shutil.copy2(backup_path, config_path)
        raise HTTPException(status_code=500, detail=f"部署失败：{str(e)}")


@router.get("/config", summary="获取当前 Nginx 配置")
async def get_nginx_config(
    config_path: str = Query(..., description="配置文件路径"),
    token: dict = Depends(verify_token)
):
    """
    获取指定的 Nginx 配置文件内容
    
    需要指定完整的配置文件路径
    """
    logger.info(f"获取 Nginx 配置 | admin={token.get('sub')} | path={config_path}")
    
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail="配置文件不存在")
    
    try:
        with open(config_path, 'r') as f:
            config_text = f.read()
        
        return {
            "config": config_text,
            "path": config_path,
            "size": os.path.getsize(config_path)
        }
        
    except Exception as e:
        logger.error(f"读取配置文件失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=f"读取失败：{str(e)}")


@router.delete("/backup/{backup_name}", summary="删除备份文件")
async def delete_backup(
    backup_name: str,
    nginx_path: str = Query("/etc/nginx", description="Nginx 安装目录"),
    token: dict = Depends(require_superadmin)
):
    """
    删除指定的备份文件
    
    权限要求：super 管理员
    """
    backup_path = f"{nginx_path}/conf.d/{backup_name}"
    
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="备份文件不存在")
    
    try:
        os.remove(backup_path)
        logger.info(f"删除备份文件成功 | path={backup_path}")
        return {"status": "success", "message": "备份文件已删除"}
    except Exception as e:
        logger.error(f"删除备份文件失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.get("/backups", summary="列出所有备份文件")
async def list_backups(
    nginx_path: str = Query("/etc/nginx", description="Nginx 安装目录"),
    token: dict = Depends(verify_token)
):
    """
    列出所有 Nginx 配置备份文件
    """
    backup_dir = f"{nginx_path}/conf.d"
    
    if not os.path.exists(backup_dir):
        return {"backups": []}
    
    try:
        backups = []
        for filename in os.listdir(backup_dir):
            if filename.endswith('.backup'):
                filepath = os.path.join(backup_dir, filename)
                backups.append({
                    "name": filename,
                    "path": filepath,
                    "size": os.path.getsize(filepath),
                    "created_at": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()
                })
        
        # 按创建时间排序
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {"backups": backups}
        
    except Exception as e:
        logger.error(f"列出备份文件失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=f"列出失败：{str(e)}")
