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
5. GitHub 401/403/404 分别映射为凭据无效、拒绝访问、资源不存在。

## 项目保存

`POST /api/v1/github/save` 请求体：

- `project_name`、`project_description`
- `project_data`：JSON 字符串，对象键为相对路径、值为文件内容
- `github_config`：`username`、`token`、`use_github`

路径会做穿越校验。`use_github=true` 时在临时目录 `git init`，调用 `POST https://api.github.com/user/repos` 创建公开仓库（`private: false`），再 `git push -u origin main`。凭据取自本次请求体，不读库内加密 Token。

`use_github=false` 时写入 `projects/{user_id}/{project_name}` 并做本地 `git init`；目录已存在则先改名为带时间戳的 `_backup_`。

响应：`success`、`message`、`repo_url`、`commit_id`。本地保存时 `repo_url` 为绝对路径。

## 客户端

Flutter 设置页调用配置 GET/POST、`/verify`、仓库/分支/提交列表。Token 输入框留空表示保留同名账号已存凭据。`GithubBinding.token` getter 恒为空。`GithubClient.saveProject` 已封装 `/save`，当前没有任何页面调用。

Web `GithubConfigPanel.vue` 与 `src/utils/api/github.js` 走同一组 `/api/v1/github/*` 接口；测试连接会先 POST 配置再 verify 并列出仓库。

## 代码索引

- `app/api/v1/github.py`
- `app/services/github_config_service.py`
- `app/services/github_remote.py`
- `app/models/github_config.py`
- `src/utils/api/github.js`
- `src/components/GithubConfigPanel.vue`
- `flutter_client/lib/infrastructure/github/github_client.dart`
- `flutter_client/lib/presentation/github_settings_page.dart`
