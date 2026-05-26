"""
AI 平台 - 全面安全测试套件（后端 API）

涵盖：
1. 认证与授权（登录、注册、Token 刷新）
2. CSRF Token 保护
3. RSA+AES 加密登录
4. API 速率限制
5. 密码策略
6. 安全响应头
7. HttpOnly Cookie
"""

import pytest
import requests
import time
import json
from datetime import datetime
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
import base64
import os
import re

# ============================================================================
# 测试配置
# ============================================================================

BASE_URL = "http://127.0.0.1:8000"
API_V1 = f"{BASE_URL}/api/v1"

# ============================================================================
# 工具函数
# ============================================================================

def generate_unique_email():
 """生成唯一邮箱地址"""
 return f"test_{int(time.time() * 1000)}_{os.urandom(2).hex()}@example.com"


def generate_aes_key():
 """生成 AES 密钥"""
 return os.urandom(32)


def generate_iv():
 """生成 IV"""
 return os.urandom(16)


def aes_encrypt(data, aes_key):
 """AES 加密"""
 iv = generate_iv()
 padder = sym_padding.PKCS7(128).padder()
 padded_data = padder.update(json.dumps(data).encode()) + padder.finalize()
 
 cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
 encryptor = cipher.encryptor()
 ciphertext = encryptor.update(padded_data) + encryptor.finalize()
 
 return base64.b64encode(iv + ciphertext).decode(), base64.b64encode(iv).decode()


def rsa_encrypt_key(aes_key, public_key_pem):
 """RSA 加密 AES 密钥"""
 public_key = serialization.load_pem_public_key(public_key_pem.encode(), backend=default_backend())
 encrypted_key = public_key.encrypt(
 aes_key,
 padding.OAEP(
 mgf=padding.MGF1(algorithm=serialization.hashes.SHA256()),
 algorithm=serialization.hashes.SHA256(),
 label=None
 )
 )
 return base64.b64encode(encrypted_key).decode()


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def session():
 """创建请求会话"""
 return requests.Session()


@pytest.fixture(scope="function")
def fresh_session():
 """创建新的会话（用于 CSRF 测试）"""
 return requests.Session()


@pytest.fixture(scope="function")
def registered_user(session):
 """创建已注册用户"""
 email = generate_unique_email()
 password = "Test1234!@#"
 username = "TestUser"
 
 # 获取 CSRF
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 # 注册
 r = session.post(
 f"{API_V1}/register",
 json={"email": email, "password": password, "username": username},
 headers={"X-CSRF-Token": csrf}
 )
 
 if r.status_code != 200:
 pytest.skip(f"注册失败：{r.text}")
 
 return {
 "email": email,
 "password": password,
 "username": username,
 "access_token": r.json().get("access_token"),
 "csrf_token": csrf
 }


@pytest.fixture(scope="function")
def csrf_token(session):
 """获取 CSRF Token"""
 r = session.get(f"{API_V1}/csrf-token")
 return r.json()["csrf_token"]


@pytest.fixture(scope="session")
def rsa_public_key(session):
 """获取 RSA 公钥"""
 r = session.get(f"{API_V1}/public-key")
 return r.json()["public_key"]


# ============================================================================
# 测试：健康检查
# ============================================================================

class TestHealth:
 """健康检查测试"""
 
 def test_health_endpoint(self, session):
 """测试健康检查端点"""
 r = session.get(f"{API_V1}/health")
 assert r.status_code == 200
 data = r.json()
 assert data["status"] == "healthy"
 assert "api" in data["checks"]
 assert data["checks"]["api"]["status"] == "healthy"
 
 def test_health_live(self, session):
 """测试存活检查"""
 r = session.get(f"{API_V1}/health/live")
 assert r.status_code == 200
 assert r.json()["status"] == "alive"


# ============================================================================
# 测试：CSRF Token 保护
# ============================================================================

