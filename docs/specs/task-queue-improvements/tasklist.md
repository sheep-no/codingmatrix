# 任务队列改进 - 任务列表

## 实施任务

- [x] 创建 Task 模型
- [x] 实现任务 CRUD API
- [x] 实现重试逻辑
- [x] 实现超时控制
- [x] 实现定时清理
- [x] 添加集成测试

## 待修复

- [ ] `app/api/v1/task_queue.py:124` - `get_db()` 异步生成器误用
- [ ] `app/api/v1/task_queue.py:181` - 同上
