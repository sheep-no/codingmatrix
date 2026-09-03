# 加密登录实现

> 最后更新：2026-09-03

登录使用 RSA-OAEP/SHA-256 与 AES-256-CBC 的混合加密载荷。实现位于 `src/utils/encryption.js`、`app/utils/encryption.py` 和 `app/api/v1/auth.py`。

## 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/v1/public-key` | 返回登录加密公钥、算法和 2048 位 Key 大小 |
| `GET` | `/api/v1/csrf-token` | 创建一小时 CSRF Token 与 Cookie |
| `POST` | `/api/v1/login` | 解密凭据、验证密码并签发 Token |

登录前必须先建立 CSRF Cookie，并在 `X-CSRF-Token` 请求头中回传同一值。

## 前端加密流程

1. 请求 `/api/v1/public-key`，前端缓存 PEM 公钥一小时。
2. Web Crypto API 生成 32 字节 AES Key 与 16 字节 IV。
3. 登录对象 `{"email":"...","password":"..."}` 序列化为 JSON，并使用 AES-CBC 加密。
4. 将 IV 前置到密文，再进行 Base64 编码，形成 `encrypted_data`。
5. 使用 RSA-OAEP/SHA-256 加密 AES Key，再进行 Base64 编码，形成 `encrypted_key`。
6. 将两个字段提交到 `/api/v1/login`。

```json
{
  "encrypted_data": "<BASE64_IV_AND_CIPHERTEXT>",
  "encrypted_key": "<BASE64_RSA_CIPHERTEXT>"
}
```

## 后端解密流程

1. Base64 解码 `encrypted_key`，使用进程内 RSA 私钥和 OAEP/SHA-256 解密 AES Key。
2. Base64 解码 `encrypted_data`，取前 16 字节作为 IV。
3. 使用 AES-CBC 解密剩余密文，移除 PKCS7 填充并解析 JSON。
4. 校验 `email` 与 `password` 字段。
5. 查询用户与权限，使用 bcrypt 验证密码。
6. 签发 access token 和 refresh token，设置 refresh 与 CSRF Cookie。

登录密钥管理器默认从工作目录下的 `keys/rsa_private.pem` 与 `keys/rsa_public.pem` 加载 RSA 密钥。文件首次缺失时生成并保存密钥对。容器部署应创建可写的 `keys/` 目录，并将同一密钥卷挂载到所有 worker；私钥应限制为服务账户可读。

## 兼容载荷

后端当前还接受以下明文 JSON：

```json
{
  "email": "<USER_EMAIL>",
  "password": "<USER_PASSWORD>"
}
```

该分支会写入明文登录告警日志。Web 前端优先使用混合加密；获取公钥或加密失败时，`src/utils/api/auth.js` 会回退到兼容载荷。生产环境应依赖 HTTPS，并逐步关闭该兼容分支。

## Token 与 Cookie

- access token：HS256 JWT，默认 30 分钟；响应 JSON 返回，由前端作为 Bearer Token 使用。
- access token 的 `refresh_until`：签发后 5 天，用于 access token 解码逻辑。
- refresh token：HS256 JWT，7 天；密钥派生自 `SECRET_KEY`，存入 `HttpOnly` Cookie。
- refresh Cookie：`SameSite=lax`，路径 `/api/v1`，非开发环境设置 `Secure`。
- CSRF Cookie：JavaScript 可读，`SameSite=lax`，路径 `/`，有效期一小时，非开发环境设置 `Secure`。

密码哈希使用 bcrypt，cost 为 12。实现按 bcrypt 限制取 UTF-8 编码后的前 72 字节进行哈希和验证。

## 前端调用示例

```javascript
import { encryptLoginData } from '@/utils/encryption'
import { getCsrfToken } from '@/utils/csrf'

await fetch('/api/v1/csrf-token', { credentials: 'include' })

const payload = await encryptLoginData({
  email: '<USER_EMAIL>',
  password: '<USER_PASSWORD>'
})

const response = await fetch('/api/v1/login', {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': getCsrfToken()
  },
  body: JSON.stringify(payload)
})
```

## 与 API Key 加密的区别

登录加密使用 `src/utils/encryption.js` 的 RSA+AES 混合方案。用户供应商 Key 使用 `src/utils/crypto.js` 直接以 RSA-OAEP 加密短文本，并从 `/api/v1/agent/apikey/public-key` 获取对应公钥。后端两个密钥管理器默认读取同一组 `keys/rsa_private.pem` 与 `keys/rsa_public.pem` 文件。

## 相关文档

- [CSRF 实现](CSRF-IMPLEMENTATION.md)
- [权限规范](PERMISSION-SPEC.md)
- [安全概览](SECURITY-OVERVIEW.md)
