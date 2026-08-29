# Requirements Document

## Introduction

本需求统一模型配置的字段语义，保证管理面保存的模型信息能够完整同步到 Agent 运行时，并为后续收敛 Aicloud 静态注册表提供稳定数据契约。

## Glossary

- **管理面配置**：`data/unified_model_config.yaml` 及其 `ModelConfigManager` 数据模型。
- **运行时配置**：由管理面配置派生的 `data/agent_model_config.yaml`。
- **模型 ID**：供配置和 UI 使用的短标识，例如 `qwen3-8b`。
- **模型 Key**：供应商 API 使用的完整名称，例如 `Qwen/Qwen3-8B`。

## Requirements

### Requirement 1

**User Story:** AS 系统管理员，我希望维护结构化模型配置，以便统一管理模型类型、上下文窗口、输出上限和运行参数。

#### Acceptance Criteria

1. WHEN 管理员读取模型配置时，系统 SHALL 为每个模型返回唯一模型 ID、模型 Key、供应商、模型类型、上下文长度、最大输出长度、启用状态和标签。
2. WHEN 管理员更新模型配置时，系统 SHALL 校验角色和降级链引用的模型 ID 已存在。
3. IF 模型配置文件缺少可选字段，系统 SHALL 使用与 `ModelConfig` 一致的默认值完成解析。

### Requirement 2

**User Story:** AS Agent 运行时，我希望使用最新的管理面配置，以便模型变更即时作用于新请求。

#### Acceptance Criteria

1. WHEN 管理员保存模型、角色或降级链配置时，系统 SHALL 更新运行时派生配置。
2. WHEN 运行时派生配置更新完成时，系统 SHALL 刷新模型 ID 映射、供应商映射、角色缓存和降级链缓存。
3. WHEN 运行时刷新失败时，系统 SHALL 记录可定位的警告并保留当前进程可用状态。

### Requirement 3

**User Story:** AS 开发者，我希望文档准确描述当前模型配置链，以便排查配置漂移。

#### Acceptance Criteria

1. WHEN 文档描述模型配置来源时，文档 SHALL 区分管理面配置、运行时派生配置和 Aicloud 静态目录。
2. WHEN 文档列出角色或降级链时，文档 SHALL 与当前配置文件中的值一致。
3. WHEN 代码注释描述配置加载行为时，注释 SHALL 指明实际读取的配置层级。
