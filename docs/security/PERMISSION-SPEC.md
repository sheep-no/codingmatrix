# 权限规范（RBAC）

> 最后更新：2026-09-03

## 权限模型

权限记录存储在 `permission` 表，模型位于 `app/models/Permission.py`。合法值为：

| 权限 | 层级值 | JWT role | 范围 |
|------|--------|----------|------|
| `normal` | 1 | `user` | 已认证的业务能力与用户自有资源 |
| `admin` | 2 | `admin` | 用户管理、服务状态、日志和监控读取等管理能力 |
| `superadmin` | 3 | `superadmin` | 系统配置、模型配置、MCP、Nginx 部署、备份与限流变更等高权限能力 |

`app/utils/permissions.py` 提供 `has_permission()`、`is_admin()` 和 `is_superadmin()`。`admin` 权限检查按层级比较，因此 `superadmin` 同时满足管理员检查。

## JWT 声明

access token 由 `create_access_token()` 签发：

```json
{
  "sub": "<USER_ID>",
  "exp": 1780000000,
  "iat": 1779998200,
  "type": "access",
  "refresh_until": 1780430200,
  "permission_level": "normal",
  "role": "user"
}
```

- `permission_level` 用于 API 权限判断。
- `role` 是登录时派生的并发与客户端展示字段。
- `type` 必须为 `access` 才能通过 `verify_token`。
- access token 默认 30 分钟到期，`refresh_until` 为签发后 5 天。

refresh token 只包含 `sub`、`exp`、`iat` 和 `type=refresh`，有效期 7 天，存于 HttpOnly Cookie。

## 后端检查方式

当前代码使用 FastAPI 依赖和端点内检查：

```python
from fastapi import Depends
from app.utils.security import verify_token, require_superadmin
from app.api.v2.guardian_router import require_admin

async def user_endpoint(token: dict = Depends(verify_token)):
    ...

async def admin_endpoint(token: dict = Depends(require_admin)):
    ...

async def superadmin_endpoint(token: dict = Depends(require_superadmin)):
    ...
```

`app/api/v2/guardian_router.py` 也定义同名 `require_superadmin`，并与 `require_admin` 一起供 Guardian 和部分 Nginx 路由使用。项目中没有通用 `@require_permission` 装饰器或 `PermissionLevel` 类。

## 公共接口

以下接口未要求 Bearer access token：

- `GET /api/v1/public-key`
- `GET /api/v1/csrf-token`
- `POST /api/v1/login`，要求 CSRF
- `POST /api/v1/register`，要求 CSRF
- `/api/v1/health` 及其 `ready`、`live`、`detailed`、`metrics`、`models` 子路径
- `/api/docs`、`/api/redoc`、`/api/openapi.json`
- 前端静态入口 `/` 与 history fallback
- `GET /api/v1/skills/categories`
- `POST /api/v1/skills/reload`；当前会执行 prompts extractor，且未声明认证依赖，属于待加固的匿名运维入口

`POST /api/v1/refresh` 使用 refresh Cookie 和 CSRF Token，不要求 Bearer access token。

## 普通用户接口

大部分 v1 业务路由直接依赖 `verify_token`，并在涉及资源时继续校验用户 ID 或所有权，包括：

- `/api/v1/chat` 与兼容 `/api/v1/code`
- `/api/v1/agent/*`
- `/api/v1/GirlAi/*`
- `/api/v1/pptx/*`
- `/api/v1/files/*`
- `/api/v1/tasks/*`
- `/api/v1/aicloud/*`
- `/api/v1/workflow/*`
- `/api/v1/vision/*`
- `/api/v1/agent/apikey/*`
- `/api/v1/providers/*`
- `/api/v1/agent/host/*`
- `/api/v1/skills/upload`、`/upload-file`、`/list`、`/{name}` 和 `/migrate-legacy`；`categories` 与 `reload` 采用上文所述公共访问现状

认证只证明调用者身份。每个读取、修改、删除与下载接口还应使用 `token.sub` 校验资源归属。

## 管理员接口

管理员及以上权限的代表性接口：

- `GET /api/v2/Controller/users` 及用户管理接口：先 `verify_token`，再在端点内调用 `is_admin()`。
- `GET /api/v2/Controller/services`
- `GET /api/v2/Controller/health/{port}`
- `GET /api/v2/Controller/admin/stats`
- `GET /api/v2/Controller/admin/memory`
- Guardian 的配置、日志、备份列表和限流读取接口。
- `/api/v2/Controller/sys-status` 与 `/api/v2/Controller/logs` WebSocket：验证 WebSocket Token 后检查管理员层级。

## 超级管理员接口

以下模块或操作使用 `require_superadmin`：

- `/api/v2/admin/config`、`/api/v2/admin/user-limit`、`/api/v2/admin/sandbox-config`
- `/api/v2/models/*` 的模型与 Agent 配置写操作
- `/api/v2/model-config/*`
- `/api/v2/mcp/*`
- `POST /api/v2/nginx/deploy`
- `DELETE /api/v2/nginx/backup/{backup_name}`
- Guardian 的启动、重命名、配置修改、备份创建/恢复/删除和限流修改操作

Nginx 的 `check`、`generate`、`config` 与 `backups` 当前只依赖 `verify_token`；它们属于任何已认证用户可调用的现状。涉及配置内容或基础设施信息的接口应在后续代码加固中按风险提升到管理员或超级管理员。

## 权限生命周期

- 注册创建 `normal` 权限记录。
- 登录发现用户缺少权限记录时创建默认 `normal` 记录。
- 登录和刷新均从数据库读取当前权限，再签发新的 access token。
- 已签发 access token 在到期前携带签发时的权限；权限变更通过重新登录或刷新进入新 Token。

## 前端边界

前端可根据 `permission_level` 或 `role` 控制路由和组件展示。所有敏感操作必须由后端依赖或端点内权限检查决定访问结果。

## 核验清单

- 公共接口清单需包含认证引导、健康、文档资源，以及当前匿名的 Skill 分类与 reload 端点；reload 应作为待加固项跟踪。
- v1 业务接口具有 `verify_token`，资源接口同时验证 `token.sub` 所有权。
- 管理操作使用 `is_admin()` 或 `require_admin`。
- 高风险配置和部署操作使用 `require_superadmin`。
- WebSocket 在握手后验证 Token、权限与资源绑定。
- 权限变更后重新签发 access token。

## 相关文档

- [安全概览](SECURITY-OVERVIEW.md)
- [加密登录](ENCRYPTED-LOGIN.md)
- [CSRF 实现](CSRF-IMPLEMENTATION.md)