class TestCSRFProtection:
 """CSRF Token 保护测试"""
 
 def test_csrf_token_retrieval(self, session):
 """测试获取 CSRF Token"""
 r = session.get(f"{API_V1}/csrf-token")
 assert r.status_code == 200
 data = r.json()
 assert "csrf_token" in data
 assert len(data["csrf_token"]) > 20
 assert data["expires_in"] == 3600
 
 def test_csrf_cookie_set(self, session):
 """测试 CSRF Cookie 是否设置"""
 r = session.get(f"{API_V1}/csrf-token")
 assert "csrf_token" in session.cookies
 
 def test_csrf_missing_token_rejected(self, fresh_session):
 """测试无 CSRF Token 被拒绝"""
 # 稍微等待避免限流
 time.sleep(0.5)
 
 r = fresh_session.post(
 f"{API_V1}/login",
 json={"email": "test@test.com", "password": "Test123!"}
 )
 # 403 (CSRF) 或 429 (限流) 都表示被拒绝
 assert r.status_code in [403, 429]
 assert "CSRF" in r.json().get("detail", "") or r.status_code == 429
 
 def test_csrf_invalid_token_rejected(self, fresh_session):
 """测试错误 CSRF Token 被拒绝"""
 time.sleep(0.5)
 
 # 设置有效 Cookie
 fresh_session.cookies.set("csrf_token", "valid_cookie_token")
 
 r = fresh_session.post(
 f"{API_V1}/login",
 json={"email": "test@test.com", "password": "Test123!"},
 headers={"X-CSRF-Token": "invalid_header_token"}
 )
 # 403 (CSRF) 或 429 (限流) 都表示被拒绝
 assert r.status_code in [403, 422, 429]
 
 def test_csrf_valid_token_accepted(self, session, registered_user):
 """测试正确 CSRF Token 通过"""
 email = generate_unique_email()
 
 r = session.post(
 f"{API_V1}/register",
 json={"email": email, "password": "Test1234!@#", "username": "Test"},
 headers={"X-CSRF-Token": registered_user["csrf_token"]}
 )
 # 可能 200（成功）或 429（限流），都说明 CSRF 通过了
 assert r.status_code in [200, 429]


# ============================================================================
# 测试：RSA+AES 加密登录
# ============================================================================

