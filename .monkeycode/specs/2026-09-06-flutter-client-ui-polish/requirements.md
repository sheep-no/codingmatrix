# Flutter Client UI Polish Requirements

## Introduction

本功能提升 Flutter 客户端登录页和工作台的信息层级、响应式布局与状态反馈。

## Glossary

- **客户端**：`flutter_client` 中运行于桌面端和移动端的 Flutter 应用。
- **工作台**：展示 Agent、会话、任务进度和 SSE 事件的认证后页面。

## Requirements

### Requirement 1: 统一视觉层级

**User Story:** AS 客户端用户, I want 一致的深色视觉系统, so that 页面内容更容易识别。

#### Acceptance Criteria

1. WHEN 客户端启动, 客户端 SHALL 使用统一的背景色、卡片边框、圆角和输入框样式。
2. WHEN 页面展示主要内容, 客户端 SHALL 使用标题、辅助文字和容器建立信息层级。

### Requirement 2: 登录反馈

**User Story:** AS 登录用户, I want 清晰的输入与错误反馈, so that 可以快速修正登录信息。

#### Acceptance Criteria

1. WHEN 用户提交空邮箱、无效邮箱或空密码, 客户端 SHALL 在对应输入框显示校验提示。
2. WHEN 登录请求失败, 客户端 SHALL 在高对比度错误容器中显示错误信息。
3. WHEN 用户点击密码可见性按钮, 客户端 SHALL 切换密码显示状态。

### Requirement 3: 响应式工作台

**User Story:** AS 工作台用户, I want 在不同屏幕宽度下查看任务和事件, so that 关键信息保持可读。

#### Acceptance Criteria

1. WHILE 可用宽度小于 720 像素, 工作台 SHALL 垂直排列任务概览和事件区域。
2. WHILE 可用宽度大于或等于 720 像素, 工作台 SHALL 并排展示任务概览和事件区域。
3. WHEN 任务存在, 工作台 SHALL 显示状态标签、阶段、百分比和进度条。
4. WHEN SSE 事件为空, 工作台 SHALL 显示等待事件流的空状态。
