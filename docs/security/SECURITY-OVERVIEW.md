# 安全架构概览

> 最后更新: 2026-05-11 | 状态: 生产就绪

## 认证与授权

### JWT 认证
- **Access Token**: 短期有效 (15 分钟)
- **Refresh Token**: 长期有效 (7 天)
- **Token 轮换**: 刷新时生成新的 Refresh Token，旧的失效
- **Cookie 存储**: HttpOnly + Secure + SameSite=Strict

### 密码安全
- **RSA-OAEP 加密**: 前端使用后端公钥加密密码后再传输
- **Argon2id 哈希**: 后端存储密码使用 Argon2id 算法
- **参数配置**: `time_cost=3, memory_cost=65536, parallelism=4`

### 三级权限系统

| 级别 | 角色 | 权限范围 |
|------|------|----------|
| 0 | normal | 基础 AI 功能 (代码生成、项目生成、图像生成等) |
| 1 | admin | 用户管理、服务管理、基础系统监控 |
| 2 | super | Nginx 配置、系统配置、限流管理 |
| 3 | superadmin | 并发限制动态配置、最高权限 |

### 权限装饰器
```python
@require_role(Role.SUPERADMIN)
async def handler(request):
    pass

@require_role(Role.ADMIN, Role.SUPERADMIN)
async def handler(request):
    pass
```

## 网络安全

### CSRF 防护
- **Double-submit Cookie 模式**
- **X-CSRFToken 头部**: 前端在请求中携带 CSRF Token
- **SameSite Cookie**: Strict 模式防止跨站请求

### 速率限制
- **全局限流**: 所有请求统一限流
- **IP 限流**: 基于 IP 地址的请求频率控制
- **用户限流**: 基于用户 ID 的请求频率控制
- **端点限流**: 针对特定 API 端点的限流
- **动态配置**: 通过 `/api/v2` 管理界面实时调整

### 并发限制
- **用户级并发**: 每个用户同时进行的请求数限制
- **JSON 配置**: `data/concurrency_config.json`
- **API 管理**: `POST /api/v2/admin/user-limit` 动态配置

## 数据安全

### 传输加密
- **HTTPS**: 生产环境强制 HTTPS
- **RSA-OAEP**: 密码传输加密
- **AES-CBC**: 敏感数据传输加密

### 存储安全
- **密码哈希**: Argon2id
- **Token 安全**: HttpOnly + Secure Cookie
- **文件加密**: 上传文件可选加密存储

### XSS 防护
- **CSP**: Content-Security-Policy 头部
- **DOMPurify**: 前端 HTML 内容清理
- **转义输出**: 所有用户输入在输出时转义

## 中间件安全链

```
Request → LogMiddleware (请求日志)
        → SecurityMiddleware (安全头部)
        → CORSMiddleware (跨域控制)
        → CSRFMiddleware (CSRF 验证)
        → RateLimitMiddleware (速率限制)
        → JWTMiddleware (认证)
        → ConcurrencyLimitMiddleware (并发限制)
        → Route Handler
```

### SecurityMiddleware 设置的头部

| 头部 | 值 | 说明 |
|------|-----|------|
| X-Content-Type-Options | nosniff | 防止 MIME 类型嗅探 |
| X-Frame-Options | DENY | 禁止 iframe 嵌入 |
| X-XSS-Protection | 1; mode=block | 浏览器 XSS 防护 |
| Referrer-Policy | strict-origin-when-cross-origin | 引用策略 |
| Permissions-Policy | camera=(), microphone=() | 权限策略 |

## 文件上传安全

### 验证机制
- **MIME 类型检查**: 验证文件真实类型
- **扩展名白名单**: 只允许安全的文件扩展名
- **大小限制**: 最大上传文件大小可配置
- **病毒扫描**: 可选的病毒扫描集成

### 存储安全
- **随机文件名**: 避免文件名冲突和路径遍历
- **权限控制**: 文件访问需要相应权限
- **隔离存储**: 不同用户的文件隔离存储

## 审计与监控

### 审计日志
- **操作记录**: 所有管理操作记录日志
- **登录日志**: 所有登录尝试记录
- **文件操作**: 文件上传/删除记录

### 系统监控
- **健康检查**: `/api/v1/health` 端点
- **Prometheus 指标**: `/api/v1/health/metrics`
- **实时统计**: WebSocket 推送系统统计

## 安全最佳实践

### 开发时
1. 不要硬编码密钥或密码
2. 使用环境变量管理敏感配置
3. 遵循最小权限原则
4. 所有用户输入都要验证

### 部署时
1. 使用 HTTPS
2. 配置防火墙规则
3. 定期更新依赖
4. 启用安全监控

### 运维时
1. 定期审查审计日志
2. 监控异常请求模式
3. 及时更新安全策略
4. 定期备份数据
