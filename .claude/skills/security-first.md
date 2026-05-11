# 安全优先 Skill (security-first)

## 描述
强化代码安全性，防止常见安全漏洞，遵循 OWASP 安全最佳实践。

## 检查项
- [x] 输入验证
- [x] SQL 注入防护
- [x] XSS 防护
- [x] CSRF 防护
- [x] 认证授权
- [x] 敏感数据加密
- [x] 密码安全
- [x] 安全配置

## 规则

### 1. 输入验证
```python
# ✅ 正确
from pydantic import BaseModel, EmailStr, validator
import re

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    username: str
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("密码至少 8 位")
        if not re.search(r'[A-Z]', v):
            raise ValueError("密码必须包含大写字母")
        if not re.search(r'[0-9]', v):
            raise ValueError("密码必须包含数字")
        return v
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        if len(v) < 3 or len(v) > 20:
            raise ValueError("用户名长度 3-20 个字符")
        return v

# ❌ 错误
username = request.form['username']  # 直接使用用户输入
```

### 2. SQL 注入防护
```python
# ✅ 正确 - 参数化查询
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
result = await db.execute(query, values={"user_id": user_id})

# ORM 查询
user = await session.get(User, user_id)
users = await session.query(User).filter(User.email == email).all()

# ❌ 错误 - 字符串拼接
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
query = f"SELECT * FROM users WHERE id = {user_id}"
```

### 3. XSS 防护
```python
# ✅ 正确 - HTML 转义
from markupsafe import escape

def render_comment(comment):
    return f"<div>{escape(comment)}</div>"

# 前端 Vue 自动转义
<template>
  <div>{{ userInput }}</div>  <!-- 自动转义 -->
  <div v-text="userInput"></div>  <!-- 显式转义 -->
</template>

# ❌ 错误
<div v-html="userInput"></div>  <!-- 除非必要且已清理，否则避免 -->
```

### 4. 密码安全
```python
# ✅ 正确
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 哈希密码
hashed = pwd_context.hash(password)

# 验证密码
is_valid = pwd_context.verify(password, hashed)

# 使用 Argon2（更安全的替代）
from argon2 import PasswordHasher
ph = PasswordHasher()
hashed = ph.hash(password)
ph.verify(hashed, password)

# ❌ 错误
hashed = hashlib.md5(password.encode()).hexdigest()  # MD5 已破解
hashed = hashlib.sha1(password.encode()).hexdigest()  # SHA1 已破解
stored_password = password  # 明文存储
```

### 5. CSRF 防护
```python
# ✅ 正确 - FastAPI
from fastapi_csrf_protect import ProtectCSRF

@app.post("/transfer")
async def transfer(csrf_protect: ProtectCSRF = Depends()):
    await csrf_protect.csrf_check()
    # 处理转账

# 前端
const csrfToken = getCookie('csrf_token')
await fetch('/api/transfer', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken }
})

# ❌ 错误
@app.post("/transfer")  # 没有 CSRF 保护
async def transfer():
    pass
```

### 6. 敏感数据加密
```python
# ✅ 正确
from cryptography.fernet import Fernet

# 生成密钥
key = Fernet.generate_key()
cipher_suite = Fernet(key)

# 加密
encrypted_data = cipher_suite.encrypt(sensitive_data.encode())

# 解密
decrypted_data = cipher_suite.decrypt(encrypted_data).decode()

# 使用 KMS 或 Vault 管理密钥
# ❌ 错误
key = "my-secret-key-123"  # 硬编码密钥
encrypted = base64.b64encode(data)  # 不是加密
```

## AI 提示词模板

```
你是一个安全专家，请根据以下安全要求生成代码：

【安全要求】
1. 所有用户输入必须经过严格验证
2. 数据库查询必须使用参数化，禁止字符串拼接
3. 输出到 HTML 的内容必须转义
4. 密码必须使用 bcrypt 或 Argon2 哈希
5. 实现 CSRF 保护（双重提交 Cookie 模式）
6. 敏感数据必须加密存储
7. 使用 HTTPS 通信
8. 实现速率限制和账户锁定

【认证授权】
- 使用 JWT 进行身份验证
- 实现基于角色的访问控制 (RBAC)
- 密码复杂度要求：至少 8 位，包含大小写字母、数字、特殊字符
- 登录失败 5 次锁定账户 15 分钟

【数据安全】
- 使用参数化查询防止 SQL 注入
- 使用 HTML 转义防止 XSS
- 使用 HTTPS 防止中间人攻击
- 敏感数据加密存储

请生成符合上述安全标准的代码。
```

## 漏洞检查清单

### OWASP Top 10 防护
- [ ] A01: 访问控制失效 - 实现 RBAC
- [ ] A02: 加密机制失效 - 使用强加密算法
- [ ] A03: 注入 - 参数化查询
- [ ] A04: 不安全设计 - 威胁建模
- [ ] A05: 安全配置错误 - 安全默认配置
- [ ] A06: 易感组件 - 定期更新依赖
- [ ] A07: 认证失败 - 强密码策略、MFA
- [ ] A08: 软件/数据完整性 - 数字签名
- [ ] A09: 日志/监控 - 审计日志
- [ ] A10: SSRF - 输入验证

## 相关资源

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security Best Practices](https://docs.python-guide.org/writing/security/)