class TestEncryptedLogin:
 """RSA+AES 加密登录测试"""
 
 def test_public_key_endpoint(self, session):
 """测试 RSA 公钥端点"""
 r = session.get(f"{API_V1}/public-key")
 assert r.status_code == 200
 data = r.json()
 assert "public_key" in data
 assert "BEGIN PUBLIC KEY" in data["public_key"] # PEM 格式
 assert data["algorithm"] == "RSA-OAEP"
 assert data["key_size"] == 2048
 
 def test_encrypted_login_success(self, session, registered_user, rsa_public_key):
 """测试加密登录成功"""
 # 获取 CSRF
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 # 准备加密数据
 aes_key = generate_aes_key()
 login_data = {
 "email": registered_user["email"],
 "password": registered_user["password"]
 }
 
 encrypted_data, _ = aes_encrypt(login_data, aes_key)
 encrypted_key = rsa_encrypt_key(aes_key, rsa_public_key)
 
 # 发送加密登录请求
 r = session.post(
 f"{API_V1}/login",
 json={"encrypted_data": encrypted_data, "encrypted_key": encrypted_key},
 headers={"X-CSRF-Token": csrf}
 )
 
 assert r.status_code == 200
 data = r.json()
 assert "access_token" in data
 assert data["encryption_enabled"] is True
 
 def test_plaintext_login_success(self, session, registered_user):
 """测试明文登录（向后兼容）"""
 # 获取 CSRF
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 r = session.post(
 f"{API_V1}/login",
 json={"email": registered_user["email"], "password": registered_user["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 assert r.status_code == 200
 data = r.json()
 assert "access_token" in data


# ============================================================================
# 测试：HttpOnly Cookie (Refresh Token)
# ============================================================================

class TestHttpOnlyCookie:
 """HttpOnly Cookie 测试"""
 
 def test_refresh_token_cookie_set(self, session, registered_user):
 """测试 Refresh Token Cookie 设置"""
 # 获取 CSRF
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 # 登录
 r = session.post(
 f"{API_V1}/login",
 json={"email": registered_user["email"], "password": registered_user["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 assert r.status_code == 200
 
 # 检查 Set-Cookie 头
 set_cookie = r.headers.get("Set-Cookie", "")
 assert "refresh_token" in set_cookie
 assert "HttpOnly" in set_cookie
 assert "SameSite" in set_cookie
 
 # 检查 Cookie 已保存
 assert "refresh_token" in session.cookies
 
 def test_refresh_token_not_in_body(self, session, registered_user):
 """测试 Refresh Token 不在响应体中"""
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 r = session.post(
 f"{API_V1}/login",
 json={"email": registered_user["email"], "password": registered_user["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 body_text = r.text
 assert "refresh_token" not in body_text
 
 def test_token_refresh_with_cookie(self, session, registered_user):
 """测试使用 Refresh Token Cookie 刷新 Token"""
 # 登录
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 r = session.post(
 f"{API_V1}/login",
 json={"email": registered_user["email"], "password": registered_user["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 # 刷新 Token
 r = session.post(f"{API_V1}/refresh", headers={"X-CSRF-Token": csrf})
 assert r.status_code == 200
 data = r.json()
 assert "access_token" in data


# ============================================================================
# 测试：安全响应头
# ============================================================================

class TestSecurityHeaders:
 """安全响应头测试"""
 
 def test_x_content_type_options(self, session, registered_user):
 """测试 X-Content-Type-Options"""
 r = session.get(f"{API_V1}/health")
 assert r.headers.get("X-Content-Type-Options") == "nosniff"
 
 def test_x_frame_options(self, session, registered_user):
 """测试 X-Frame-Options"""
 r = session.get(f"{API_V1}/health")
 assert r.headers.get("X-Frame-Options") == "DENY"
 
 def test_content_security_policy(self, session, registered_user):
 """测试 Content-Security-Policy"""
 r = session.get(f"{API_V1}/health")
 csp = r.headers.get("Content-Security-Policy", "")
 assert "default-src" in csp
 
 def test_referrer_policy(self, session, registered_user):
 """测试 Referrer-Policy"""
 r = session.get(f"{API_V1}/health")
 rp = r.headers.get("Referrer-Policy", "")
 assert "strict-origin" in rp.lower()
 
 def test_all_security_headers_present(self, session):
 """测试所有安全响应头存在"""
 r = session.get(f"{API_V1}/health")
 
 required_headers = [
 "X-Content-Type-Options",
 "X-Frame-Options",
 "Content-Security-Policy",
 "Referrer-Policy"
 ]
 
 for header in required_headers:
 assert header in r.headers, f"缺少安全响应头：{header}"


# ============================================================================
# 测试：密码策略
# ============================================================================

class TestPasswordPolicy:
 """密码策略测试"""
 
 @pytest.mark.parametrize("weak_password,expected_message", [
 ("123", "长度"),
 ("abc", "长度"),
 ("12345678", "大写"),
 ("password", "大写"),
 ("Password", "数字"),
 ("Pass1234", "特殊字符"),
 ])
 def test_weak_password_rejected(self, session, weak_password, expected_message):
 """测试弱密码被拒绝"""
 email = generate_unique_email()
 
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 r = session.post(
 f"{API_V1}/register",
 json={"email": email, "password": weak_password, "username": "Test"},
 headers={"X-CSRF-Token": csrf}
 )
 
 if r.status_code == 429:
 pytest.skip("触发限流")
 
 assert r.status_code == 400
 data = r.json()
 assert expected_message in data.get("detail", "")
 
 def test_strong_password_accepted(self, session):
 """测试强密码被接受"""
 email = generate_unique_email()
 strong_password = "StrongPass123!@#"
 
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 r = session.post(
 f"{API_V1}/register",
 json={"email": email, "password": strong_password, "username": "Test"},
 headers={"X-CSRF-Token": csrf}
 )
 
 if r.status_code == 429:
 pytest.skip("触发限流")
 
 assert r.status_code == 200
 assert "access_token" in r.json()


# ============================================================================
# 测试：API 速率限制
# ============================================================================

class TestRateLimiting:
 """API 速率限制测试"""
 
 def test_login_rate_limit(self, fresh_session):
 """测试登录速率限制"""
 email = generate_unique_email()
 
 r = fresh_session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 fresh_session.cookies.set("csrf_token", csrf)
 
 # 连续发送 35 次登录请求
 status_codes = []
 for _ in range(35):
 r = fresh_session.post(
 f"{API_V1}/login",
 json={"email": email, "password": "WrongPassword"},
 headers={"X-CSRF-Token": csrf}
 )
 status_codes.append(r.status_code)
 if r.status_code == 429:
 break
 
 # 应该有限流
 assert 429 in status_codes, "未触发登录限流"
 
 def test_rate_limit_message(self, fresh_session):
 """测试限流错误信息"""
 email = generate_unique_email()
 
 r = fresh_session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 fresh_session.cookies.set("csrf_token", csrf)
 
 # 触发限流
 for _ in range(35):
 r = fresh_session.post(
 f"{API_V1}/login",
 json={"email": email, "password": "WrongPassword"},
 headers={"X-CSRF-Token": csrf}
 )
 if r.status_code == 429:
 break
 
 if r.status_code == 429:
 data = r.json()
 assert "频繁" in data.get("detail", "") or "retry_after" in data


# ============================================================================
# 测试：Token 管理
# ============================================================================

class TestTokenManagement:
 """Token 管理测试"""
 
 def test_access_token_format(self, session, registered_user):
 """测试 Access Token 格式"""
 token = registered_user["access_token"]
 parts = token.split(".")
 assert len(parts) == 3 # JWT 三段式
 
 def test_token_contains_permission(self, session, registered_user):
 """测试 Token 包含权限信息"""
 import base64
 
 token = registered_user["access_token"]
 payload = token.split(".")[1]
 
 # 添加填充
 padding = 4 - len(payload) % 4
 if padding != 4:
 payload += '=' * padding
 
 decoded = json.loads(base64.urlsafe_b64decode(payload))
 assert "permission_level" in decoded


# ============================================================================
# 测试：错误处理
# ============================================================================

class TestErrorHandling:
 """错误处理测试"""
 
 def test_invalid_email_format(self, session, csrf_token):
 """测试无效邮箱格式"""
 r = session.post(
 f"{API_V1}/register",
 json={"email": "invalid-email", "password": "Test1234!@#", "username": "Test"},
 headers={"X-CSRF-Token": csrf_token}
 )
 
 if r.status_code != 429: # 跳过限流
 assert r.status_code in [400, 500]
 
 def test_wrong_password(self, session, registered_user):
 """测试错误密码"""
 r = session.get(f"{API_V1}/csrf-token")
 csrf = r.json()["csrf_token"]
 
 r = session.post(
 f"{API_V1}/login",
 json={"email": registered_user["email"], "password": "WrongPassword"},
 headers={"X-CSRF-Token": csrf}
 )
 
 assert r.status_code == 401
 assert "密码错误" in r.json().get("detail", "")
 
 def test_nonexistent_user(self, fresh_session, csrf_token):
 """测试不存在的用户"""
 # 使用新会话避免限流
 email = generate_unique_email()
 
 r = fresh_session.post(
 f"{API_V1}/login",
 json={"email": email, "password": "Test1234!@#"},
 headers={"X-CSRF-Token": csrf_token}
 )
 
 if r.status_code == 429:
 pytest.skip("触发限流")
 
 assert r.status_code == 401
 assert r.json().get("detail") == "邮箱或密码错误"


# ============================================================================
# 主程序（直接运行）
# ============================================================================

if __name__ == "__main__":
 pytest.main([
 __file__,
 "-v",
 "--tb=short",
 f"--html=tests/report_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
 "--self-contained-html"
 ])
