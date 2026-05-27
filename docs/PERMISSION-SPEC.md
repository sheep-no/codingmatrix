# 权限规范 (RBAC)

> 最后更新：2026-05-27 | v5.10.0

## 三级权限模型

| 级别 | 名称 | 描述 | 权限范围 |
|------|------|------|----------|
| 0 | normal | 普通用户 | 基础 AI 功能、文件管理、个人项目 |
| 1 | admin | 管理员 | normal 全部 + 用户管理、服务监控、知识管理 |
| 2 | superadmin | 超级管理员 | admin 全部 + 系统配置、限流管理、部署操作 |

**注意**: 权限级别在代码中使用 `normal`/`admin`/`superadmin` 字符串表示

## 权限检查机制

### 后端装饰器

```python
from app.utils.security import require_permission, PermissionLevel

@require_permission(PermissionLevel.ADMIN)
async def admin_only_endpoint():
    ...

@require_permission(PermissionLevel.SUPERADMIN)
async def super_only_endpoint():
    ...
```

### 权限常量

```python
class PermissionLevel:
    NORMAL = "normal"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"
```

### JWT Token 结构

```json
{
    "sub": "user_id",
    "permission_level": "normal",
    "role": "user",
    "exp": 1714665600,
    "type": "access",
    "refresh_until": 1714752000
}
```

**Token 字段说明**:
- `sub`: 用户ID
- `permission_level`: 权限级别 (normal/admin/superadmin)
- `role`: 用户角色 (user/admin/superadmin)，用于并发限制判断
- `exp`: 过期时间
- `type`: Token类型 (access/refresh)
- `refresh_until`: Refresh Token 有效期截止时间

## 端点权限分配

### 公开端点 (无需认证)

