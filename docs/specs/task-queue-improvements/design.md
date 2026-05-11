# 任务队列改进 - 技术设计

## 架构

```
创建任务 -> APScheduler 调度 -> 异步执行 -> 更新状态 -> 通知
```

## 数据模型 (Task)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 任务 UUID |
| user_id | Integer (FK) | 用户 ID |
| type | String | 任务类型 |
| status | String | 状态 |
| result | JSON | 结果 |
| error | Text | 错误信息 |
| created_at | DateTime | 创建时间 |
| completed_at | DateTime | 完成时间 |

## 调度器

使用 APScheduler 管理后台任务:
- 定时清理过期任务
- 定时清理临时文件
- 定时检查超时任务
