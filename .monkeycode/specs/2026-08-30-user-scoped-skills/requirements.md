# Requirements Document

## Introduction

本功能统一 Web 与 VS Code 的 Skill 使用边界，提供系统内置、用户云端和工作区会话三类 Skill，并通过统一命名空间、用户认证和会话同步保证权限隔离。

## Glossary

- **System Skill**: 平台内置、所有已认证用户可使用的 Skill。
- **User Skill**: 用户上传并归属于单个用户的云端 Skill。
- **Workspace Skill**: VS Code 从当前 workspace folder 发现并绑定到当前 Agent Host session 的 Skill。
- **Agent Host session**: 一次 VS Code 与云端 Agent Host 的连接会话。
- **命名空间**: Skill 的唯一标识前缀，分别为 `system:`, `user:`, `workspace:`。

## Requirements

### Requirement 1: Skill ownership and isolation

**User Story:** 作为用户，我希望个人 Skills 只属于我的账号，以便保护个人提示词和工作流。

#### Acceptance Criteria

1. WHEN 用户创建 User Skill，云端 SHALL 将 Skill 的 `owner_user_id` 设置为当前认证用户 ID。
2. WHEN 用户查询 User Skills，云端 SHALL 仅返回当前认证用户拥有的 User Skills。
3. WHEN 用户读取、更新或删除 User Skill，云端 SHALL 校验 Skill 所有权并返回对应资源结果。
4. IF 请求用户不拥有目标 User Skill，云端 SHALL 返回统一的资源不可用响应。

### Requirement 2: Skill namespaces

**User Story:** 作为 Agent，我希望同时使用不同来源的同名 Skill，以便项目上下文和个人偏好可以并存。

#### Acceptance Criteria

1. WHEN 系统列出可用 Skills，系统 SHALL 使用 `system:`, `user:` 和 `workspace:` 命名空间生成唯一标识。
2. WHEN User Skill 与 Workspace Skill 使用相同原始名称，系统 SHALL 在可用列表中保留两个独立条目。
3. WHEN Agent 选择 Skill，系统 SHALL 根据完整命名空间标识加载对应内容。
4. WHEN System Skill、User Skill 和 Workspace Skill 同时可用，系统 SHALL 允许三类 Skill 并行存在。

### Requirement 3: Workspace discovery and synchronization

**User Story:** 作为 VS Code 用户，我希望项目中的 Skills 自动同步到当前云端会话，以便 Web 对话使用项目上下文。

#### Acceptance Criteria

1. WHEN VS Code 云端连接启用，扩展 SHALL 递归扫描所有 workspace folders 的 `.claude/skills/**/SKILL.md`、`skills/**/SKILL.md` 和 `data/custom_skills/**/*.md`。
2. WHEN 扩展发现 Workspace Skill，扩展 SHALL 使用 `workspace:<folder-name>:<skill-name>` 作为 Skill 标识。
3. WHEN 工作区 Skill 文件新增或修改，扩展 SHALL 自动重新扫描并同步当前 Agent Host session。
4. WHEN 工作区 Skill 文件删除或移动，扩展 SHALL 从当前 Agent Host session 移除对应 Skill。
5. IF Skill 文件内容超过 100 KB，扩展 SHALL 跳过该文件并记录可诊断的跳过原因。

### Requirement 4: Session lifecycle

**User Story:** 作为用户，我希望工作区 Skills 与当前项目会话绑定，以便项目上下文不会变成长期云端资产。

#### Acceptance Criteria

1. WHILE Agent Host session 处于活动或离线保留状态，云端 SHALL 保存该 session 的 Workspace Skills。
2. WHEN VS Code 断开连接，云端 SHALL 将 session 标记为离线并保留 Workspace Skills 至 session 过期时间。
3. WHEN Agent Host session 过期，云端 SHALL 使该 session 的 Workspace Skills 不再可用于 Web 对话。
4. WHEN VS Code 重新连接并创建新 session，扩展 SHALL 重新发现并同步全部 Workspace Skills。

### Requirement 5: Web availability

**User Story:** 作为 Web 用户，我希望当前 VS Code 会话中的 Skills 可以直接参与对话，以便在 Web 和 VS Code 间共享项目上下文。

#### Acceptance Criteria

1. WHILE 用户拥有活动或离线保留的 Agent Host session，Web SHALL 显示该 session 可用的 Workspace Skills。
2. WHEN Web Agent 处理用户对话，Agent SHALL 自动从当前用户可用的 System、User 和 Workspace Skills 中选择匹配项。
3. WHEN 当前用户没有对应的 Agent Host session，Web SHALL 显示 User Skills 和 System Skills。
4. IF Web 对话请求引用其他用户的 User Skill 或 Workspace Skill，云端 SHALL 返回资源不可用响应。

### Requirement 6: User Skill propagation

**User Story:** 作为用户，我希望个人 Skill 的变更实时作用于我的工作台，以便各入口保持一致。

#### Acceptance Criteria

1. WHEN 用户创建、更新或删除 User Skill，云端 SHALL 向该用户的活动 Web 和 VS Code sessions 推送变更。
2. WHEN VS Code 收到 User Skill 变更，扩展 SHALL 更新本地 Agent Host runtime 的 User Skill 集合。
3. WHEN Web 收到 User Skill 变更，Web Agent SHALL 在后续对话中使用最新版本。
4. IF 目标 session 暂时离线，云端 SHALL 在 session 恢复或重新握手时提供最新 User Skill 集合。

### Requirement 7: Legacy migration

**User Story:** 作为系统管理员，我希望历史 Skills 获得明确归属，以便迁移后继续可用并完成后续分配。

#### Acceptance Criteria

1. WHEN 系统执行历史 Skill 迁移，系统 SHALL 将作者为 `api_user` 的 Skill 归属到按创建时间最早识别出的系统管理员用户。
2. WHEN 系统管理员用户不存在，迁移任务 SHALL 保留可重试状态并报告明确原因。
3. WHEN 历史 Skill 完成迁移，系统 SHALL 保留 Skill 名称、分类、内容、版本和时间字段。
4. WHEN 迁移任务重复执行，系统 SHALL 保持已迁移 Skill 的唯一归属。
