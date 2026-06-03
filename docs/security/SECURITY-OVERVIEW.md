# 安全架构概览

> 最后更新: 2026-06-02 | 状态: 生产就绪 | 版本: v5.12.0+

## v5.12.0+ 安全更新

### 1. 代码沙箱 (Code Sandbox)

v5.12.0+ 新增可配置的代码沙箱系统，用于在 ReAct 工具调用中安全执行任意代码。

#### 支持的沙箱

| 语言 | 实现方式 | 限制 |
|------|----------|------|
| Python | AST 静态分析 + 限制性 builtins | exec/eval/compile/__import__/open/getattr/setattr 全部禁止 |
| JavaScript | Node.js 子进程 + 危险模式拦截 | child_process/fs/eval/Function/process.exit/process.env 全部禁止 |

#### 安全特性

- **AST 静态分析**（Python）：执行前解析语法树，拦截危险节点
- **危险模式黑名单**（JavaScript）：正则匹配代码，禁止危险 API
- **超时控制**：30 秒硬超时，防止死循环
- **进程隔离**：JavaScript 使用独立子进程，崩溃不影响主进程
- **管理员可控**：`ENABLE_CODE_SANDBOX` 和 `SANDBOX_LANGUAGES` 可通过 API 动态配置

#### API 端点

```http
GET /api/v2/admin/sandbox-config
PUT /api/v2/admin/sandbox-config
```

请求体：
```json
{
  "enable_code_sandbox": true,
  "sandbox_languages": "python,javascript"
}
```

详见 [REACT-TOOL-CALLING.md#代码沙箱](../features/REACT-TOOL-CALLING.md#代码沙箱)

### 2. Engineer 写入工具安全审计

v5.12.0+ 工程师获得 4 个写入/验证工具（`partial_update` / `insert_content` / `regex_replace` / `execute_code`），需要额外的安全约束：

#### 文件路径验证

- 工程师只能修改工作目录内的文件
- 路径遍历攻击防护（`../` 拦截）
- 文件大小限制（默认 1MB）

#### Git Stash 原子回滚

- 每次编辑前自动 `git stash` 备份
- 失败时自动 `git stash pop` 还原
- 成功时 `git stash drop` 清理
- 新文件失败时直接 `unlink()` 删除

详见 [REACT-TOOL-CALLING.md#git-stash-原子回滚](../features/REACT-TOOL-CALLING.md#git-stash-原子回滚)

### 3. 会话并发限制加固

v5.12.0+ 实施严格的并发限制：

- `MAX_PROJECT_SESSIONS_PER_USER = 2`：每个用户最多 2 个活跃项目会话
- 超出时返回 409 响应，包含活跃会话列表
- 僵尸会话自动检测并清理（防资源泄漏）

详见 [SESSION-LIFECYCLE.md#并发限制429-响应](../features/SESSION-LIFECYCLE.md#并发限制429-响应)

### 4. API Key context_length 多级保护

v5.12.0+ 用户 API Key 支持自定义 context_length，需注意：

- 用户自定义 context_length 仅对自己的请求生效
- 管理员配置的 context_length 全局生效
- 用户提交 OpenAI/Anthropic Key 时自动同步模型列表

详见 [MODELS.md#context_length-管理](../architecture/MODELS.md#context_length-管理)

---

## 认证与授权

### JWT 认证
- **Access Token**: 短期有效 (30 分钟)
- **Refresh Token**: 长期有效 (7 天)
- **Token 轮换**: 刷新时生成新的 Refresh Token，旧的失效
- **Cookie 存储**: HttpOnly + Secure + SameSite=lax

### 密码安全
- **RSA-OAEP 加密**: 前端使用后端公钥加密密码后再传输
- **bcrypt 哈希**: 后端存储密码使用 bcrypt 算法 (rounds=12)

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

### API Key 安全 (v5.9.0)

#### RSA-2048 加密传输

用户 API Key 使用 RSA-2048 加密传输：

1. 前端获取后端 RSA 公钥
2. 使用公钥加密 API Key
3. 加密后的 Token 存储在 Redis 中
4. Token 有 TTL，自动过期

#### Redis 内存存储

```python
# 存储结构
api_key_token = {
 "user_id": "user-uuid",
 "encrypted_key": "RSA-encrypted-api-key",
 "created_at": "2026-05-26T10:00:00Z",
 "expires_at": "2026-05-26T18:00:00Z"  # 8 小时过期
}
```

#### Token 使用统计

```python
# 从 chat_histories 表查询
token_usage = {
 "today": {"prompt_tokens": 1000, "completion_tokens": 2000},
 "this_month": {"prompt_tokens": 50000, "completion_tokens": 100000},
 "total": {"prompt_tokens": 200000, "completion_tokens": 400000},
 "by_model": {
   "glm-z1-9b": {"prompt_tokens": 5000, "completion_tokens": 10000},
   "deepseek-r1": {"prompt_tokens": 3000, "completion_tokens": 8000}
 }
}
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

## 输入验证

CodingMatrix 遵循 OWASP Top 10 安全最佳实践。

### 验证机制
- **Pydantic Schema**: 严格类型验证
- **SQL 参数化查询**: 防注入
- **文件上传限制**: 类型/大小限制
- **路径遍历防护**: 防止目录穿越

### 安全端点

| 端点 | 描述 |
|------|------|
| GET /api/v1/public-key | 获取 RSA 公钥 |
| GET /api/v1/csrf-token | 获取 CSRF Token |
| POST /api/v1/vision/check-safety | 图像安全检查 |

### 服务保护
- **熔断器**: 防止服务雪崩
- **超时控制**: 防止请求 hang 住
- **资源限制**: CPU/内存使用限制

## 安全建议

1. 定期更新依赖 (运行 `pip audit`)
2. 定期轮换 SECRET_KEY
3. 监控异常访问模式
4. 保持 HTTPS 始终开启
