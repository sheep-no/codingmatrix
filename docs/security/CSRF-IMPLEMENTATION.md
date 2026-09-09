# CSRF 防护实现

> 最后更新：2026-09-03

项目使用带服务端有效期记录的 Double-submit Cookie。实现位于 `app/utils/csrf.py`、`app/api/v1/auth.py`、`src/utils/csrf.js` 和 `src/utils/api/base.js`。

## Token 获取

`GET /api/v1/csrf-token` 创建随机 `secrets.token_urlsafe(32)` Token，返回 JSON，并设置同值 Cookie：

| 属性 | 值 |
|------|----|
| Cookie 名 | `csrf_token` |
| `HttpOnly` | `false`，供前端读取 |
| `SameSite` | `lax` |
| `Secure` | `ENV != development` 时启用 |
| Path | `/` |
| 有效期 | 3600 秒 |

服务端同时在当前进程内的 `CSRFTokenManager._tokens` 保存 Token、可选用户 ID 和到期时间。

## 验证规则

`csrf_protect` 依次验证：

1. 请求头 `X-CSRF-Token` 存在。
2. Cookie `csrf_token` 存在。
3. Header 与 Cookie 完全相等。
4. Token 存在于当前进程的管理器中且未过期。

失败返回 HTTP 403。`csrf_protect_optional` 使用相同检查，失败时返回 `None`。

## 实际保护范围

当前代码通过 FastAPI 路由依赖保护以下三个端点：

| 方法 | 路径 |
|------|------|
| `POST` | `/api/v1/login` |
| `POST` | `/api/v1/register` |
| `POST` | `/api/v1/refresh` |

应用未注册全局 CSRF 中间件。其他 POST、PUT、PATCH 和 DELETE 端点依赖 Bearer Token、Cookie 属性及各自的鉴权逻辑；它们不会自动执行 `csrf_protect`。

## 前端行为

`src/utils/csrf.js` 从 Cookie 读取 Token，并在缺失时请求 `/api/v1/csrf-token`。`src/utils/api/base.js` 会为常规请求附加 `X-CSRF-Token`，请求统一使用 `credentials: include`。

登录客户端显式先获取 CSRF Token，再提交加密登录载荷。当前前端还存在两个接口接线差异：

- 基础客户端的 `CSRF_SKIP_ENDPOINTS` 包含 `/api/v1/register`，而后端注册端点要求 CSRF。
- `createAuthClient.refreshToken()` 直接调用 `/api/v1/refresh`，未附加 `X-CSRF-Token`；`src/utils/tokenManager.js` 的刷新路径会获取并附加该 Header。

注册与刷新流程上线前应统一复用一个会自动获取和附加 CSRF Token 的请求入口。

## 多进程边界

CSRF Token 状态保存在进程内字典。多 worker 部署可能由一个 worker 签发 Token、另一个 worker 执行验证，从而返回 403。生产多 worker 场景应将有效 Token 状态迁移到共享存储，或采用可由每个 worker 独立验证的签名 Token 方案。

## 请求示例

```bash
# 获取 Cookie 与响应 Token
curl -c cookies.txt http://localhost:8000/api/v1/csrf-token

# 使用响应中的 Token 发起受保护请求
curl -b cookies.txt -X POST http://localhost:8000/api/v1/refresh \
  -H "X-CSRF-Token: <CSRF_TOKEN>"
```

刷新还要求 `refresh_token` HttpOnly Cookie。登录与注册分别要求各自的请求体。

## 核验要点

- 同时缺少 Header 和 Cookie 时返回 403。
- Header 与 Cookie 不一致时返回 403。
- 超过一小时或服务端状态丢失的 Token 返回 403。
- 开发环境 Cookie 可通过 HTTP 使用；非开发环境要求 HTTPS 发送 Secure Cookie。
- 登录成功和刷新成功都会签发新的 CSRF Cookie。

## 相关文档

- [加密登录](ENCRYPTED-LOGIN.md)
- [权限规范](PERMISSION-SPEC.md)
- [安全概览](SECURITY-OVERVIEW.md)
