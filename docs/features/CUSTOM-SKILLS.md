# 自定义 Skill 系统

> 最后核对：2026-09-03
> 状态：用户 Skill 管理、Agent 注册和 VS Code Host 同步活跃

## 概述

自定义 Skill 是用户拥有的 Markdown 提示词资产。系统负责内容校验、文件存储、元数据、用户隔离、运行时注册和 Host 同步。

主要组件：

- `app/api/v1/skills.py`：HTTP API
- `app/services/custom_skill_manager.py`：文件与元数据管理
- `app/services/skill_registry.py`：进程内注册、加载和缓存
- `app/api/v1/agent_host.py`：Host Skill 同步和撤销

## 存储与所有权

根目录为 `/workspace/data/custom_skills`，元数据保存在 `_metadata.json`。用户上传文件存放于：

```text
/workspace/data/custom_skills/{category}/{owner_user_id}/{name}.md
```

读取、更新、删除和列表操作均按 `owner_user_id` 过滤。同名 Skill 可由不同用户分别拥有。历史数据可通过管理员指定归属的迁移接口补齐所有权。

运行时注册表使用 `user:{owner_user_id}:{name}` 作为内部键，避免跨用户冲突。Agent 提示词展示采用 `[user:{name}]` 标记。Agent Host 收到的 Skill map 使用 `user:{name}` 键，因为 Host 会话本身已绑定用户。

## 约束

- 名称以字母开头，可包含字母、数字、下划线和连字符。
- 内容使用 UTF-8 Markdown。
- 单个 Skill 最大 100 KB。
- 每个用户最多 50 个 Skill。
- 分类包括 `orchestrator`、`reviewer`、`validation`、`workflow`、`api`、`tool` 和 `other`。

## API

路由前缀为 `/api/v1/skills`。

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| `POST` | `/upload` | Token | JSON 上传 |
| `POST` | `/upload-file` | Token | Markdown 文件上传 |
| `GET` | `/list` | Token | 列出当前用户 Skill |
| `GET` | `/categories` | 当前实现未声明 Token | 返回分类 |
| `GET` | `/{name}` | Token | 获取当前用户 Skill 详情 |
| `PUT` | `/{name}` | Token | 更新当前用户 Skill |
| `DELETE` | `/{name}` | Token | 删除当前用户 Skill |
| `POST` | `/reload` | 当前实现未声明 Token | 运行 prompts extractor 更新文档 |
| `POST` | `/migrate-legacy` | Token 与管理员校验 | 迁移历史 Skill 所有权 |

路由声明顺序使静态 `/reload` 和 `/migrate-legacy` 仍按各自端点解析。

## API 示例

```json
{
  "name": "strict-review",
  "category": "reviewer",
  "description": "严格审查安全性和回归风险",
  "content": "# Review policy\n\nFocus on correctness and regressions."
}
```

该请求发送到 `POST /api/v1/skills/upload`，并携带用户 Token。

## 注册与缓存

`CustomSkillManager` 在创建和更新后通知 `SkillRegistry` 执行 full reload，清除并重新扫描全部用户 Skill；注册表延迟调用 loader，并缓存加载结果。删除当前调用 `registry.unregister(name)` 使用裸名称，而注册键是 `user:{owner_user_id}:{name}`，因此 namespaced 项可能残留到下次 full reload，这是当前缺陷。删除后的 Host 广播仍由 Skills API 负责。

用户 Skill 与内置 Skill 共享注册表。调用方需要携带用户上下文并解析对应的用户命名空间，才能获得正确的私有内容。

## Agent 集成

Agent 编排链路会把当前用户可用 Skill 注入提示词上下文。传统角色类还会读取固定名称的注册表项，例如：

- `architect_prompt`
- `frontend_engineer_prompt`
- `backend_engineer_prompt`
- `code_reviewer_prompt`
- `ppt_system_prompt`

固定名称覆盖属于 legacy 角色加载方式；用户命名空间注入属于当前多租户方式。扩展新角色时应优先维持用户所有权边界。

## Agent Host 同步

握手响应包含当前用户的 `user_skills`。上传、更新或删除后，Skills API 调用 `broadcast_user_skill_update`，向该用户活跃 Host 会话广播最新集合。

Host API 还提供：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `PUT` | `/api/v1/agent/host/sessions/{session_id}/skills` | 覆盖会话 Skill 集合并排队 `skill_runtime/sync` 动作 |
| `DELETE` | `/api/v1/agent/host/sessions/{session_id}/skills/{skill_name}` | 撤销 Skill 并排队 `skill_revoke` 动作 |

VS Code 扩展声明 `skill_runtime` capability，轮询动作后在本地工具调度器中应用同步或撤销。

## `/reload` 运维状态

`POST /api/v1/skills/reload` 直接执行：

```text
python3 /workspace/.claude/skills/prompts-extractor/extract.py
```

该端点用于重新生成 `PROMPTS.md` 类提示词文档，超时为 60 秒。它不承担用户 Skill 注册表热更新；用户 Skill 的注册表刷新由管理器通知完成。创建和更新操作触发注册表 full reload，删除操作当前仅尝试按裸名称注销。

截至 2026-09-03，该端点未声明 `verify_token` 依赖，并绑定绝对脚本路径。部署时应将其视为受限运维能力，通过网关限制访问，或在代码层增加管理员认证后开放。

## 安全边界

- Skill 内容属于提示词输入，调用方需要继续执行工具权限、路径和审批校验。
- 用户身份来自 Token，客户端提交的 author 不作为所有权依据。
- Host 会话按用户校验，过期会话返回 410。
- Skill 同步只改变提示词运行时，不扩大 Host capability 或 validation policy。

## 代码索引

- `app/api/v1/skills.py`
- `app/services/custom_skill_manager.py`
- `app/services/skill_registry.py`
- `app/api/v1/agent_host.py`
- `vscode-extension/src/tool-dispatcher.ts`
