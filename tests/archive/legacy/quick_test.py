#!/usr/bin/env python3
"""
简化版安全测试 - 验证关键功能

使用前确保：
1. 后端服务已启动
2. 数据库中有测试用户
"""

import requests
import json

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"

def test_step(name, func):
    """测试步骤包装器"""
    try:
        result = func()
        print(f"✅ {name}")
        return True
    except AssertionError as e:
        print(f"❌ {name}: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ {name}: {type(e).__name__}: {str(e)}")
        return False

# 测试会话
session = requests.Session()

print("\n" + "="*60)
print("前后端通信安全测试")
print("="*60 + "\n")

# 1. 检查 CSRF Token 端点
def check_csrf_endpoint():
    response = session.get(f"{API}/csrf-token")
    assert response.status_code == 200, f"状态码：{response.status_code}"
    data = response.json()
    assert "csrf_token" in data, "缺少 csrf_token"
    print(f"   CSRF Token: {data['csrf_token'][:30]}...")
    return True

test_step("1. CSRF Token 端点", check_csrf_endpoint)

# 2. 检查登录端点
def check_login_endpoint():
    # 先获取 CSRF
    response = session.get(f"{API}/csrf-token")
    csrf = response.json()["csrf_token"]
    
    # 尝试登录（可能失败，但应该返回有意义的错误）
    response = session.post(
        f"{API}/login",
        json={"email": "test@example.com", "password": "Test123!@#"},
        headers={"X-CSRF-Token": csrf}
    )
    
    # 200 表示登录成功，401 表示用户不存在，都是正常响应
    assert response.status_code in [200, 401, 403], f"异常状态码：{response.status_code}"
    
    # 检查响应格式
    if response.status_code == 200:
        data = response.json()
        assert "access_token" in data, "缺少 access_token"
        print(f"   登录成功，用户：{data.get('username', 'unknown')}")
        
        # 检查 Cookie
        cookies = session.cookies.get_dict()
        if "refresh_token" in cookies:
            print(f"   ✅ Refresh Token Cookie: {cookies['refresh_token'][:30]}...")
        if "csrf_token" in cookies:
            print(f"   ✅ CSRF Token Cookie: {cookies['csrf_token'][:30]}...")
    else:
        error = response.json() if response.headers.get("content-type") == "application/json" else response.text
        print(f"   登录响应：{response.status_code} - {error}")
    
    return True

test_step("2. 登录流程", check_login_endpoint)

# 3. 检查 Refresh Token
def check_refresh_token():
    # 尝试刷新（即使没有有效 token 也应该返回有意义的错误）
    response = session.post(f"{API}/refresh")
    
    # 200 表示刷新成功，401/403 表示需要重新登录
    assert response.status_code in [200, 401, 403], f"异常状态码：{response.status_code}"
    
    if response.status_code == 200:
        data = response.json()
        assert "access_token" in data, "缺少新的 access_token"
        print(f"   Token 刷新成功")
    else:
        print(f"   Token 刷新：{response.status_code}")
    
    return True

test_step("3. Token 刷新", check_refresh_token)

# 4. 检查 CSRF 保护
def check_csrf_protection():
    # 不带 CSRF Token 的请求
    response = session.post(
        f"{API}/login",
        json={"email": "test@example.com", "password": "wrong"}
    )
    
    # 应该返回 403（CSRF 验证失败）或 422（验证错误）
    assert response.status_code in [403, 422], f"应该返回 403/422，实际：{response.status_code}"
    print(f"   无 CSRF Token 被拒绝：{response.status_code}")
    
    return True

test_step("4. CSRF 防护", check_csrf_protection)

# 5. 检查健康端点
def check_health():
    response = session.get(f"{API}/health")
    # 500 表示服务有内部错误
    if response.status_code == 500:
        print(f"   ⚠️  服务返回 500，可能存在配置问题")
        return False
    print(f"   健康检查：{response.status_code}")
    return True

test_step("5. 健康检查", check_health)

print("\n" + "="*60)
print("测试完成")
print("="*60 + "\n")

print("注意:")
print("- 如果看到大量 500 错误，请检查后端日志")
print("- 如果 CSRF Token 端点失败，可能需要重新加载后端服务")
print("- 测试结果仅供参考，具体以浏览器测试为准\n")
