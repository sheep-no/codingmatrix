# Flutter 桌面客户端

> 最后更新：2026-09-10 | 源码：`flutter_client/` | Dart：58 个 `lib/**/*.dart` / 9,149 行 | 页面：16 | 测试：15 个文件

`flutter_client` 是 CodingMatrix 的桌面 Agent 工作台，包名为 `codingmatrix_desktop`，版本 `1.0.0+1`，Dart SDK `^3.9.2`。客户端只调用现有 FastAPI 接口，使用 Cookie JWT、CSRF 和 RSA 加密登录，不单独实现业务引擎。

## 分层

| 层 | 路径 | 职责 |
|----|------|------|
| domain | `lib/domain/` | 会话、任务、快照、交付物、工作流、PPT、GirlAI、GitHub 配置等模型 |
| application | `lib/application/` | Riverpod 状态、工作流/PPT/GirlAI/图片生成编排 |
| infrastructure | `lib/infrastructure/` | HTTP 客户端、SSE 解析、认证存储、文件上传 |
| presentation | `lib/presentation/` | 16 个页面与工作台导航 |

入口在 `lib/main.dart`。HTTP 统一走 `AuthenticatedClient`：自动带 Cookie、CSRF，401 时刷新 access token。

## 已接入页面

| 页面 | 文件 | 后端能力 |
|------|------|----------|
| 工作台 | `workbench_page.dart` | 按权限显示模块入口；MCP 仅 `superadmin` |
| 登录 | `login_page.dart` | `/api/v1/public-key`、`/api/v1/csrf-token`、`/api/v1/login` |
| 对话 | `chat_page.dart` | `/api/v1/agent/orchestrate/stream` SSE |
| GirlAI | `girl_page.dart` | `/api/v1/girlai/*` 角色、对话、历史、偏好 |
| PPT | `ppt_page.dart` | `/api/v1/ppt/*` 大纲、生成、质量、单页重生成 |
| 图片生成 | `image_generation_page.dart` | `/api/v1/image/generate`、`/api/v1/image/status/{task_id}` |
| 工作流 | `workflow_page.dart` | `/api/v1/workflow/create` 与状态查询 |
| 文件中心 | `files_page.dart` | `/api/v1/files` 列表、下载、删除；`/api/v1/upload` 普通上传；大于 10MB 走 `/api/v1/upload/init|chunk|complete` |
| 模型列表 | `models_page.dart` | `/api/v1/models` |
| 动态供应商 | `dynamic_provider_page.dart` | `/api/v1/providers` 增删改、同步、测试、启停 |
| 任务中心 | `task_center_page.dart` | `/api/v1/tasks` 列表、取消、重试、恢复、心跳、事件 |
| Agent 历史 | `agent_history_page.dart` | 会话、快照、回滚、并发限制 |
| 决策 | `decisions_page.dart` | 决策记录查询 |
| GitHub | `github_settings_page.dart` | `/api/v1/github/config` 与 `/api/v1/github/save` |
| 管理后台 | `admin_page.dart` | 用户 CRUD、重置密码、系统配置/统计、沙箱、内存、限流、日志、MCP 只读列表 |
| MCP 管理 | `mcp_admin_page.dart` | `/api/v2/mcp/servers` 列表、新增、编辑、启停、连接测试、删除 |

## 认证与权限

- 登录使用 RSA 加密载荷，请求带 CSRF Cookie 与 `X-CSRF-Token`。
- Token 与 CSRF 写入安全存储；后续请求由 `AuthenticatedClient` 附加。
- 管理后台入口对 `admin` / `superadmin` 可见。
- MCP 完整管理页仅 `superadmin` 可见。

## GitHub 边界

当前后端 `app/api/v1/github.py` 只提供配置读写和 `POST /api/v1/github/save`。客户端对应实现配置保存与项目保存。仓库列表、分支、验证、提交、推送、发布接口尚未提供，客户端未接入。

## 管理后台边界

- 用户管理走 `/api/v2/Controller/create_user`、`update_user/{id}`、`delete_user/{id}`、`{id}/reset-password`。
- 运维只读/配置走 `/api/v2/Controller/admin/*`：`system-config`、`stats`、`sandbox-config`、`mcp-servers`、`memory`、`rate-limit`、`log-config`。
- MCP 写操作走 `/api/v2/mcp/servers`，与管理面 MCP 只读列表分开。

## 运行与验证

```bash
# 安装依赖
cd /workspace/flutter_client
flutter pub get

# 静态分析
flutter analyze --no-pub

# 测试（当前环境记录：2026-09-10，88 passed）
flutter test --no-pub --concurrency=1

# 启动桌面端（需本机已配置 Flutter 桌面目标）
flutter run -d windows
flutter run -d linux
```

测试文件位于 `flutter_client/test/`，共 15 个 `*_test.dart`。当前记录覆盖 Mock HTTP 与 widget 测试，不覆盖真实 Provider、GitHub、LLM 或 Android/Windows 真机。

## 相关文档

- [快速开始](../guides/GETTING-STARTED.md)
- [测试指南](../testing/TESTING.md)
- [API 文档](../api/API-DOCUMENTATION.md)
- [模块说明](../architecture/MODULES.md)
