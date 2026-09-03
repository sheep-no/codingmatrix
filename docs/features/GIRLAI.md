# 虚拟姬（GirlAI）

> 最后更新：2026-09-03

GirlAI 是 CodingMatrix 的角色化对话功能。后端入口位于 `app/api/v1/GirlAi.py`，前端入口位于 `src/components/VirtualGirl.vue`。

## 功能范围

- 5 个预设角色：`gentle`、`lively`、`tsundere`、`intellectual`、`companion`。
- 每个用户可创建、查看和删除自己的自定义角色。
- 对话 Prompt 组合角色设定、两条问候示例、用户偏好、较早对话摘要、最近消息和当前输入。
- 历史记录支持分页、关键词搜索、导出和按记录或全量清理。
- 偏好提取覆盖姓名、年龄、爱好、心情、工作和所在地等规则，结果保存到用户偏好表。
- 内联 SVG 为预设角色提供头像。

## API

路由前缀为 `/api/v1/GirlAi`。

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/v1/GirlAi/characters` | 获取预设角色 | JWT |
| GET | `/api/v1/GirlAi/characters/{character_id}/avatar` | 获取 SVG 头像 | 公开 |
| GET | `/api/v1/GirlAi/history/search` | 搜索历史 | JWT |
| POST | `/api/v1/GirlAi` | 发起角色对话 | JWT |
| GET | `/api/v1/GirlAi/history` | 分页读取历史 | JWT |
| GET | `/api/v1/GirlAi/characters/custom/list` | 获取自定义角色 | JWT |
| POST | `/api/v1/GirlAi/characters/custom` | 创建自定义角色 | JWT |
| DELETE | `/api/v1/GirlAi/characters/custom/{character_id}` | 删除自定义角色 | JWT |
| GET | `/api/v1/GirlAi/preferences` | 获取用户偏好 | JWT |
| DELETE | `/api/v1/GirlAi/preferences/{preference_id}` | 删除用户偏好 | JWT |
| DELETE | `/api/v1/GirlAi/history` | 删除指定记录或清空历史 | JWT |

对话请求使用 `GirlRequest`：`prompt` 长度为 1-2000，`temperature` 范围为 0-1.5，`max_tokens` 范围为 50-1000，另含 `character_id`。自定义角色 ID 在 API 中使用 `custom_` 前缀；查询和修改均校验当前用户所有权。

## 对话状态

一次成功对话的写入流程如下：

1. 从 `ChatHistoryService.get_lightweight_context()` 加载摘要和近期消息，近期消息上限由 `MAX_HISTORY_MESSAGES = 10` 控制。
2. 加载用户偏好并构建角色 Prompt；Prompt 中最多使用最近 6 条消息。
3. 调用角色配置的模型并清理角色名前缀等冗余输出。
4. 将用户消息和助手消息写入旧版 `chat_histories`。
5. 通过 `append_conversation_turn()` 写入统一 session/message 状态，并记录 `legacy_message_id` 映射。
6. 在同一请求事务中提交；调用或写入异常会回滚。

删除指定历史或清空历史时，服务会同步清理对应的统一消息。

## 摘要与归档

`app/db/chat_archiver.py` 由数据库调度器调用，用于压缩较早对话：

- 从旧版历史生成 `ChatSummary`。
- 将摘要保存为统一状态的 summary checkpoint。
- 根据旧版消息 ID 删除对应的统一消息。
- 保留近期消息供后续对话继续使用。

该归档流程承担长对话压缩；实时请求仅加载轻量摘要和近期上下文。

## 角色与偏好存储

- `ChatHistory`：旧版逐条聊天记录。
- `CustomCharacter`：用户自定义角色，问候语和标签以 JSON 字符串存储，温度按整数比例持久化。
- `UserPreference`：按用户保存偏好键、值、置信度和来源。
- 统一 `sessions/messages/checkpoints`：支撑跨功能的一致状态模型。

## 前端能力

`VirtualGirl.vue` 当前提供：

- 预设与自定义角色选择、创建和删除。
- 历史分页加载、关键词搜索、文本导出和清空。
- 按当前用户隔离 localStorage 状态。
- 窗口拖拽、缩放、最小化、自动隐藏和 Document Picture-in-Picture。

偏好查询和删除已有后端 API，当前组件未提供偏好管理界面。

## 运行边界

- 全局 GirlAI 对话并发上限为 10。
- 整体请求超时为 30 秒，最多重试 3 次。
- 角色默认模型和参数来自代码常量及 Agent 模型常量，部署时应以运行配置为准。
- 角色头像接口对未知 ID 返回预设兜底头像；自定义角色头像由前端颜色等信息呈现。

## 相关文件

- `app/api/v1/GirlAi.py`
- `app/db/chat_history_service.py`
- `app/db/chat_archiver.py`
- `app/services/girlai_state_adapter.py`
- `app/models/chat_history.py`
- `src/components/VirtualGirl.vue`
- `src/utils/api/girl.js`
