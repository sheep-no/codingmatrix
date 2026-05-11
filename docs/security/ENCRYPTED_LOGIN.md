# RSA 加密登录

## 概述

CodingMatrix 使用 RSA-OAEP + AES-CBC 混合加密方案保护登录过程中的密码传输。

## 加密流程

```
前端                              后端
  |                                |
  |--- GET /api/v1/public-key ---->|
  |<---- RSA 公钥 (PEM) -----------|
  |                                |
  | 1. 生成随机 AES Key            |
  | 2. AES 加密密码                |
  | 3. RSA-OAEP 加密 AES Key       |
  |                                |
  |--- POST /api/v1/login -------->|
  |    {encrypted_aes_key,         |
  |     encrypted_password, iv}    |
  |                                |
  |                  1. RSA 解密 AES Key |
  |                  2. AES 解密密码     |
  |                  3. bcrypt 验证      |
  |<---- JWT Token -----------------|
```

## 前端实现

```javascript
import { RSA } from '@/utils/crypto'

// 获取公钥
const publicKey = await api.get('/api/v1/public-key')

// 加密密码
const { encryptedKey, encryptedPassword, iv } = RSA.encryptPassword(
  password,
  publicKey.data
)

// 登录
const response = await api.post('/api/v1/login', {
  username,
  encrypted_aes_key: encryptedKey,
  encrypted_password: encryptedPassword,
  iv
})
```

## 后端实现

```python
from app.utils.encryption import decrypt_password

@router.post("/login")
async def login(body: LoginRequest):
    # 解密密码
    password = decrypt_password(
        body.encrypted_aes_key,
        body.encrypted_password,
        body.iv
    )
    # 验证用户
    user = authenticate(username, password)
    return create_token(user)
```

## 安全特性

- RSA-2048 OAEP 加密 AES Key
- AES-256-CBC 加密密码
- 每次登录生成新的随机 AES Key
- 服务端使用 RSA 私钥解密
- 密码明文不出前端和后端内存
