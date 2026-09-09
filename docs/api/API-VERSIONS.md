# API 版本管理文档

> 代码同步日期：2026-09-03

## 版本策略

本项目采用 **URL 路径版本化** 策略，版本号直接体现在路由前缀中。

### 版本格式

```
/api/{version}/{resource}
```

示例:
- `/api/v1/login`
- `/api/v1/agent/generate`
- `/api/v2/Controller/users`

### 当前版本

| 版本 | 状态 | 说明 |
|------|------|------|
| v1 | 活跃 | 认证、聊天、Agent、PPT、任务、GirlAI 等产品 API |
| v2 | 活跃 | Nginx、用户/系统管理、模型配置和 MCP 等管理 API |

`v1` 与 `v2` 当前按业务域并行提供。客户端应按资源选择代码中实际挂载的路径，路径前缀没有通用的一一替换关系。

## 当前挂载基线

统计对象为 `app/main.py` 中实际 `include_router()` 后，以 `/api/v1/` 或 `/api/v2/` 开头的 FastAPI Route；排除框架文档路由、静态资源和前端 catch-all。

| 版本 | Router 挂载数 | HTTP | WebSocket | 合计 |
|------|---------------|------|-----------|------|
| v1 | 20 | 199 | 2 | 201 |
| v2 | 8 | 72 | 2 | 74 |
| 总计 | 28 | 271 | 4 | 275 |

v1 WebSocket 为 `/api/v1/ws/ppt/{task_id}` 和 `/api/v1/tasks/ws/{user_id}`；v2 WebSocket 为 `/api/v2/Controller/sys-status` 和 `/api/v2/Controller/logs`。

## 版本生命周期约定

```
活跃 (Active) → 维护 (Maintenance) → 废弃 (Deprecated) → 移除 (Removed)
```

### 各阶段说明

| 阶段 | 说明 | 持续时间 |
|------|------|----------|
| 活跃 | 正常开发并由 `app/main.py` 挂载 | - |
| 维护 | 接收兼容性修复 | 发布计划确定 |
| 废弃 | 端点显式接入废弃响应头后进入迁移期 | 发布计划确定 |
| 移除 | 端点从挂载路由中删除 | 发布计划确定 |

截至同步日期，代码中尚无固定维护期或废弃期的自动执行机制，过渡时长由具体发布计划声明。

## 废弃标记

`app/api/__init__.py` 提供 `@deprecated` 装饰器，可为显式采用它的端点添加废弃元数据：

```python
from app.api import deprecated

@deprecated(
 since_version="v1",
 removal_version="v3",
 alternative="/api/v2/models/default",
 message="请使用 v2 版本的用户接口"
)
@router.get("/users/{user_id}")
async def get_user(user_id: int):
 ...
```

### 响应头

装饰器设计目标包含以下响应头：

| 头 | 说明 | 示例 |
|----|------|------|
| `Deprecation` | 标记接口废弃起始版本 | `version=v1` |
| `Sunset` | 预计移除版本 | `v3` |
| `Link` | 替代端点链接 | `</api/v2/models/default>; rel="successor-version"` |

当前 `app/api` 路由未使用 `@deprecated`，`app/main.py` 也未调用 `create_versioned_app_setup()` 或安装 `VersionMiddleware`。生产挂载链路当前不会自动返回上述废弃头或 `X-API-Version`、`X-API-Deprecation-Notice`。

## 当前路由注册方式

`app/main.py` 直接为各业务 Router 指定版本前缀；部分 Router 自带资源前缀，最终路径是两级前缀拼接结果。

```python
app.include_router(userRouter, prefix="/api/v1", tags=["auth"])
app.include_router(agentRouter, prefix="/api/v1", tags=["agent"])
app.include_router(modelAdminRouter, prefix="/api/v2", tags=["model-admin"])
```

| main.py 前缀 | Router 内前缀或路径 | 最终路径 |
|--------------|---------------------|----------|
| `/api/v1` | `/login` | `/api/v1/login` |
| `/api/v1` | `/agent` + `/orchestrate/stream` | `/api/v1/agent/orchestrate/stream` |
| `/api/v1` | `/tasks` + `/{task_id}/events` | `/api/v1/tasks/{task_id}/events` |
| `/api/v2` | `/models` + `/context-lengths` | `/api/v2/models/context-lengths` |

`get_version_router()`、`include_all_version_routers()` 和 `create_versioned_app_setup()` 当前属于预留基础设施，`app/main.py` 的生产挂载链路未调用这些函数。

## 错误码规范

错误码分为五类，详见 `app/utils/error_codes.py`:

| 分类 | 范围 | 前缀 | 说明 |
|------|------|------|------|
| 认证错误 | 1000-1999 | AUTH_ | 认证和授权相关 |
| 验证错误 | 2000-2999 | VAL_ | 输入验证相关 |
| 资源错误 | 3000-3999 | RES_ | 资源操作相关 |
| 业务错误 | 4000-4999 | BIZ_ | 业务逻辑相关 |
| 系统错误 | 5000-5999 | SYS_ | 系统基础设施相关 |

### 错误响应格式

```json
{
 "success": false,
 "code": "AUTH_1001",
 "message": "需要认证",
 "details": {},
 "timestamp": "2024-01-01T00:00:00+00:00"
}
```

## 分页规范

### 标准分页

适用于数据量可控、变更不频繁的场景。

**请求参数:**
- `page`: 页码 (从 1 开始，默认 1)
- `size`: 每页大小 (默认 20，最大 100)

**响应格式:**
```json
{
 "success": true,
 "data": [...],
 "pagination": {
 "total": 100,
 "page": 1,
 "size": 20,
 "pages": 5,
 "has_next": true,
 "has_prev": false
 }
}
```

### 游标分页

适用于数据频繁变动或无限滚动场景。

**请求参数:**
- `cursor`: 游标 (Base64 编码的 JSON)
- `size`: 每页大小 (默认 20，最大 100)

**响应格式:**
```json
{
 "success": true,
 "data": [...],
 "pagination": {
 "next_cursor": "eyJpZCI6MTAwfQ==",
 "has_more": true
 }
}
```

## 迁移指南

### 从 v1 迁移到 v2

当前采用按资源迁移方式：

1. 从 `app/main.py` 和目标 Router 确认新端点已实际挂载。
2. 按资源更新方法、路径、认证、请求 schema 和响应 schema。
3. 对照 `/api/openapi.json` 验证 HTTP 端点；WebSocket 路径从 Router 源码核对。
4. 在发布说明中声明替代路径、过渡期和移除日期。

现有 v1 产品 API 与 v2 管理 API 各自活跃；通用的 `/api/v1/*` 到 `/api/v2/*` 一一映射当前不存在。

### 兼容性保证

- 已发布路径的兼容要求由对应业务模块和发布说明管理。
- 破坏性变更应提供新路径或明确版本迁移，并同步 OpenAPI 与本文件。
- 废弃端点需要显式接入废弃响应头并给出可验证的替代路径与移除日期。
