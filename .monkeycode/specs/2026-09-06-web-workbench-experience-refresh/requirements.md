# Requirements Document

## Introduction

本规格定义 CodingMatrix Web 工作台的视觉统一、首屏加载、任务反馈、移动端导航和能力中心体验改进要求。规格覆盖首页聊天工作台、Agent Dashboard、Workflow、Capability Center 及共享 UI 基础层，Flutter 客户端属于独立规格范围。

## Glossary

- **Web 工作台**：由首页聊天工作台、Agent Dashboard、Workflow 和 Capability Center 组成的浏览器端交互界面。
- **设计令牌**：用于统一颜色、字号、间距、圆角、阴影和动效的语义化 CSS 变量。
- **首屏可交互**：用户能够看到主要界面并操作核心入口的时间点。
- **能力面板**：用于视觉分析、知识库、代码沙箱、Skills、Agent Host 或项目上传的功能页面。
- **移动端断点**：视口宽度小于等于 768px 的布局条件。

## Requirements

### Requirement 1

**User Story:** 作为 Web 工作台用户，我希望不同页面拥有一致的视觉和交互语言，以便快速理解页面结构和操作方式。

#### Acceptance Criteria

1. THE Web 工作台 SHALL use semantic design tokens for shared colors, typography, spacing, radius, elevation, control height, and motion duration.
2. WHEN a user navigates between the home chat workspace, Agent Dashboard, Workflow, or Capability Center, the system SHALL preserve consistent primary action, secondary action, status, empty state, loading state, and error state presentation.
3. THE Web 工作台 SHALL provide one primary navigation hierarchy containing conversations, projects, capabilities, documentation, and settings.
4. WHEN a control exposes an icon-only action, the system SHALL provide a visible tooltip or accessible label and a minimum interactive area of 40px by 40px.

### Requirement 2

**User Story:** 作为 Web 工作台用户，我希望页面能够根据真实初始化状态完成加载，以便尽快开始工作并理解当前系统状态。

#### Acceptance Criteria

1. WHEN the application initializes, the system SHALL hide the application loading layer after required initialization tasks complete.
2. THE application SHALL report loading progress as determinate progress only when the corresponding completion ratio is available.
3. WHEN a loading component is unmounted, the system SHALL release all timers, animation loops, event listeners, and pending abortable requests owned by the component.
4. THE Web 工作台 SHALL meet a Largest Contentful Paint target below 2.5 seconds, an Interaction to Next Paint target below 200 milliseconds, and a Cumulative Layout Shift target below 0.1 on the supported baseline device.

### Requirement 3

**User Story:** 作为用户，我希望流式 Agent 任务具有清晰的过程反馈，以便知道系统正在做什么以及下一步可以做什么。

#### Acceptance Criteria

1. WHILE an Agent task is running, the system SHALL display the current stage, task status, elapsed time, and available user action.
2. WHEN a task changes stage, the system SHALL update the stage indicator without replacing the entire conversation or workspace view.
3. WHEN a task fails, the system SHALL display a human-readable error, retry action, and preserved user input or task context.
4. WHEN a task completes, the system SHALL display the result summary and the next relevant action, such as preview, download, continue, or open files.

### Requirement 4

**User Story:** 作为移动端用户，我希望在窄屏设备上访问会话、项目和文件能力，以便完成核心任务。

#### Acceptance Criteria

1. WHEN the viewport width is less than or equal to 768px, the system SHALL render one primary work area and expose secondary content through drawers or sheets.
2. WHEN a user opens a mobile drawer, the system SHALL preserve the current task state and provide a visible close action and modal scrim.
3. WHILE the mobile input area is visible, the system SHALL preserve a minimum 16px input font size and the device safe-area inset.
4. WHEN the viewport width is less than or equal to 480px, the system SHALL keep primary controls reachable without horizontal scrolling.

### Requirement 5

**User Story:** 作为用户，我希望能力中心按任务组织并提供清晰反馈，以便使用视觉分析、知识库、代码沙箱和开发工具。

#### Acceptance Criteria

1. WHEN a user opens the Capability Center, the system SHALL load the active capability panel and defer inactive panel data until the user opens the corresponding panel.
2. WHEN a capability request is pending, the system SHALL disable the affected submit action and display an operation-specific loading state.
3. IF one capability request fails, the system SHALL preserve unrelated panel content and provide a retry action for the failed operation.
4. WHEN a destructive capability action is requested, the system SHALL display the target, impact, and confirmation action before execution.
5. WHEN a file is uploaded, the system SHALL display accepted formats, file size, upload progress, processing status, and the resulting resource state.

### Requirement 6

**User Story:** 作为产品和工程维护者，我希望能够量化 Web 工作台体验，以便持续发现回归并验证改进效果。

#### Acceptance Criteria

1. THE project SHALL collect route-level navigation timing and core Web Vitals for supported production-like builds.
2. THE project SHALL define performance budgets for initial JavaScript, initial CSS, largest image resources, and route chunk size.
3. WHEN a production-like build exceeds a defined budget, the verification process SHALL report the exceeded metric and affected asset.
4. THE test suite SHALL cover desktop and mobile navigation, loading states, task state transitions, capability panel isolation, and keyboard-accessible primary actions.
