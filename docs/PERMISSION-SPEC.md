# 权限规范 (RBAC)

## 三级权限模型

| 级别 | 名称 | 描述 | 权限范围 |
|------|------|------|----------|
| 0 | normal | 普通用户 | 基础 AI 功能、文件管理、个人项目 |
| 1 | admin | 管理员 | normal 全部 + 用户管理、服务监控、知识管理 |
| 2 | super | 超级管理员 | admin 全部 + 系统配置、限流管理、部署操作 |

## 权限检查机制

### 后端装饰器

```python
@require_permission(PermissionLevel.ADMIN)
async def admin_only_endpoint():
    ...

@require_permission(PermissionLevel.SUPER)
async def super_only_endpoint():
    ...
```

### 权限常量

```python
class PermissionLevel:
    NORMAL = 0
    ADMIN = 1
    SUPER = 2
```

### JWT Token 结构

```json
{
  "sub": "user_id",
  "permission_level": 1,
  "exp": 1714665600
}
```

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
| POST /api/v1/agent/generate | AI 项目生成 |
| POST /api/v1/GirlAi | 虚拟 AI 对话 |
| POST /api/v1/kolors/* | 图像生成 |
| POST /api/v1/pptx/* | PPT 生成 |
| POST /api/v1/files/* | 文件管理 |
| POST /api/v1/vision/* | 视觉分析 |
| POST /api/v1/workflow/* | 工作流 |
| POST /api/v1/aicloud/* | AI 云功能 |
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

### 超级管理员 (super, level >= 2)

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
                            no  -> 403 Forbidden
```
