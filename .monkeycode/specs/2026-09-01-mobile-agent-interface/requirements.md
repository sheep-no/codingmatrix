# Requirements Document

## Introduction

为 Agent Dashboard 提供适配手机浏览器的交互界面，使用户能够在窄屏设备上查看生成进度、管理会话、浏览文件和提交项目需求。

## Glossary

- **手机端界面**：视口宽度小于等于 768px 时呈现的单列 Agent 交互界面。
- **会话抽屉**：从屏幕左侧打开的会话历史和项目文件树面板。
- **文件抽屉**：从屏幕右侧打开的当前文件预览面板。

## Requirements

### Requirement 1

**User Story:** AS 手机端用户，我希望在单列页面中查看 Agent 工作状态，以便持续跟踪项目生成。

#### Acceptance Criteria

1. WHEN 视口宽度小于等于 768px，系统 SHALL 使用单列工作区展示 Agent 内容。
2. WHILE Agent 正在生成，系统 SHALL 在手机顶部工具栏显示生成状态。
3. WHEN 用户滚动工作区，系统 SHALL 保持底部需求输入区域可操作。

### Requirement 2

**User Story:** AS 手机端用户，我希望快速打开会话和文件面板，以便完成历史会话与代码浏览操作。

#### Acceptance Criteria

1. WHEN 用户点击会话按钮，系统 SHALL 从左侧打开会话抽屉。
2. WHEN 用户点击文件按钮且存在选中文件，系统 SHALL 从右侧打开文件抽屉。
3. WHEN 用户点击遮罩层或切换会话，系统 SHALL 关闭当前移动端抽屉。

### Requirement 3

**User Story:** AS 手机端用户，我希望输入项目需求，以便在触屏设备上提交生成请求。

#### Acceptance Criteria

1. WHEN 用户聚焦需求输入框，系统 SHALL 使用不小于 16px 的字号减少移动浏览器自动缩放。
2. WHEN 手机存在底部安全区域，系统 SHALL 为输入区域保留安全区域内边距。
3. WHEN 文件预览不可用，系统 SHALL 将文件按钮置为不可操作状态。
