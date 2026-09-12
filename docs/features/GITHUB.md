# GitHub 集成

> 最后核对：2026-09-12

当前可达接口只有配置读写和项目保存，实现位于 `app/api/v1/github.py`。表 `github_user_configs` 按 `user_id` 存用户名、加密 Token 和 `use_github`。

## 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/github/config` | 加密保存用户名、Token、是否启用 |
| GET | `/api/v1/github/config` | 返回摘要，`token` 恒为空字符串 |

Token 用 AES-GCM 加密，密钥再经应用 RSA 公钥 OAEP 包装，AAD 为 `github:{user_id}`。读取摘要时尝试解密以判断 `credential_state`：`stored`、`missing`、`unreadable`。

保存规则：

1. 用户名需符合 GitHub 登录名格式（最长 39，字母数字与中间连字符）。
2. Token 最长 4096 且不能含空白。
3. 已有凭据时改用户名必须同时提交新 Token。
4. `use_github=true` 时必须已有用户名和可解密 Token。
5. 成功响应带 `success`、`persisted`、`has_token`、`credential_state`；`verified` 固定为 `false`，`verification_status` 为 `not_performed`。

## 项目保存

`POST /api/v1/github/save` 请求体：

- `project_name`、`project_description`
- `project_data`：JSON 字符串，对象键为相对路径、值为文件内容
- `github_config`：`username`、`token`、`use_github`

路径会做穿越校验。`use_github=true` 时在临时目录 `git init`，调用 `POST https://api.github.com/user/repos` 创建公开仓库（`private: false`），再 `git push -u origin main`。凭据取自本次请求体，不读库内加密 Token。

`use_github=false` 时写入 `projects/{user_id}/{project_name}` 并做本地 `git init`；目录已存在则先改名为带时间戳的 `_backup_`。

响应：`success`、`message`、`repo_url`、`commit_id`。本地保存时 `repo_url` 为绝对路径。

## 客户端

Flutter 设置页 `github_settings_page.dart` 只调用配置 GET/POST。Token 输入框留空表示保留同名账号已存凭据。`GithubBinding.token` getter 恒为空。`GithubClient.saveProject` 已封装 `/save`，当前没有任何页面调用。

`src/` 下没有 `/api/v1/github/*` 请求。

## 代码索引

- `app/api/v1/github.py`
- `app/services/github_config_service.py`
- `app/models/github_config.py`
- `flutter_client/lib/infrastructure/github/github_client.dart`
- `flutter_client/lib/presentation/github_settings_page.dart`
