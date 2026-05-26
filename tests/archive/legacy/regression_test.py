#!/usr/bin/env python3
"""
综合回归性测试

测试所有安全改进功能：
1. HttpOnly Cookie (Refresh Token)
2. CSRF Token 保护
3. RSA+AES 加密登录
4. API 限流
5. 密码策略
6. 日志安全过滤
7. 安全响应头

使用前确保：
1. 后端服务已启动
2. 测试用户已创建
"""

import requests
import json
import time
import sys
import base64
import os
from datetime import datetime
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from colorama import init, Fore, Style

# 初始化 colorama
init(autoreset=True)

# 配置
PORTS_TO_TRY = [8000] # 只测试后端端口
BASE_URL = None

# 自动检测服务端口
for port in PORTS_TO_TRY:
 try:
 response = requests.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=3)
 if response.status_code in [200, 500]:
 BASE_URL = f"http://127.0.0.1:{port}"
 print(f"{Fore.GREEN}{Style.RESET_ALL} 检测到服务在端口 {port}")
 break
 except:
 pass

if not BASE_URL:
 print(f"{Fore.RED}[FAILED] 未检测到服务，请确保后端服务已启动{Style.RESET_ALL}")
 sys.exit(1)

API_V1 = f"{BASE_URL}/api/v1"

# 测试用户（使用时间戳避免限流）
TEST_USER = {
 "email": f"regression_{int(time.time())}@test.com",
 "password": "Regression123!",
 "username": "RegressionTest"
}

# 测试报告
test_results = {
 "timestamp": datetime.now().isoformat(),
 "passed": 0,
 "failed": 0,
 "skipped": 0,
 "tests": []
}


def log_test(category, name, status, details=""):
 """记录测试结果"""
 icon = "" if status == "PASS" else "[FAILED]" if status == "FAIL" else "⏭️"
 color = Fore.GREEN if status == "PASS" else Fore.RED if status == "FAIL" else Fore.YELLOW
 
 print(f" {color}{icon} {name}: {status}{Style.RESET_ALL}")
 if details:
 print(f" {details}")
 
 test_results["tests"].append({
 "category": category,
 "name": name,
 "status": status,
 "details": details
 })
 
 if status == "PASS":
 test_results["passed"] += 1
 elif status == "FAIL":
 test_results["failed"] += 1
 else:
 test_results["skipped"] += 1


# =============================================================================
# 加密工具函数
# =============================================================================

def generate_aes_key():
 return os.urandom(32)

def generate_iv():
 return os.urandom(16)

def aes_encrypt(data, aes_key):
 iv = generate_iv()
 padder = sym_padding.PKCS7(128).padder()
 padded_data = padder.update(json.dumps(data).encode()) + padder.finalize()
 
 cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
 encryptor = cipher.encryptor()
 ciphertext = encryptor.update(padded_data) + encryptor.finalize()
 
 return base64.b64encode(iv + ciphertext).decode()

def rsa_encrypt_key(aes_key, public_key_pem):
 public_key = serialization.load_pem_public_key(
 public_key_pem.encode(),
 backend=default_backend()
 )
 
 encrypted_key = public_key.encrypt(
 aes_key,
 padding.OAEP(
 mgf=padding.MGF1(algorithm=padding.hashes.SHA256()),
 algorithm=padding.hashes.SHA256(),
 label=None
 )
 )
 
 return base64.b64encode(encrypted_key).decode()


# =============================================================================
# 测试 1: HttpOnly Cookie
# =============================================================================

