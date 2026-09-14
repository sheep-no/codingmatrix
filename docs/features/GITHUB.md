# GitHub 集成

> 最后核对：2026-09-12

当前可达接口包括配置读写、凭据验证、仓库/分支/提交只读列表，以及项目保存。实现位于 `app/api/v1/github.py` 与 `app/services/github_remote.py`。表 `github_user_configs` 按 `user_id` 存用户名、加密 Token 和 `use_github`。

## 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/github/config` | 加密保存用户名、Token、是否启用 |
| GET | `/api/v1/github/config` | 返回摘要，`token` 恒为空字符串 |
| POST | `/api/v1/github/verify` | 用库内加密 Token 调用 GitHub `/user` |
| GET | `/api/v1/github/repos` | 列出当前凭据可见仓库，最多 100 个 |
| GET | `/api/v1/github/repos/{owner}/{repo}/branches` | 列出分支，最多 100 个 |
| GET | `/api/v1/github/repos/{owner}/{repo}/commits` | 列出最近提交，最多 20 条；可选 `sha` |

Token 用 AES-GCM 加密，密钥再经应用 RSA 公钥 OAEP 包装，AAD 为 `github:{user_id}`。读取摘要时尝试解密以判断 `credential_state`：`stored`、`missing`、`unreadable`。

保存规则：

1. 用户名需符合 GitHub 登录名格式（最长 39，字母数字与中间连字符）。
2. Token 最长 4096 且不能含空白。
3. 已有凭据时改用户名必须同时提交新 Token。
4. `use_github=true` 时必须已有用户名和可解密 Token。
5. 成功响应带 `success`、`persisted`、`has_token`、`credential_state`；GET 配置的 `verified` 固定为 `false`，`verification_status` 为 `not_performed`。

验证与列表规则：

1. 只读接口使用库内解密 Token，响应不含 Token。
2. 未配置或无法解密时返回 422。
3. `POST /verify` 比较 GitHub `login` 与已存用户名（大小写不敏感）；匹配时 `verified=true`。
4. `owner`/`repo` 需符合 GitHub 命名；非法路径返回 422。
5. GitHub PAT 无效映射为 422；403/404 分别为拒绝访问、资源不存在。

## 项目保存

`POST /api/v1/github/save` 请求体：

- `project_name`、`project_description`
- `project_data`：JSON 字符串，对象键为相对路径、值为文件内容
- `github_config`：可选。`username`、`token`、`use_github`；缺省时读库内加密配置

路径会做穿越校验（`Path.is_relative_to`）。启用 GitHub 时在临时目录 `git init`，调用 `POST https://api.github.com/user/repos` 创建公开仓库（`private: false`）。仓库名冲突时追加 Unix 时间戳再建，remote 使用返回的 `owner/name`，再用 `http.extraHeader` 推送 `main`，remote URL 不含 Token。请求体有 Token 则用本次凭据；否则解密库内 Token。`use_github` 缺省时沿用已保存开关。空 `project_data` 返回 400。Web `/save` 客户端超时 90 秒。

`use_github=false` 时写入 `projects/{user_id}/{project_name}` 并做本地 `git init`；目录已存在则先改名为带时间戳的 `_backup_`。

响应：`success`、`message`、`repo_url`、`commit_id`。本地保存时 `repo_url` 为绝对路径。

## 客户端

Flutter 设置页调用配置 GET/POST、`/verify`、仓库/分支/提交列表。验证成功后设置页 `verified` 立刻为 true；GET 配置仍不落库。Token 输入框留空表示保留同名账号已存凭据。`GithubBinding.token` getter 恒为空。`GithubClient.saveProject` 可省略 `github_config`，改走库内凭据。项目文件页仅在 `use_github` 为 true 时显示「推送到 GitHub」，否则给出前往设置的入口。

Web 设置页 GitHub 标签承载 `GithubConfigPanel.vue`；`/github-config` 重定向到 `/settings?tab=github`。打开面板会 GET `/config` 同步 `use_github` 与用户名；已保存 Token 可留空。面板有「保存配置」；用户名或 Token 失焦、开关变更都会 POST `/config`，开关以服务端结果为准。保存成功后清空输入框中的 Token，不写 sessionStorage。Agent 工作台与项目生成器在服务端 `use_github` 为 true 时，保存后追加 `/save`；仓库名会去掉非 `[A-Za-z0-9._-]` 字符，Agent 推送使用 `agent-<时间戳>`。

## 代码索引

- `app/api/v1/github.py`
- `app/services/github_config_service.py`
- `app/services/github_remote.py`
- `app/models/github_config.py`
- `src/utils/api/github.js`
- `src/components/GithubConfigPanel.vue`
- `src/views/Settings.vue`
- `src/composables/useAgentBackend.js`
- `flutter_client/lib/infrastructure/github/github_client.dart`
- `flutter_client/lib/presentation/project_files_page.dart`
- `flutter_client/lib/presentation/github_settings_page.dart`
- `src/stores/github.js`
