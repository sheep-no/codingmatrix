# 安全优先指南

## 概述

CodingMatrix 遵循 OWASP Top 10 安全最佳实践。

## 已实施的安全措施

### 1. 认证与授权
- JWT Token 认证 (包含 role 字段)
- RSA-OAEP 加密密码传输
- 三级 RBAC 权限模型 (normal/admin/super)
- Token 角色映射 (user/admin/superadmin)
- Token 过期自动刷新

### 2. CSRF 防护
- Double-submit Cookie 模式
- 所有写操作验证 CSRF Token
- 前端 Axios 拦截器自动携带

### 3. 限流保护
- IP 维度限流
- 用户维度限流
- 端点维度限流
- 可动态配置限流规则

### 4. 资源控制
- 用户并发会话限制 (按角色分级)
- 会话生命周期管理
- 资源释放机制 (停止/删除项目)
- 管理员动态配置能力

### 4. 输入验证
- Pydantic Schema 严格类型验证
- SQL 参数化查询 (防注入)
- 文件上传类型/大小限制
- 路径遍历防护

### 5. 数据安全
- 密码 bcrypt 哈希存储
- 敏感数据 AES-CBC 加密
- 结构化日志脱敏

### 6. 服务保护
- 熔断器防止雪崩
- 超时控制
- 资源限制 (CPU/内存)

## 安全端点

| 端点 | 描述 |
|------|------|
| GET /api/v1/public-key | 获取 RSA 公钥 |
| GET /api/v1/csrf-token | 获取 CSRF Token |
| POST /api/v1/vision/check-safety | 图像安全检查 |

## 安全测试

- 集成测试覆盖所有认证/授权端点
- 测试未授权访问返回 401/403
- 测试权限级别隔离

## 建议

1. 定期更新依赖 (运行 `pip audit`)
2. 定期轮换 SECRET_KEY
3. 监控异常访问模式
4. 保持 HTTPS 始终开启