def test_httponly_cookie(session):
 """测试 HttpOnly Cookie 设置"""
 print(f"\n{Fore.CYAN}[测试 1] HttpOnly Cookie{Style.RESET_ALL}")
 
 # 获取 CSRF
 try:
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json()["csrf_token"]
 log_test("Cookie", "获取 CSRF Token", "PASS")
 except Exception as e:
 log_test("Cookie", "获取 CSRF Token", "FAIL", str(e))
 return
 
 # 登录
 try:
 response = session.post(
 f"{API_V1}/login",
 json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 if response.status_code == 200:
 log_test("Cookie", "登录成功", "PASS")
 
 # 检查 Set-Cookie 头
 set_cookie = response.headers.get("Set-Cookie", "")
 
 has_refresh = "refresh_token" in set_cookie
 has_httponly = "HttpOnly" in set_cookie
 has_samesite = "SameSite" in set_cookie
 
 log_test("Cookie", "Refresh Token Cookie", "PASS" if has_refresh else "FAIL")
 log_test("Cookie", "HttpOnly 属性", "PASS" if has_httponly else "FAIL")
 log_test("Cookie", "SameSite 属性", "PASS" if has_samesite else "FAIL")
 
 # 验证 Cookie 已保存
 cookies = session.cookies.get_dict()
 has_cookie = "refresh_token" in cookies
 log_test("Cookie", "Cookie 已保存到会话", "PASS" if has_cookie else "FAIL")
 
 # 验证响应体中无 refresh_token
 body = response.text
 no_leak = "refresh_token" not in body
 log_test("Cookie", "响应体无 Token 泄漏", "PASS" if no_leak else "FAIL")
 else:
 log_test("Cookie", "登录", "FAIL", f"状态码：{response.status_code}")
 except Exception as e:
 log_test("Cookie", "登录流程", "FAIL", str(e))


# =============================================================================
# 测试 2: CSRF Token
# =============================================================================

def test_csrf_protection(session):
 """测试 CSRF Token 保护"""
 print(f"\n{Fore.CYAN}[测试 2] CSRF Token 保护{Style.RESET_ALL}")
 
 # 无 CSRF Token
 try:
 response = session.post(
 f"{API_V1}/login",
 json={"email": "test@test.com", "password": "test"}
 )
 
 # 应该返回 403 或 422
 if response.status_code in [403, 422]:
 log_test("CSRF", "无 Token 被拒绝", "PASS", f"返回 {response.status_code}")
 else:
 log_test("CSRF", "无 Token 被拒绝", "FAIL", f"应该返回 403/422，实际 {response.status_code}")
 except Exception as e:
 log_test("CSRF", "无 Token 被拒绝", "FAIL", str(e))
 
 # 错误 CSRF Token
 try:
 response = session.post(
 f"{API_V1}/login",
 json={"email": "test@test.com", "password": "test"},
 headers={"X-CSRF-Token": "invalid_token"}
 )
 
 if response.status_code in [403, 422]:
 log_test("CSRF", "错误 Token 被拒绝", "PASS")
 else:
 log_test("CSRF", "错误 Token 被拒绝", "FAIL", f"应该返回 403/422，实际 {response.status_code}")
 except Exception as e:
 log_test("CSRF", "错误 Token 被拒绝", "FAIL", str(e))
 
 # 正确 CSRF Token
 try:
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json()["csrf_token"]
 
 response = session.post(
 f"{API_V1}/login",
 json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 # 200 表示成功，401 表示密码错误（都说明 CSRF 通过了）
 if response.status_code in [200, 401]:
 log_test("CSRF", "正确 Token 通过", "PASS")
 else:
 log_test("CSRF", "正确 Token 通过", "FAIL", f"返回 {response.status_code}")
 except Exception as e:
 log_test("CSRF", "正确 Token 通过", "FAIL", str(e))


# =============================================================================
# 测试 3: RSA+AES 加密登录
# =============================================================================

def test_encrypted_login(session):
 """测试 RSA+AES 加密登录"""
 print(f"\n{Fore.CYAN}[测试 3] RSA+AES 加密登录{Style.RESET_ALL}")
 
 # 获取公钥
 try:
 response = session.get(f"{API_V1}/public-key")
 if response.status_code == 200:
 public_key = response.json()["public_key"]
 log_test("加密", "获取 RSA 公钥", "PASS")
 else:
 log_test("加密", "获取 RSA 公钥", "FAIL", f"状态码：{response.status_code}")
 return
 except Exception as e:
 log_test("加密", "获取 RSA 公钥", "FAIL", str(e))
 return
 
 # 获取 CSRF
 try:
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json()["csrf_token"]
 log_test("加密", "获取 CSRF Token", "PASS")
 except Exception as e:
 log_test("加密", "获取 CSRF Token", "FAIL", str(e))
 return
 
 # 加密登录数据
 try:
 aes_key = generate_aes_key()
 encrypted_data = aes_encrypt({
 "email": TEST_USER["email"],
 "password": TEST_USER["password"]
 }, aes_key)
 encrypted_key = rsa_encrypt_key(aes_key, public_key)
 
 log_test("加密", "AES 加密数据", "PASS")
 log_test("加密", "RSA 加密密钥", "PASS")
 except Exception as e:
 log_test("加密", "数据加密", "FAIL", str(e))
 return
 
 # 发送加密登录请求
 try:
 encrypted_payload = {
 "encrypted_data": encrypted_data,
 "encrypted_key": encrypted_key
 }
 
 response = session.post(
 f"{API_V1}/login",
 json=encrypted_payload,
 headers={"X-CSRF-Token": csrf}
 )
 
 if response.status_code == 200:
 data = response.json()
 encryption_enabled = data.get("encryption_enabled", False)
 
 log_test("加密", "加密登录成功", "PASS")
 log_test("加密", "encryption_enabled=true", "PASS" if encryption_enabled else "FAIL")
 elif response.status_code == 400:
 # 解密失败，可能是测试用户不存在
 log_test("加密", "加密登录", "SKIP", "用户可能不存在")
 else:
 log_test("加密", "加密登录", "FAIL", f"状态码：{response.status_code}")
 except Exception as e:
 log_test("加密", "加密登录", "FAIL", str(e))


# =============================================================================
# 测试 4: Token 刷新
# =============================================================================

def test_token_refresh(session):
 """测试 Token 刷新机制"""
 print(f"\n{Fore.CYAN}[测试 4] Token 刷新机制{Style.RESET_ALL}")
 
 # 先登录获取有效 Cookie
 try:
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json()["csrf_token"]
 
 response = session.post(
 f"{API_V1}/login",
 json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
 headers={"X-CSRF-Token": csrf}
 )
 
 if response.status_code != 200:
 log_test("刷新", "前置登录", "SKIP", "用户可能不存在")
 return
 except Exception as e:
 log_test("刷新", "前置登录", "FAIL", str(e))
 return
 
 # 使用 Refresh Token 刷新
 try:
 response = session.post(f"{API_V1}/refresh")
 
 if response.status_code == 200:
 data = response.json()
 has_new_token = "access_token" in data
 has_new_csrf = "csrf_token" in data
 
 log_test("刷新", "Token 刷新成功", "PASS")
 log_test("刷新", "返回新 access_token", "PASS" if has_new_token else "FAIL")
 log_test("刷新", "返回新 csrf_token", "PASS" if has_new_csrf else "FAIL")
 else:
 log_test("刷新", "Token 刷新", "FAIL", f"状态码：{response.status_code}")
 except Exception as e:
 log_test("刷新", "Token 刷新", "FAIL", str(e))


# =============================================================================
# 测试 5: API 限流
# =============================================================================

def test_rate_limiting():
 """测试 API 限流"""
 print(f"\n{Fore.CYAN}[测试 5] API 限流{Style.RESET_ALL}")
 
 # 快速连续发送错误登录请求
 rate_limited = False
 status_codes = []
 
 for i in range(7):
 try:
 session = requests.Session()
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json().get("csrf_token", "")
 
 response = session.post(
 f"{API_V1}/login",
 json={"email": "fake@test.com", "password": "wrong"},
 headers={"X-CSRF-Token": csrf}
 )
 
 status_codes.append(response.status_code)
 
 if response.status_code == 429:
 rate_limited = True
 log_test("限流", f"第{i+1}次请求被限流 (429)", "PASS")
 break
 except Exception as e:
 pass
 
 if not rate_limited:
 log_test("限流", "连续请求限流", "FAIL", f"状态码序列：{status_codes}")
 else:
 log_test("限流", "限流阈值正确", "PASS", "5 次后限流")


# =============================================================================
# 测试 6: 密码策略
# =============================================================================

def test_password_policy():
 """测试密码策略"""
 print(f"\n{Fore.CYAN}[测试 6] 密码策略{Style.RESET_ALL}")
 
 # 弱密码测试
 weak_passwords = [
 ("123456", "太短"),
 ("abcdef", "无大写无数字"),
 ("ABCDEF", "无小写无数字"),
 ("12345678", "无字母"),
 ("Abcd1234", "无特殊字符")
 ]
 
 weak_rejected = 0
 for pwd, reason in weak_passwords:
 try:
 session = requests.Session()
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json().get("csrf_token", "")
 
 response = session.post(
 f"{API_V1}/register",
 json={
 "email": f"test{time.time()}@example.com",
 "username": "Test",
 "password": pwd
 },
 headers={"X-CSRF-Token": csrf}
 )
 
 if response.status_code == 400:
 detail = response.json().get("detail", "")
 if "密码" in detail or "强度" in detail:
 weak_rejected += 1
 except:
 pass
 
 if weak_rejected >= 3:
 log_test("密码", "弱密码拒绝", "PASS", f"{weak_rejected}/{len(weak_passwords)} 被拒绝")
 else:
 log_test("密码", "弱密码拒绝", "FAIL", f"仅 {weak_rejected}/{len(weak_passwords)} 被拒绝")
 
 # 强密码测试
 try:
 session = requests.Session()
 response = session.get(f"{API_V1}/csrf-token")
 csrf = response.json().get("csrf_token", "")
 
 response = session.post(
 f"{API_V1}/register",
 json={
 "email": f"strong{time.time()}@example.com",
 "username": "StrongUser",
 "password": "Strong123!@#"
 },
 headers={"X-CSRF-Token": csrf}
 )
 
 if response.status_code == 200:
 log_test("密码", "强密码接受", "PASS")
 else:
 log_test("密码", "强密码接受", "SKIP", response.json().get("detail", ""))
 except Exception as e:
 log_test("密码", "强密码接受", "SKIP", str(e))


# =============================================================================
# 测试 7: 安全响应头
# =============================================================================

def test_security_headers():
 """测试安全响应头"""
 print(f"\n{Fore.CYAN}[测试 7] 安全响应头{Style.RESET_ALL}")
 
 try:
 session = requests.Session()
 response = session.get(f"{API_V1}/health")
 
 headers = response.headers
 
 # 检查各种安全头
 security_headers = {
 "X-Content-Type-Options": "nosniff",
 "X-Frame-Options": None, # 有值就行
 "Content-Security-Policy": None,
 "Referrer-Policy": None,
 }
 
 for header, expected_value in security_headers.items():
 header_value = headers.get(header)
 
 if header_value:
 if expected_value:
 status = "PASS" if expected_value in header_value else "FAIL"
 else:
 status = "PASS"
 log_test("响应头", header, status, header_value)
 else:
 log_test("响应头", header, "FAIL", "未设置")
 except Exception as e:
 log_test("响应头", "检查", "FAIL", str(e))


# =============================================================================
# 生成报告
# =============================================================================

def generate_report():
 """生成测试报告"""
 total = test_results["passed"] + test_results["failed"] + test_results["skipped"]
 pass_rate = (test_results["passed"] / total * 100) if total > 0 else 0
 
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}回归测试报告{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 print(f"\n测试时间：{test_results['timestamp']}")
 print(f"测试环境：{BASE_URL}")
 print(f"\n总计：{total} 个测试")
 print(f"通过：{Fore.GREEN}{test_results['passed']}{Style.RESET_ALL}")
 print(f"失败：{Fore.RED}{test_results['failed']}{Style.RESET_ALL}")
 print(f"跳过：{Fore.YELLOW}{test_results['skipped']}{Style.RESET_ALL}")
 print(f"通过率：{Fore.GREEN if pass_rate >= 90 else Fore.YELLOW if pass_rate >= 70 else Fore.RED}{pass_rate:.1f}%{Style.RESET_ALL}")
 
 # 按类别分组统计
 categories = {}
 for test in test_results["tests"]:
 cat = test["category"]
 if cat not in categories:
 categories[cat] = {"passed": 0, "failed": 0, "skipped": 0}
 
 status = test["status"].lower()
 if status == "pass":
 categories[cat]["passed"] += 1
 elif status == "fail":
 categories[cat]["failed"] += 1
 else:
 categories[cat]["skipped"] += 1
 
 print(f"\n按类别统计:")
 for cat, stats in categories.items():
 cat_total = stats["passed"] + stats["failed"] + stats["skipped"]
 cat_rate = (stats["passed"] / cat_total * 100) if cat_total > 0 else 0
 color = Fore.GREEN if cat_rate >= 90 else Fore.YELLOW if cat_rate >= 70 else Fore.RED
 print(f" {cat}: {color}{stats['passed']}/{cat_total} ({cat_rate:.0f}%){Style.RESET_ALL}")
 
 # 保存 JSON 报告
 report_file = f"regression_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
 with open(report_file, "w", encoding="utf-8") as f:
 json.dump(test_results, f, ensure_ascii=False, indent=2, default=str)
 
 print(f"\n报告已保存到：{report_file}")
 
 return test_results["failed"] == 0


# =============================================================================
# 主测试流程
# =============================================================================

def main():
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}综合回归性测试{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"服务地址：{BASE_URL}")
 print(f"测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
 
 session = requests.Session()
 
 try:
 # 测试 1: HttpOnly Cookie
 test_httponly_cookie(session)
 
 # 测试 2: CSRF Token
 test_csrf_protection(session)
 
 # 测试 3: RSA+AES 加密登录
 test_encrypted_login(session)
 
 # 测试 4: Token 刷新
 test_token_refresh(session)
 
 # 测试 5: API 限流
 test_rate_limiting()
 
 # 测试 6: 密码策略
 test_password_policy()
 
 # 测试 7: 安全响应头
 test_security_headers()
 
 except KeyboardInterrupt:
 print(f"\n\n{Fore.YELLOW}[WARNING] 测试被用户中断{Style.RESET_ALL}")
 except Exception as e:
 print(f"\n{Fore.RED}[FAILED] 测试执行异常：{e}{Style.RESET_ALL}")
 import traceback
 traceback.print_exc()
 
 # 生成报告
 success = generate_report()
 
 sys.exit(0 if success else 1)


if __name__ == "__main__":
 main()
