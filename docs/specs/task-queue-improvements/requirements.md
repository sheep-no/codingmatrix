# 任务队列改进

## 需求

### 用户故事

1. 作为用户，我希望创建异步任务并跟踪其状态
2. 作为用户，我希望在任务失败时重试
3. 作为管理员，我希望查看所有任务的列表

## 设计

### API

| 端点 | 方法 | 描述 |
|------|------|------|
| /api/v1/tasks | POST | 创建任务 |
| /api/v1/tasks/{id} | GET | 任务状态 |
| /api/v1/tasks | GET | 任务列表 |
| /api/v1/tasks/{id} | DELETE | 取消任务 |
| /api/v1/tasks/{id}/retry | POST | 重试任务 |

### 任务状态

| 状态 | 描述 |
|------|------|
| pending | 等待处理 |
| running | 执行中 |
| completed | 完成 |
| failed | 失败 |
| cancelled | 已取消 |

## 实现状态: 完成

## 已知问题

`app/api/v1/task_queue.py:124,181` 处 `get_db()` 被误用为异步上下文管理器。应改为 `async for db in get_db()`。
