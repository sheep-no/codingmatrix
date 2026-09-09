# Flutter Client UI Polish

Feature Name: flutter-client-ui-polish
Updated: 2026-09-06

## Description

本设计在保留认证、Riverpod 状态和 SSE 数据流的基础上，重构 Flutter 客户端的视觉样式和页面布局。

## Architecture

界面继续由 `CodingMatrixApp` 提供全局主题，`LoginPage` 负责认证交互，`WorkbenchPage` 根据视口宽度组织任务概览与实时事件。

## Components and Interfaces

- `CodingMatrixApp`：定义深色配色、卡片和输入框主题。
- `LoginPage`：使用表单校验、密码可见性切换和错误反馈容器。
- `_OverviewCard`：展示会话、任务、阶段、状态和进度。
- `_EventsCard`：展示事件计数、空状态和可选择日志文本。

## Data Models

本功能复用 `AuthState`、`WorkbenchState`、`Task` 和 `SseEvent`，不增加持久化数据。

## Correctness Properties

- 页面切换继续由 `AuthState.isAuthenticated` 控制。
- 任务进度显示值限制在 0 到 100 的视觉范围。
- 响应式断点为 720 像素。

## Error Handling

- 表单在提交前校验 API 地址、邮箱和密码。
- 认证错误使用主题错误色展示。
- 事件为空时展示稳定空状态。

## Test Strategy

- 执行 `flutter analyze` 验证静态类型和 lint。
- 执行 `flutter test` 验证登录页、认证后工作台、模型和 SSE 解析。
- 构建 release APK 验证 Android 资源与打包流程。
