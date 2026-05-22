# Requirements Document

## Introduction

CodingMatrix 当前只支持 SiliconFlow 一个模型供应商，所有模型调用都通过 `call_siliconflow()` 函数。本需求旨在扩展为多供应商架构，支持主流 API 供应商（OpenAI、Anthropic、阿里百炼、智谱 GLM、DeepSeek 官方、SiliconFlow 等），并允许 Agent 根据不同任务调用不同供应商的模型。

## Glossary

- **供应商 (Provider)**: 模型 API 服务提供商，如 OpenAI、Anthropic、SiliconFlow
- **模型 (Model)**: 具体的 AI 模型，如 gpt-4o、claude-3-5-sonnet、qwen-plus
- **适配器 (Adapter)**: 将不同供应商 API 统一为内部标准接口的中间层
- **路由 (Router)**: 根据任务类型、成本、延迟等指标选择最佳供应商和模型的组件

## Requirements

### Requirement 1: 多供应商配置系统

**User Story:** AS 系统管理员，I WANT 配置多个模型供应商的 API Key 和 Base URL，SO THAT 系统可以调用不同供应商的模型。

#### Acceptance Criteria

1. WHEN 系统启动，系统 SHALL 从环境变量或配置文件加载所有供应商配置
2. THE 系统 SHALL 支持供应商配置格式：`{PROVIDER}_API_KEY` 和 `{PROVIDER}_BASE_URL`
3. THE 系统 SHALL 验证供应商配置有效性（API Key 非空、Base URL 格式正确）
4. WHEN 供应商配置无效，系统 SHALL 记录警告并跳过该供应商

### Requirement 2: 供应商适配器层

**User Story:** AS 开发者，I WANT 统一的模型调用接口，SO THAT 不需要关心底层供应商 API 差异。

#### Acceptance Criteria

1. THE 系统 SHALL 提供统一调用函数 `call_llm(model_name, prompt, system_prompt, ...)`
2. WHEN 调用模型，系统 SHALL 根据模型名称自动选择对应供应商适配器
3. THE 系统 SHALL 支持以下调用参数：
   - `model`: 模型名称
   - `prompt`: 用户提示
   - `system_prompt`: 系统提示（可选）
   - `stream`: 是否流式输出
   - `temperature`: 温度参数
   - `max_tokens`: 最大输出 token
   - `timeout`: 超时设置
   - `cancel_event`: 取消事件
4. THE 系统 SHALL 统一返回 OpenAI 兼容格式（`choices[0].message.content`）

### Requirement 3: 供应商模型路由

**User Story:** AS Agent，I WANT 根据任务类型自动选择最佳供应商和模型，SO THAT 获得最优性能成本比。

#### Acceptance Criteria

1. THE 系统 SHALL 为每个模型映射到具体供应商
2. WHEN Agent 调用模型，系统 SHALL 根据模型名称查找对应供应商
3. THE 系统 SHALL 支持供应商故障转移（当供应商 A 失败时自动尝试供应商 B）
4. THE 系统 SHALL 支持同一模型多供应商备份（如 Qwen 可同时通过 SiliconFlow 和阿里百炼调用）

### Requirement 4: Agent 多供应商集成

**User Story:** AS Agent 系统，I WANT 调用不同供应商的模型完成不同任务，SO THAT 充分利用各供应商的专长。

#### Acceptance Criteria

1. WHEN Agent 推理任务，系统 SHALL 使用 DeepSeek 或 GLM 系列模型
2. WHEN Agent 代码生成任务，系统 SHALL 使用 Qwen 系列模型
3. WHEN Agent 视觉理解任务，系统 SHALL 使用 GLM-4.1V 或 DeepSeek-OCR
4. WHEN Agent 快速响应任务，系统 SHALL 使用轻量模型（Qwen3.5-4B）
5. THE 系统 SHALL 记录每次调用的供应商、模型、延迟和成功状态

### Requirement 5: 向后兼容性

**User Story:** AS 现有用户，I WANT 升级后系统行为不变，SO THAT 不需要修改现有配置。

#### Acceptance Criteria

1. WHEN 用户只配置 SiliconFlow API Key，系统 SHALL 保持与之前相同的行为
2. THE 系统 SHALL 保持 `call_siliconflow()` 函数兼容性（内部调用新适配器层）
3. WHEN 用户配置新供应商，系统 SHALL 自动启用新供应商而不影响现有功能
