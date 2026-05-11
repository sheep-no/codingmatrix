# 生产就绪指南

## 概述

本指南帮助将 CodingMatrix 从开发环境部署到生产环境。

## 生产清单

### 安全
- [x] 设置强 SECRET_KEY
- [x] 配置 SILICONFLOW_API_KEY
- [x] 启用 HTTPS (反向代理)
- [x] 配置 CORS 允许域名
- [x] 启用 CSRF 防护
- [x] 配置限流策略

### 性能
- [x] 使用多 worker 启动 uvicorn
- [x] 配置 Redis 缓存
- [x] 启用日志轮转
- [x] 数据库连接池优化

### 监控
- [x] 健康检查端点就绪
- [x] Prometheus 指标暴露
- [x] 结构化日志输出
- [x] 系统监控面板

### 备份
- [x] 定期备份 SQLite 数据库
- [x] 备份上传文件
- [x] 备份配置

## 启动命令 (生产)

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
```

## Nginx 反向代理

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 健康检查

```bash
curl -f http://localhost:8000/api/v1/health/live
```

预期响应:
```json
{"status": "alive"}
```
