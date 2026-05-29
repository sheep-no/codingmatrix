# 生产部署指南

Docker 部署、性能优化、监控配置、备份策略。

## Docker 部署

### docker-compose.yml

```yaml
version: '3.8'

services:
 backend:
 build: .
 ports:
 - "8080:8080"
 environment:
 - DATABASE_URL=sqlite+aiosqlite:///app/data.db
 - SECRET_KEY=your-secret-key
 - OTEL_ENABLED=1
 - OTEL_EXPORTER_JAEGER_ENDPOINT=http://jaeger:14268/api/traces
 volumes:
 - ./data:/app/data
 depends_on:
 - jaeger

 frontend:
 build: ./src
 ports:
 - "80:80"
 depends_on:
 - backend

 jaeger:
 image: jaegertracing/all-in-one:1.52
 ports:
 - "16686:16686" # UI
 - "14268:14268" # HTTP
 - "14250:14250" # gRPC
 environment:
 - COLLECTOR_OTLP_ENABLED=true
```

### 构建镜像

```bash
# 后端
docker build -t codingmatrix-backend .

# 前端
docker build -t codingmatrix-frontend ./src
```

### 启动服务

```bash
docker compose up -d
```

### 查看日志

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

## 性能优化

### 后端优化

1. **数据库连接池**

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
 DATABASE_URL,
 pool_size=10,
 max_overflow=20,
 pool_pre_ping=True
)
```

2. **缓存策略**

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_config(key: str) -> str:
 return config[key]
```

3. **异步 IO**

```python
async def fetch_data():
 async with aiohttp.ClientSession() as session:
 async with session.get(url) as response:
 return await response.json()
```

### 前端优化

1. **代码分割**

```javascript
// 懒加载路由
const routes = [
 {
 path: '/agent',
 component: () => import('@/views/Agent.vue')
 }
]
```

2. **资源压缩**

```javascript
// vite.config.js
export default {
 build: {
 minify: 'terser',
 terserOptions: {
 compress: {
 drop_console: true,
 drop_debugger: true
 }
 }
 }
}
```

3. **CDN 加速**

```javascript
// 使用 CDN 加载第三方库
export default {
 build: {
 rollupOptions: {
 external: ['vue', 'vue-router', 'pinia'],
 output: {
 globals: {
 vue: 'Vue',
 'vue-router': 'VueRouter',
 pinia: 'Pinia'
 }
 }
 }
 }
}
```

## 监控配置

### 健康检查

```bash
# 存活检查
curl http://localhost:8080/health/live

# 就绪检查
curl http://localhost:8080/health/ready

# Prometheus 指标
curl http://localhost:8080/metrics
```

### 日志收集

```yaml
# logging.yaml
version: 1
handlers:
 file:
 class: logging.handlers.RotatingFileHandler
 filename: app/logs/app.log
 maxBytes: 10485760 # 10MB
 backupCount: 10
 formatter: json
 console:
 class: logging.StreamHandler
 formatter: json
```

### 告警配置

```yaml
# alerting.yaml
rules:
 - alert: HighErrorRate
 expr: rate(http_requests_total{status="5xx"}[5m]) > 0.1
 for: 5m
 labels:
 severity: critical
 annotations:
 summary: "高错误率"
 description: "5 分钟内错误率超过 10%"
```

## 备份策略

### 数据库备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# SQLite 备份
cp app/data.db ${BACKUP_DIR}/data_${DATE}.db

# 压缩
tar -czf ${BACKUP_DIR}/data_${DATE}.tar.gz ${BACKUP_DIR}/data_${DATE}.db

# 清理旧备份（保留 7 天）
find ${BACKUP_DIR} -name "data_*.tar.gz" -mtime +7 -delete
```

### 日志轮转

```bash
#!/bin/bash
# log-rotate.sh

LOG_DIR="app/logs"
DATE=$(date +%Y%m%d)

# 移动日志
mv ${LOG_DIR}/app.log ${LOG_DIR}/app_${DATE}.log

# 压缩
gzip ${LOG_DIR}/app_${DATE}.log

# 清理旧日志（保留 30 天）
find ${LOG_DIR} -name "app_*.log.gz" -mtime +30 -delete
```

## 安全加固

### 防火墙配置

```bash
# 允许 HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# 允许 SSH
ufw allow 22/tcp

# 启用防火墙
ufw enable
```

### SSL/TLS 配置

```nginx
server {
 listen 443 ssl;
 server_name your-domain.com;

 ssl_certificate /etc/ssl/certs/cert.pem;
 ssl_certificate_key /etc/ssl/private/key.pem;

 ssl_protocols TLSv1.2 TLSv1.3;
 ssl_ciphers HIGH:!aNULL:!MD5;

 location / {
 proxy_pass http://localhost:80;
 }
}
```

### 定期安全审计

```bash
# 后端
pip-audit -r configs/requirements.txt

# 前端
npm audit

# 系统
lynis audit system
```

## 相关文档

- [文档首页](../README.md) - 文档导航
- [安全架构](../security/SECURITY-OVERVIEW.md) - 安全架构
- [分布式追踪](../observability/TRACING.md) - 分布式追踪
