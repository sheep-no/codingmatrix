# 安全实现概览

> 最后更新：2026-09-03

本文档描述当前代码已经接入的安全边界。核心实现位于 `app/utils/security.py`、`app/utils/encryption.py`、`app/utils/csrf.py`、`app/middleware/`、`app/api/v1/auth.py` 和 `app/utils/permissions.py`。

## 认证

- 登录、注册和刷新路径为 `/api/v1/login`、`/api/v1/register` 和 `/api/v1/refresh`。
- access token 使用 HS256 JWT，默认有效期 30 分钟，通过响应 JSON 返回。
- refresh token 使用派生自 `SECRET_KEY` 的 HS256 JWT，有效期 7 天，保存在 `HttpOnly` Cookie 中。
- access token 包含 `sub`、`exp`、`iat`、`type=access`、`refresh_until`、`permission_level` 和 `role`。
- Bearer 鉴权由 `verify_token` 提供，并要求 Token 类型为 `access`。
- WebSocket 使用 `verify_token_ws`，以关闭码区分 access token 过期、刷新窗口过期和策略拒绝。

`SECRET_KEY` 在生产环境必须显式配置且至少 16 字符。开发环境缺失时会生成进程级随机值，重启后已有 Token 随之失效。

## 密码与登录载荷

- 密码哈希使用 bcrypt，cost 为 12，并按 bcrypt 约束处理 UTF-8 编码后的前 72 字节。
- 注册密码至少 8 字符，并要求大写字母、小写字母、数字、特殊字符，同时拒绝内置常见密码列表。
- Web 前端使用 AES-256-CBC 加密登录 JSON，并使用 RSA-2048 OAEP/SHA-256 加密 AES Key。
- 后端登录端点当前兼容明文 `email` 与 `password` JSON。
- RSA 登录密钥默认从工作目录的 `keys/` 文件加载，首次缺失时生成并保存；多 worker 需要共享同一密钥卷。

详细流程见 [加密登录](ENCRYPTED-LOGIN.md)。

## CSRF

CSRF 使用 Cookie、Header 与服务端有效 Token 三重匹配：

- Cookie：`csrf_token`，JavaScript 可读，`SameSite=lax`，有效期一小时。
- Header：`X-CSRF-Token`。
- 服务端状态：当前进程内 `CSRFTokenManager`。
- 接入端点：登录、注册、刷新。

项目未注册全局 CSRF 中间件。多 worker 的进程内 Token 状态及前端注册/刷新接线差异见 [CSRF 实现](CSRF-IMPLEMENTATION.md)。

## RBAC

权限值固定为 `normal`、`admin` 和 `superadmin`。登录时从 `permission` 表读取 `permission_level` 并映射 JWT `role`：

| permission_level | JWT role | 主要用途 |
|------------------|----------|----------|
| `normal` | `user` | 已认证业务接口 |
| `admin` | `admin` | 用户、服务、监控等管理接口 |
| `superadmin` | `superadmin` | 配置、模型、MCP、Nginx 部署等高权限操作 |

路由通过 `verify_token`、`require_admin`、`require_superadmin` 或端点内 `is_admin()` 检查权限。前端展示控制只改善交互，后端依赖才是访问控制边界。详见 [权限规范](PERMISSION-SPEC.md)。

## 用户供应商 Key

- 用户 Key 先由前端使用 `/api/v1/agent/apikey/public-key` 返回的 RSA 公钥加密。
- 后端解密后将真实 Key、元数据与索引保存到 Redis，并设置 TTL。
- SQL 数据库不保存该模块的真实用户 Key。
- 每个用户最多 20 个 Key，支持启用状态、模型 context length 和降级偏好。
- Redis 必须使用受限网络、访问控制和符合部署风险的持久化策略。

动态供应商 `/api/v1/providers` 接收原始 `api_key` 字段，依赖 HTTPS 保护传输；当前管理器为进程内状态，接口实现未增加用户级记录隔离。详见 [API Key 指南](../guides/API-KEY-GUIDE.md) 与 [多供应商配置](../guides/MULTI-PROVIDER-SETUP.md)。

## HTTP 中间件

`app/main.py` 注册以下安全相关组件：

- `CORSMiddleware`：来源取自 `CORS_ORIGINS`，正则取自 `ALLOWED_HOSTS`，允许 credentials、全部方法和全部请求头。
- `RequestLoggingMiddleware`：生成请求 ID 并记录请求耗时。
- `InputValidatorMiddleware`：请求体大小及 SQL 注入/XSS 模式检查。
- `RateLimitMiddleware`：请求限流；登录另有 IP 与邮箱组合的失败尝试限流。
- `FeatureSwitchMiddleware`：按功能开关限制模块。
- `SecurityHeadersMiddleware`：统一安全响应头。
- `GZipMiddleware`：响应超过 500 字节时压缩。
- 性能监控中间件：慢请求阈值为一秒。
- draining 中间件：优雅关闭阶段返回 503 与 `Retry-After: 30`。

## 安全响应头

`SecurityHeadersMiddleware` 设置：

- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`
- `X-Permitted-Cross-Domain-Policies: none`
- `Cross-Origin-Opener-Policy: same-origin`
- 除 API docs/redoc 外的 `Cross-Origin-Embedder-Policy: require-corp`
- API 响应的 `Cache-Control: no-store, no-cache, must-revalidate, private`、`Pragma: no-cache` 和 `Expires: 0`

Swagger、ReDoc 与 OpenAPI 路径使用允许 jsDelivr 的单独 CSP。Nginx 也设置部分安全头，其中 `X-Frame-Options` 配置为 `SAMEORIGIN`；经 FastAPI 返回的响应还会携带应用层 `DENY` 值，部署时应统一策略。

## CORS 与主机配置

默认配置仅包含：

```text
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
```

`ALLOWED_HOSTS` 当前被直接转换为 CORS `allow_origin_regex`，它并非独立的 Host Header 校验中间件。生产环境应使用精确转义的来源正则，并在 Nginx 或专用中间件校验 Host。

## 文件与工作区边界

- 文件上传 API 使用认证依赖、类型/大小检查和分块写盘。
- Agent 路径输入通过项目内路径安全校验限制绝对路径、父目录穿越及敏感目标。
- VS Code Agent Host 使用工作区授权、真实路径解析、符号链接越界检查、参数数组进程执行和 `shell=false`。
- 本地验证结果回传前由 sanitizer 处理密钥、Bearer Token、密码、Cookie、私钥和连接串。

## 当前部署重点

- 生产环境使用 HTTPS，确保 Secure Cookie、登录兼容载荷和动态供应商 Key 传输得到 TLS 保护。
- 多 worker 部署前共享 RSA 密钥文件，并处理进程内 CSRF Token 和动态供应商状态共享。
- CORS 仅配置明确来源，并统一 Nginx 与应用安全头。
- Redis 作为用户 Key 和任务基础设施，应限制网络访问并启用认证。
- 健康端点检查数据库与 Redis，Celery worker 状态需要单独监控。

## 相关文档

- [加密登录](ENCRYPTED-LOGIN.md)
- [CSRF 实现](CSRF-IMPLEMENTATION.md)
- [权限规范](PERMISSION-SPEC.md)
- [服务与端口](../guides/SERVICES.md)
