# 数据模型

## SQLAlchemy 模型列表

| 模型 | 文件 | 表名 | 描述 |
|------|------|------|------|
| User | `user.py` | users | 用户信息 |
| History | `history.py` | histories | 聊天/代码历史 |
| File | `file.py` | files | 上传文件元数据 |
| Task | `task.py` | tasks | 异步任务 |
| SavedProject | `saved_project.py` | saved_projects | 已保存项目 |
| AgentMemory | `agent_memory.py` | agent_memories | Agent 记忆 |
| AicloudSession | `aicloud.py` | aicloud_sessions | AI 云会话 |
| AicloudKnowledge | `aicloud_knowledge.py` | aicloud_knowledge | 知识库文档 |
| ServerConfig | `server_config.py` | server_config | 系统配置 |
| ChatHistory | `chat_history.py` | chat_histories | 对话历史 |
| Permission | `Permission.py` | (常量) | 权限定义 |

## User 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 用户 ID |
| username | String | 用户名 (唯一) |
| email | String | 邮箱 (唯一) |
| hashed_password | String | bcrypt 密码 |
| permission_level | Integer | 权限级别 (0/1/2) |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

## History 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 历史 ID |
| user_id | Integer (FK) | 用户 ID |
| type | String | 类型 (code/chat) |
| content | Text | 内容 |
| created_at | DateTime | 创建时间 |

## Task 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 任务 UUID |
| user_id | Integer (FK) | 用户 ID |
| type | String | 任务类型 |
| status | String | 状态 |
| result | JSON | 结果数据 |
| created_at | DateTime | 创建时间 |
| completed_at | DateTime | 完成时间 |

## SavedProject 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 项目 UUID |
| user_id | Integer (FK) | 用户 ID |
| name | String | 项目名称 |
| files | JSON | 文件树 |
| session_id | String | 会话 ID (预留多会话) |
| created_at | DateTime | 创建时间 |

## ServerConfig 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 配置 ID |
| key | String | 配置键 (唯一) |
| value | Text | 配置值 |
| description | String | 描述 |
| updated_by | Integer | 修改人 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |
