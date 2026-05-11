# 管理员资源控制 - 技术设计

## 架构

```
请求 -> 权限检查 (admin/super) -> ServerConfig CRUD -> 响应
```

## 实现细节

### 获取配置

```python
@router.get("/admin/project-session/config")
async def get_project_session_config(db: AsyncSession = Depends(get_db)):
    config = await db.execute(
        select(ServerConfig).where(ServerConfig.key == "max_project_sessions_per_user")
    )
    return config.first()
```

### 更新配置

```python
@router.post("/admin/project-session/config")
async def update_project_session_config(
    body: ConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    config = await db.execute(
        select(ServerConfig).where(ServerConfig.key == "max_project_sessions_per_user")
    )
    row = config.first()
    if row:
        row.value = str(body.value)
    else:
        row = ServerConfig(key="max_project_sessions_per_user", value=str(body.value))
        db.add(row)
    await db.commit()
```

## 权限

- 获取: admin
- 更新: super
