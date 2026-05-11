# API 版本管理文档

## 版本策略

本项目采用 **URL 路径版本化** 策略，版本号直接体现在路由前缀中。

### 版本格式

```
/api/{version}/{resource}
```

示例:
- `/api/v1/auth/login`
- `/api/v2/users`
- `/api/v1/ai-agent/generate`

### 当前版本

| 版本 | 状态 | 说明 |
|------|------|------|
| v1 | 维护中 | 初始版本，保持兼容 |
| v2 | 最新 | 当前活跃开发版本 |

## 版本生命周期

```
活跃 (Active) → 维护 (Maintenance) → 废弃 (Deprecated) → 移除 (Removed)
```

### 各阶段说明

| 阶段 | 说明 | 持续时间 |
|------|------|----------|
| 活跃 | 正常开发，新功能优先添加到此版本 | - |
| 维护 | 仅修复 bug，不添加新功能 | 至少 6 个月 |
| 废弃 | 返回 Deprecation 头，建议迁移 | 至少 3 个月 |
| 移除 | 端点从代码中删除 | - |

## 废弃标记

使用 `@deprecated` 装饰器标记废弃的 API 端点:

```python
from app.api import deprecated

@deprecated(
    since_version="v1",
    removal_version="v3",
    alternative="/api/v2/users",
    message="请使用 v2 版本的用户接口"
)
@router.get("/users/{user_id}")
async def get_user(user_id: int):
    ...
```

### 响应头

废弃的 API 会在响应中添加以下 HTTP 头:

| 头 | 说明 | 示例 |
|----|------|------|
| `Deprecation` | 标记接口已废弃 | `version=v1` |
| `Sunset` | 预计移除版本 | `v3` |
| `Link` | 替代版本链接 | `</api/v2/users>; rel="successor-version"` |

## 版本路由器

### 创建版本路由器

```python
from app.api import get_version_router

# v1 路由器
v1_router = get_version_router("v1", tags=["认证"])

@v1_router.post("/auth/login")
async def login():
    ...

# v2 路由器
v2_router = get_version_router("v2", tags=["用户管理"])

@v2_router.get("/users")
async def list_users():
    ...
```

### 注册到应用

在 `app/main.py` 中:

```python
from app.api import create_versioned_app_setup

create_versioned_app_setup(app)
```

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

1. 将请求路径中的 `/api/v1/` 替换为 `/api/v2/`
2. 检查响应格式变化 (如有)
3. 更新错误码处理逻辑
4. 测试验证

### 兼容性保证

- 同一主版本内保持向后兼容
- 破坏性变更必须升级主版本号
- 废弃接口会保留至少 3 个月过渡期
