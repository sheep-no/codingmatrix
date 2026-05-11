# 定时任务清理指南

## 概述

CodingMatrix 使用 APScheduler 管理后台任务，定期清理过期任务和临时数据。

## 清理策略

| 任务类型 | 保留时间 | 清理方式 |
|----------|----------|----------|
| 已完成的 PPT 任务 | 24 小时 | 自动删除 |
| 失败的任务 | 7 天 | 自动删除 |
| 临时文件 | 1 小时 | 定时清理 |
| 过期的 Token | 立即 | JWT 过期自动失效 |
| 过期的会话 | 30 分钟无活动 | 自动清理 |

## 调度器配置

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# 清理过期任务
scheduler.add_job(
    cleanup_expired_tasks,
    'interval',
    hours=1,
    id='cleanup_tasks'
)

# 清理临时文件
scheduler.add_job(
    cleanup_temp_files,
    'interval',
    minutes=30,
    id='cleanup_temp'
)
```

## 管理 API

| 端点 | 描述 |
|------|------|
| GET /api/v1/tasks | 列出任务 |
| GET /api/v1/tasks/{task_id} | 任务状态 |
| DELETE /api/v1/tasks/{task_id} | 取消任务 |
| POST /api/v1/tasks/{task_id}/retry | 重试任务 |

## 监控

- 通过 `/api/v2/Controller/admin/stats` 查看任务统计
- 日志中记录每次清理的详情
