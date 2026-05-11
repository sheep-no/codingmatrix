# 管理员资源控制

## 需求

系统管理员需要能够控制和限制用户对系统资源的使用。

### 用户故事

1. 作为管理员，我希望能够限制每个用户的并发项目生成会话数
2. 作为超级管理员，我希望能够动态调整会话限制配置
3. 作为用户，我希望在达到限制时收到明确的提示

## 设计

### API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| /api/v1/agent/admin/project-session/config | GET | 获取配置 |
| /api/v1/agent/admin/project-session/config | POST | 更新配置 |

### 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| MAX_PROJECT_SESSIONS_PER_USER | 1 | 每个用户最大并发会话数 |

### 数据模型

配置存储在 `server_config` 表中:

| key | value | description |
|-----|-------|-------------|
| max_project_sessions_per_user | 1 | 每个用户最大并发项目会话数 |

## 实现状态: 完成
