# Flutter 能力注册表与能力开关需求文档

## Introduction

本文档定义 Flutter 桌面端的两项改造。第一项把当前散落在 `workbench_page.dart` 的 13 项硬编码入口收敛为一份声明式能力注册表，并按分组呈现为左侧导航。第二项在需求输入区暴露编排生成开关，其中 `enable_skills` 当前从未发送到后端。

两项改造共同目标是：新增一项能力只需增加一条声明；用户可在提交前控制本次生成启用的能力，而不必依赖服务端默认值。

## Glossary

- **客户端**：`flutter_client` 中运行于桌面端的 Flutter 应用。
- **工作台**：认证后的主页面，当前实现位于 `lib/presentation/workbench_page.dart`。
- **能力**：客户端可通过导航打开的一个功能模块，例如聊天、PPT、任务队列。
- **能力注册表**：客户端声明全部能力的唯一来源。
- **能力分组**：一组能力在导航中的归类，本文档固定为工作区、创作、数据、系统四组。
- **生成开关**：随编排请求 `POST /api/v1/agent/orchestrate/stream` 发送的能力布尔字段。
- **会话权限**：`AuthSession.permissionLevel`，取值为 `normal`、`admin`、`superadmin`。
- **常驻导航栏**：在工作台左侧持续可见、不需要展开动作的导航区域。

## Requirements

### Requirement 1: 能力注册表作为唯一来源

**User Story:** AS 客户端用户, I want 功能入口由一个统一来源声明, so that 新增或调整功能时不会出现入口不一致。

#### Acceptance Criteria

1. The 客户端 SHALL 用一个能力注册表声明每项能力的标识、名称、图标、分组、可见权限与构建函数。
2. WHEN 开发者向能力注册表增加一条声明, the 客户端 SHALL 在所属能力分组中展示该能力。
3. The 客户端 SHALL 由能力注册表生成工作台的全部模块导航入口。
4. The 客户端 SHALL 为每项能力声明唯一的字符串标识。

### Requirement 2: 分组导航与响应式呈现

**User Story:** AS 客户端用户, I want 按用途分组的导航, so that 我可以快速找到目标功能。

#### Acceptance Criteria

1. The 客户端 SHALL 将能力归入工作区、创作、数据、系统四个能力分组。
2. WHILE 视口宽度大于等于 900 像素, the 客户端 SHALL 在工作台左侧展示常驻导航栏。
3. WHILE 视口宽度小于 900 像素, the 客户端 SHALL 通过抽屉展示能力分组。
4. WHEN 用户选择一项能力, the 客户端 SHALL 打开该能力对应的页面。
5. The 客户端 SHALL 在导航中标记当前打开的能力。
6. The 客户端 SHALL 在常驻导航栏中为每个能力分组展示分组标题。

### Requirement 3: 权限过滤可见能力

**User Story:** AS 客户端用户, I want 只看到与我的权限匹配的功能, so that 我不会进入无权访问的页面。

#### Acceptance Criteria

1. WHILE 会话权限不满足能力的可见权限, the 客户端 SHALL 在能力分组中隐藏该能力。
2. The 客户端 SHALL 将管理员后台的可见权限声明为 admin 或 superadmin。
3. The 客户端 SHALL 将 MCP 管理的可见权限声明为 superadmin。
4. WHEN 会话权限从高权限切换为低权限, the 客户端 SHALL 关闭已在展示的高权限能力页面。

### Requirement 4: 输入区生成开关

**User Story:** AS 客户端用户, I want 在提交前选择本次生成启用的能力, so that 我可以控制生成过程的行为。

#### Acceptance Criteria

1. The 客户端 SHALL 在需求输入区展示生成开关。
2. WHEN 用户启动生成, the 客户端 SHALL 将当前生成开关状态放入编排请求体。
3. The 客户端 SHALL 在编排请求体中发送 `enable_skills` 字段。
4. The 客户端 SHALL 在编排请求体中发送 `enable_review`、`enable_validation`、`enable_error_recovery`、`enable_memory`、`spec_first`、`dependency_graph` 字段。
5. WHEN 用户在生成进行中修改生成开关, the 客户端 SHALL 在当前生成结束前保持本次请求的开关值不变。
6. WHILE 用户未修改任一生成开关, the 客户端 SHALL 在编排请求体中发送值 `true` 给全部七个生成开关。

### Requirement 5: 生成开关按账号保持

**User Story:** AS 客户端用户, I want 我的开关选择被记住, so that 我不必每次重新设置。

#### Acceptance Criteria

1. WHEN 用户修改生成开关, the 客户端 SHALL 将生成开关状态持久化到本地存储。
2. The 客户端 SHALL 以当前登录账号标识作为生成开关状态的存储作用域。
3. WHEN 账号切换, the 客户端 SHALL 载入该账号的生成开关状态。
4. WHEN 账号没有已保存的生成开关状态, the 客户端 SHALL 使用 Requirement 4 第 6 条规定的默认值。

### Requirement 6: 工作台上下文动作保持独立

**User Story:** AS 客户端用户, I want 与当前任务绑定的动作留在工作台, so that 导航只承担模块入口职责。

#### Acceptance Criteria

1. WHILE 任务返回项目路径, the 客户端 SHALL 在工作台正文展示项目文件入口。
2. WHILE 存在待提交的架构决策, the 客户端 SHALL 在工作台正文展示决策入口。
3. The 客户端 SHALL 在项目路径存在时跳转到该项目路径对应的文件页面。
