# CSRF 防护实现

## 概述

CodingMatrix 使用 Double-submit Cookie 模式实现 CSRF 防护。

## 工作原理

```
1. 前端请求 GET /api/v1/csrf-token
2. 后端生成 CSRF Token，设置 Cookie
3. 前端在后续写请求中携带 CSRF Token (Header)
4. 后端验证 Cookie 中的 Token 与 Header 中的 Token 一致
```

## 实现细节

### 后端 (app/utils/csrf.py)

```python
from fastapi import Request, Response
from app.utils.csrf import generate_csrf_token, verify_csrf_token

# 生成 Token
@router.get("/csrf-token")
async def get_csrf_token(response: Response):
    token = generate_csrf_token()
    response.set_cookie("csrf_token", token, httponly=False)
    return {"csrf_token": token}

# 验证 (中间件自动执行)
def verify_csrf(request: Request):
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if cookie_token != header_token:
        raise HTTPException(403, "CSRF validation failed")
```

### 前端 (Axios 拦截器)

```javascript
axios.interceptors.request.use(config => {
  const csrfToken = getCookie('csrf_token')
  if (csrfToken && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(config.method?.toUpperCase())) {
    config.headers['X-CSRF-Token'] = csrfToken
  }
  return config
})
```

## 防护措施

| 防护 | 说明 |
|------|------|
| Cookie 标记 | httponly=False (前端需读取) |
| Header 验证 | X-CSRF-Token |
| 写操作保护 | POST/PUT/DELETE/PATCH |
| GET 豁免 | GET 请求不验证 |

## 安全测试

所有 CSRF 相关测试通过:
- `test_security_api.py` - CSRF Token 获取
- `test_security_api.py` - 无效 Token 拒绝
- `test_security_api.py` - 缺失 Token 拒绝
