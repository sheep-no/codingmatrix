# Requirements Document

## Introduction

本需求为 Agent 会话提供后端模型信息上下文管理，使角色模型分配、当前模型、调用统计和降级记录能够随会话持久化并恢复。

## Glossary

- **模型上下文**：某个 Agent 会话使用的模型配置版本、角色分配、当前模型、调用统计和降级记录。
- **运行时配置**：Agent 在请求开始时读取的角色模型配置。
- **模型上下文 Checkpoint**：统一状态层中专门保存模型上下文的版本化快照。

## Requirements

### Requirement 1

**User Story:** AS Agent 用户，我希望系统保存会话使用的模型信息，以便识别生成结果对应的模型配置。

#### Acceptance Criteria

1. WHEN Agent 工作流开始时，系统 SHALL 将运行时配置版本和角色模型分配写入模型上下文。
2. WHEN 前端收到模型运行事件时，系统 SHALL 将当前 Agent、当前模型和调用统计合并到模型上下文。
3. WHEN 模型发生降级切换时，系统 SHALL 在模型上下文中追加结构化降级记录。

### Requirement 2

**User Story:** AS Agent 用户，我希望切换历史会话时恢复模型上下文，以便界面显示该会话的真实模型状态。

#### Acceptance Criteria

1. WHEN 用户请求自有会话的模型上下文时，系统 SHALL 返回最新模型上下文 Checkpoint。
2. IF 会话缺少模型上下文 Checkpoint，系统 SHALL 返回当前运行时模型配置和空运行统计。
3. IF 用户请求其他用户的会话，系统 SHALL 返回资源不存在响应。

### Requirement 3

**User Story:** AS 系统维护者，我希望模型上下文使用独立版本序列，以便 Agent Graph Checkpoint 保持稳定。

#### Acceptance Criteria

1. WHEN 模型上下文更新时，系统 SHALL 创建独立 `agent_model_context` 任务的递增 Checkpoint。
2. WHEN相同会话多次更新模型上下文时，系统 SHALL 保留最新完整快照。
3. WHEN Agent Graph 持久化时，系统 SHALL 将 Graph metadata 中的模型上下文同步到模型上下文 Checkpoint。
4. IF 客户端提交的模型上下文 revision 已过期，系统 SHALL 拒绝陈旧更新并允许客户端基于最新快照重试。

### Requirement 4

**User Story:** AS 前端用户，我希望浏览器缓存与后端状态协同工作，以便短时网络异常期间仍可查看会话状态。

#### Acceptance Criteria

1. WHILE 后端模型上下文可用时，前端 SHALL 使用后端快照更新 Pinia 会话状态。
2. IF 后端模型上下文请求失败，前端 SHALL 保留本地会话快照。
3. WHEN 流式生成完成时，前端 SHALL 将已观察到的模型上下文同步到后端。