| 端点 | 描述 |
|------|------|
| POST /api/v1/login | 用户登录 |
| POST /api/v1/register | 用户注册 |
| GET /api/v1/public-key | 获取 RSA 公钥 |
| GET /api/v1/health/* | 健康检查 |
| GET /, /{path} | 前端静态文件 |

### 普通用户 (normal, level >= 0)

| 端点 | 描述 |
|------|------|
| POST /api/v1/code | AI 代码生成 |
| POST /api/v1/agent/orchestrate | Agent 项目生成 |
| POST /api/v1/agent/orchestrate/stream | Agent 流式生成 |
| POST /api/v1/agent/generate | 项目生成 |
| POST /api/v1/agent/modify | 项目修改 |
| POST /api/v1/agent/evaluate | 需求评价 |
| POST /api/v1/agent/analyze_complexity | 复杂度分析 |
| GET /api/v1/agent/snapshots/{id} | 快照列表 |
| POST /api/v1/agent/rollback/{id} | 快照回滚 |
| GET /api/v1/agent/snapshot/diff | 快照对比 |
| POST /api/v1/agent/session/{id}/action | 会话操作 |
| POST /api/v1/agent/session/{id}/decision | 提交决策 |
| DELETE /api/v1/agent/sessions/{id} | 删除会话 |
| GET /api/v1/agent/saved | 已保存项目 |
| POST /api/v1/agent/save | 保存项目 |
| GET /api/v1/agent/generate/files | 项目文件列表 |
| GET /api/v1/agent/generate/read | 读取文件 |
| DELETE /api/v1/agent/generate/file | 删除文件 |
| GET /api/v1/agent/generate/download/{path} | 下载项目 |
| POST /api/v1/agent/knowledge | 添加知识 |
| GET /api/v1/agent/knowledge | 知识列表 |
| GET /api/v1/agent/knowledge/search | 知识搜索 |
| POST /api/v1/agent/requirement-association | 需求联想 |
| GET /api/v1/agent/performance | 性能指标 |
| GET /api/v1/agent/token-usage | Token 统计 |
| POST /api/v1/agent/apikey | 提交 API Key |
| POST /api/v1/agent/apikey/test | 测试 API Key |
| DELETE /api/v1/agent/apikey/{token} | 删除 API Key |
| GET /api/v1/agent/apikeys | API Key 列表 |
| PUT /api/v1/agent/apikey/{token}/enabled | 启用/禁用 Key |
| POST /api/v1/GirlAi | 虚拟 AI 对话 |
| POST /api/v1/kolors/* | 图像生成 |
| POST /api/v1/pptx/* | PPT 生成 |
| POST /api/v1/files/* | 文件管理 |
| POST /api/v1/vision/* | 视觉分析 |
| POST /api/v1/workflow/* | 工作流 |
| POST /api/v1/aicloud/* | AI 云功能 |
| GET /api/v1/models | 免费模型列表 |
| GET /api/v1/models/default | 默认模型 |
| GET /api/v1/user/profile | 用户资料 |
| GET /api/v1/conversations | 对话列表 |

### 管理员 (admin, level >= 1)

| 端点 | 描述 |
|------|------|
| GET /api/v2/Controller/users | 用户列表 |
| POST /api/v2/Controller/create_user | 创建用户 |
| PATCH /api/v2/Controller/update_user/{id} | 更新用户 |
| DELETE /api/v2/Controller/delete_user/{id} | 删除用户 |
| POST /api/v2/Controller/{id}/reset-password | 重置密码 |
| GET /api/v2/Controller/services | 服务列表 |
| GET /api/v2/Controller/health/{port} | 健康检查 |
| POST /api/v2/Controller/guard/start | 启动守护 |
| POST /api/v2/nginx/check | Nginx 配置检查 |

### 超级管理员 (superadmin, level >= 2)

| 端点 | 描述 |
|------|------|
| GET /api/v2/Controller/admin/config | 系统配置 |
| PUT /api/v2/Controller/admin/config/{key} | 更新配置 |
| GET /api/v2/Controller/admin/stats | 系统统计 |
| GET /api/v2/Controller/admin/memory | 内存统计 |
| GET /api/v2/Controller/admin/docker/containers | Docker 容器 |
| GET /api/v2/Controller/admin/rate-limit | 限流配置 |
| PUT /api/v2/Controller/admin/rate-limit/* | 更新限流 |
| GET /api/v2/Controller/admin/backup | 备份管理 |
| POST /api/v2/nginx/generate | Nginx 配置生成 |
| POST /api/v2/nginx/deploy | Nginx 部署 |
| PUT /api/v2/Controller/service/{port}/fuse-config | 熔断配置 |
| GET /api/v2/admin/config | 获取系统配置 |
| POST /api/v2/admin/config | 更新系统配置 |
| POST /api/v2/admin/user-limit | 更新用户并发限制 |
| DELETE /api/v2/admin/user-limit/{user_id} | 移除用户并发限制 |
| POST /api/v1/models/switch | 切换默认模型 |

## 前端权限控制

### 路由守卫

```javascript
router.beforeEach((to) => {
    const userStore = useUserStore()
    if (to.meta.permissionLevel && userStore.permissionLevel < to.meta.permissionLevel) {
        return '/unauthorized'
    }
})
```

### 组件级控制

```vue
<AdminPanel v-if="userStore.isAdmin" />
<SuperConfig v-if="userStore.isSuper" />
```

## 权限验证流程

```
请求 -> JWT 验证 -> Token 解析 -> 权限级别检查 -> 端点访问决策
 |
 v
 level >= required?
 |
 yes -> 允许访问
 no -> 403 Forbidden
```

## JWT Token 角色映射

```
登录时 permission_level -> role 映射:
 permission_level=0 (normal) -> role="user"
 permission_level=1 (admin) -> role="admin"
 permission_level=2 (superadmin) -> role="superadmin"

Token 结构:
{
    "sub": "user_id",
    "permission_level": "normal", // 用于端点权限检查
    "role": "user", // 用于并发限制判断
    "type": "access",
    "exp": timestamp,
    "refresh_until": timestamp
}
```

## 已知问题

详见 [TECH-DEBT.md](TECH-DEBT.md)

---

## 相关文档

- [安全架构](security/SECURITY-OVERVIEW.md)
- [加密登录](security/ENCRYPTED_LOGIN.md)
- [CSRF 防护](security/CSRF-IMPLEMENTATION-COMPLETE.md)
- [技术债务](TECH-DEBT.md)

---

最后更新：2026-05-27
