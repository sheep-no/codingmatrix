# 管理员资源控制 - 技术设计

## 架构

```
用户请求 -> JWT 验证 -> 权限检查 (superadmin) -> SystemConfigManager -> 响应
 |
 v
 configs/system_config.json
 |
 v
 更新用户并发限制/系统配置
```

## 并发限制检查流程

```
项目生成请求 -> 获取 user_id 和 role (从 JWT)
 |
 v
 SystemConfigManager.can_create_new_session()
 |
 +----------+----------+
 | |
 v v
 active < limit active >= limit
 | |
 v v
 允许创建会话 返回 429 错误
 提示停止/删除项目
```

## JWT 角色映射流程

```
登录请求 -> 查询 permission_level (0/1/2)
 |
 v
 映射到 role:
 - 0 (normal) -> "user"
 - 1 (admin) -> "admin"
 - 2 (super) -> "superadmin"
 |
 v
 创建 JWT Token (包含 role 字段)
 |
 v
 返回给前端，后续请求携带
```

## 实现细节

### 系统配置管理

使用 `SystemConfigManager` 单例模式管理配置，配置文件存储在 `configs/system_config.json`。

```python
from app.utils.system_config import system_config_manager
from app.utils.security import require_superadmin

@router.get("/admin/config")
async def get_system_config(token: dict = Depends(require_superadmin)):
 return system_config_manager._config

@router.post("/admin/config")
async def update_system_config(
 update: ConfigUpdate,
 token: dict = Depends(require_superadmin)
):
 system_config_manager.set_config_value(update.path, update.value)
 return {"success": True}
```

### 用户并发限制

```python
@router.post("/admin/user-limit")
async def update_user_concurrent_limit(
 update: UserLimitUpdate,
 token: dict = Depends(require_superadmin)
):
 system_config_manager.update_user_override(
 update.user_id, 
 update.limit, 
 update.tier
 )
 return {"success": True}
```

### JWT Token 角色字段

登录时根据 `permission_level` 映射到 `role`：
- `normal` (0) -> `user`
- `admin` (1) -> `admin`
- `super` (2) -> `superadmin`

Token 中包含 `role` 字段用于并发限制判断。

## 权限

- 所有管理 API: superadmin (require_superadmin 装饰器)

## 配置结构

```json
{
 "system_config": {
 "user_concurrent_limits": {
 "default_tiers": {
 "free": 1,
 "basic": 2,
 "premium": 5,
 "enterprise": 10,
 "superadmin": 50
 },
 "user_overrides": {}
 },
 "session_management": {
 "cleanup_inactive_after_hours": 24,
 "max_sessions_per_user": 10
 }
 }
}
```
