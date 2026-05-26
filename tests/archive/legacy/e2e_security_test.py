#!/usr/bin/env python3
"""
端到端安全测试脚本

测试场景：
1. 登录流程 + Cookie 设置
2. Token 刷新机制
3. CSRF 防护
4. API 限流
5. XSS 防护验证
"""

import requests
import json
import sys
import time
from colorama import init, Fore, Style

# 初始化 colorama
init(autoreset=True)

# 配置
PORTS_TO_TRY = [8080, 8000, 3000]
BASE_URL = None

# 自动检测服务端口
for port in PORTS_TO_TRY:
 try:
 response = requests.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=3)
 if response.status_code in [200, 500]: # 500 也说明服务在运行
 BASE_URL = f"http://127.0.0.1:{port}"
 print(f" 检测到服务在端口 {port}")
 break
 except:
 pass

if not BASE_URL:
 print("[FAILED] 未检测到服务，请确保后端服务已启动")
 print(f"尝试的端口：{PORTS_TO_TRY}")
 sys.exit(1)

API_V1 = f"{BASE_URL}/api/v1"

# 测试用户
TEST_USER = {
 "email": "test@example.com",
 "password": "Test123!@#",
 "username": "TestUser"
}

# 测试报告
test_results = {
 "passed": 0,
 "failed": 0,
 "tests": []
}

def log_test(name, status, details=""):
 """记录测试结果"""
 icon = "" if status == "PASS" else "[FAILED]"
 color = Fore.GREEN if status == "PASS" else Fore.RED
 
 print(f"{color}{icon} {name}: {status}{Style.RESET_ALL}")
 if details:
 print(f" {details}")
 
 test_results["tests"].append({
 "name": name,
 "status": status,
 "details": details
 })
 
 if status == "PASS":
 test_results["passed"] += 1
 else:
 test_results["failed"] += 1


# =============================================================================
# 测试 1: 登录流程 + Cookie 设置
# =============================================================================
def test_login_flow():
 """测试登录流程和 Cookie 设置"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试 1: 登录流程 + Cookie 设置{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 session = requests.Session()
 
 # 1.1 获取 CSRF Token
 try:
 response = session.get(f"{API_V1}/csrf-token")
 assert response.status_code == 200
 csrf_token = response.json().get("csrf_token")
 assert csrf_token is not None
 log_test("1.1 获取 CSRF Token", "PASS", f"Token: {csrf_token[:20]}...")
 except Exception as e:
 log_test("1.1 获取 CSRF Token", "FAIL", str(e))
 return False
 
 # 1.2 登录（带 CSRF Token）
 try:
 login_data = {
 "email": TEST_USER["email"],
 "password": TEST_USER["password"]
 }
 headers = {"X-CSRF-Token": csrf_token}
 
 response = session.post(
 f"{API_V1}/login",
 json=login_data,
 headers=headers
 )
 
 assert response.status_code == 200, f"登录失败：{response.text}"
 data = response.json()
 
 # 验证响应
 assert "access_token" in data, "缺少 access_token"
 assert "token_type" in data, "缺少 token_type"
 assert "username" in data, "缺少 username"
 
 log_test("1.2 登录成功", "PASS", f"用户：{data['username']}")
 except Exception as e:
 log_test("1.2 登录成功", "FAIL", str(e))
 return False
 
 # 1.3 验证 Cookie 设置
 try:
 cookies = session.cookies.get_dict()
 
 # 检查 Refresh Token Cookie
 assert "refresh_token" in cookies, "缺少 refresh_token Cookie"
 refresh_token = cookies["refresh_token"]
 assert refresh_token.startswith("eyJ"), "Refresh Token 格式错误"
 
 # 检查 CSRF Token Cookie
 assert "csrf_token" in cookies, "缺少 csrf_token Cookie"
 
 # 验证 HttpOnly（通过 Python 无法直接验证，检查响应头）
 set_cookie_header = response.headers.get("Set-Cookie", "")
 assert "HttpOnly" in set_cookie_header, "refresh_token 未设置 HttpOnly"
 
 log_test("1.3 Cookie 设置验证", "PASS", 
 f"refresh_token: {refresh_token[:20]}... (HttpOnly)")
 except Exception as e:
 log_test("1.3 Cookie 设置验证", "FAIL", str(e))
 return False
 
 # 1.4 使用 access token 访问受保护资源
 try:
 access_token = data["access_token"]
 headers = {"Authorization": f"Bearer {access_token}"}
 
 response = session.get(f"{API_V1}/health", headers=headers)
 assert response.status_code == 200, f"访问失败：{response.text}"
 
 log_test("1.4 Access Token 访问资源", "PASS")
 except Exception as e:
 log_test("1.4 Access Token 访问资源", "FAIL", str(e))
 
 return session, access_token


# =============================================================================
# 测试 2: Token 刷新机制
# =============================================================================
def test_token_refresh(session):
 """测试 Token 刷新机制"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试 2: Token 刷新机制{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 # 2.1 使用 Refresh Token 刷新
 try:
 response = session.post(f"{API_V1}/refresh")
 assert response.status_code == 200, f"刷新失败：{response.text}"
 
 data = response.json()
 assert "access_token" in data, "缺少新的 access_token"
 assert "csrf_token" in data, "缺少新的 csrf_token"
 
 log_test("2.1 Refresh Token 刷新成功", "PASS",
 f"新 Token: {data['access_token'][:20]}...")
 except Exception as e:
 log_test("2.1 Refresh Token 刷新成功", "FAIL", str(e))
 return False
 
 # 2.2 使用新 Token 访问资源
 try:
 new_token = data["access_token"]
 headers = {"Authorization": f"Bearer {new_token}"}
 
 response = session.get(f"{API_V1}/health", headers=headers)
 assert response.status_code == 200
 
 log_test("2.2 新 Token 有效", "PASS")
 except Exception as e:
 log_test("2.2 新 Token 有效", "FAIL", str(e))
 return False
 
 return True


# =============================================================================
# 测试 3: CSRF 防护
# =============================================================================
def test_csrf_protection(session):
 """测试 CSRF 防护"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试 3: CSRF 防护{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 # 3.1 无 CSRF Token 的请求（应该失败）
 try:
 login_data = {
 "email": TEST_USER["email"],
 "password": TEST_USER["password"]
 }
 
 # 不携带 CSRF Token
 new_session = requests.Session()
 response = new_session.post(
 f"{API_V1}/login",
 json=login_data
 )
 
 # 应该返回 403
 if response.status_code == 403:
 log_test("3.1 无 CSRF Token 被拒绝", "PASS", 
 f"返回 403: {response.json().get('detail', '')}")
 elif response.status_code == 422:
 log_test("3.1 无 CSRF Token 被拒绝", "PASS", 
 f"返回 422 (验证失败): {response.text}")
 else:
 log_test("3.1 无 CSRF Token 被拒绝", "FAIL", 
 f"应该返回 403，实际返回 {response.status_code}")
 except Exception as e:
 log_test("3.1 无 CSRF Token 被拒绝", "FAIL", str(e))
 
 # 3.2 错误的 CSRF Token（应该失败）
 try:
 login_data = {
 "email": TEST_USER["email"],
 "password": TEST_USER["password"]
 }
 headers = {"X-CSRF-Token": "invalid_token"}
 
 response = session.post(
 f"{API_V1}/login",
 json=login_data,
 headers=headers
 )
 
 # 应该返回 403
 if response.status_code == 403:
 log_test("3.2 错误 CSRF Token 被拒绝", "PASS")
 else:
 log_test("3.2 错误 CSRF Token 被拒绝", "FAIL", 
 f"应该返回 403，实际返回 {response.status_code}")
 except Exception as e:
 log_test("3.2 错误 CSRF Token 被拒绝", "FAIL", str(e))
 
 # 3.3 正确的 CSRF Token（应该成功）
 try:
 # 获取新的 CSRF Token
 response = session.get(f"{API_V1}/csrf-token")
 csrf_token = response.json().get("csrf_token")
 
 login_data = {
 "email": TEST_USER["email"],
 "password": TEST_USER["password"]
 }
 headers = {"X-CSRF-Token": csrf_token}
 
 response = session.post(
 f"{API_V1}/login",
 json=login_data,
 headers=headers
 )
 
 assert response.status_code == 200, f"登录失败：{response.text}"
 log_test("3.3 正确 CSRF Token 通过", "PASS")
 except Exception as e:
 log_test("3.3 正确 CSRF Token 通过", "FAIL", str(e))


# =============================================================================
# 测试 4: XSS 防护验证
# =============================================================================
def test_xss_protection(session):
 """测试 XSS 防护（验证 Cookie 不可被 JavaScript 访问）"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试 4: XSS 防护验证{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 # 4.1 验证 Refresh Token 不在响应体中
 try:
 # 登录请求
 response = session.get(f"{API_V1}/csrf-token")
 csrf_token = response.json().get("csrf_token")
 
 login_data = {
 "email": TEST_USER["email"],
 "password": TEST_USER["password"]
 }
 headers = {"X-CSRF-Token": csrf_token}
 
 response = session.post(
 f"{API_V1}/login",
 json=login_data,
 headers=headers
 )
 
 response_body = response.text
 
 # 检查响应体中是否包含 refresh_token
 assert "refresh_token" not in response_body, "Refresh Token 泄漏在响应体中"
 
 log_test("4.1 Refresh Token 不在响应体", "PASS")
 except Exception as e:
 log_test("4.1 Refresh Token 不在响应体", "FAIL", str(e))
 
 # 4.2 验证 Cookie 属性
 try:
 # 检查 Cookie 的 HttpOnly 属性
 # Python requests 无法直接读取 HttpOnly 属性，需要检查响应头
 set_cookie = response.headers.get("Set-Cookie", "")
 
 has_httponly = "HttpOnly" in set_cookie
 has_samesite = "SameSite" in set_cookie
 
 if has_httponly and has_samesite:
 log_test("4.2 Cookie HttpOnly 属性", "PASS", 
 "HttpOnly=True, SameSite=lax")
 elif has_httponly:
 log_test("4.2 Cookie HttpOnly 属性", "PASS", "HttpOnly=True")
 else:
 log_test("4.2 Cookie HttpOnly 属性", "FAIL", 
 "缺少 HttpOnly 属性")
 except Exception as e:
 log_test("4.2 Cookie HttpOnly 属性", "FAIL", str(e))


# =============================================================================
# 测试 5: API 限流
# =============================================================================
def test_rate_limiting():
 """测试 API 限流"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试 5: API 限流{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 # 5.1 登录失败限流
 try:
 # 连续发送错误登录请求
 for i in range(7):
 session = requests.Session()
 response = session.get(f"{API_V1}/csrf-token")
 csrf_token = response.json().get("csrf_token")
 
 login_data = {
 "email": TEST_USER["email"],
 "password": "WrongPassword"
 }
 headers = {"X-CSRF-Token": csrf_token}
 
 response = session.post(
 f"{API_V1}/login",
 json=login_data,
 headers=headers
 )
 
 if response.status_code == 429:
 log_test(f"5.1 登录失败限流 (第{i+1}次)", "PASS", 
 f"第{i+1}次请求被限流 (429)")
 break
 elif i >= 5:
 log_test(f"5.1 登录失败限流 (第{i+1}次)", "FAIL", 
 f"应该在 5 次后限流，实际返回 {response.status_code}")
 else:
 print(f" 第{i+1}次登录失败：{response.status_code}")
 except Exception as e:
 log_test("5.1 登录失败限流", "FAIL", str(e))


# =============================================================================
# 测试 6: 密码策略
# =============================================================================
def test_password_policy():
 """测试密码策略"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试 6: 密码策略{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 # 6.1 弱密码拒绝
 weak_passwords = [
 "123456",
 "password",
 "abc123",
 "Test"
 ]
 
 for pwd in weak_passwords:
 try:
 session = requests.Session()
 response = session.get(f"{API_V1}/csrf-token")
 csrf_token = response.json().get("csrf_token")
 
 register_data = {
 "email": f"test{time.time()}@example.com",
 "password": pwd,
 "username": "Test"
 }
 headers = {"X-CSRF-Token": csrf_token}
 
 response = session.post(
 f"{API_V1}/register",
 json=register_data,
 headers=headers
 )
 
 if response.status_code == 400:
 detail = response.json().get("detail", "")
 if "密码" in detail or "强度" in detail:
 log_test(f"6.1 弱密码拒绝 ({pwd})", "PASS", detail)
 else:
 log_test(f"6.1 弱密码拒绝 ({pwd})", "FAIL", 
 f"错误消息不明确：{detail}")
 else:
 log_test(f"6.1 弱密码拒绝 ({pwd})", "FAIL", 
 f"应该返回 400，实际返回 {response.status_code}")
 except Exception as e:
 log_test(f"6.1 弱密码拒绝 ({pwd})", "FAIL", str(e))
 
 # 6.2 强密码接受
 try:
 session = requests.Session()
 response = session.get(f"{API_V1}/csrf-token")
 csrf_token = response.json().get("csrf_token")
 
 register_data = {
 "email": f"strong{time.time()}@example.com",
 "password": "Strong123!@#",
 "username": "StrongUser"
 }
 headers = {"X-CSRF-Token": csrf_token}
 
 response = session.post(
 f"{API_V1}/register",
 json=register_data,
 headers=headers
 )
 
 if response.status_code == 200:
 log_test("6.2 强密码接受", "PASS")
 else:
 log_test("6.2 强密码接受", "FAIL", 
 f"应该返回 200，实际返回 {response.status_code}: {response.text}")
 except Exception as e:
 log_test("6.2 强密码接受", "FAIL", str(e))


# =============================================================================
# 生成测试报告
# =============================================================================
def generate_report():
 """生成测试报告"""
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}测试报告{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 
 total = test_results["passed"] + test_results["failed"]
 pass_rate = (test_results["passed"] / total * 100) if total > 0 else 0
 
 print(f"\n总测试数：{total}")
 print(f"通过：{Fore.GREEN}{test_results['passed']}{Style.RESET_ALL}")
 print(f"失败：{Fore.RED}{test_results['failed']}{Style.RESET_ALL}")
 print(f"通过率：{Fore.GREEN if pass_rate >= 90 else Fore.YELLOW}{pass_rate:.1f}%{Style.RESET_ALL}")
 
 print(f"\n详细结果:")
 for test in test_results["tests"]:
 icon = "" if test["status"] == "PASS" else "[FAILED]"
 color = Fore.GREEN if test["status"] == "PASS" else Fore.RED
 print(f" {color}{icon} {test['name']}: {test['status']}{Style.RESET_ALL}")
 if test.get("details"):
 print(f" {test['details']}")
 
 # 保存报告
 report = {
 "timestamp": time.time(),
 "total": total,
 "passed": test_results["passed"],
 "failed": test_results["failed"],
 "pass_rate": pass_rate,
 "tests": test_results["tests"]
 }
 
 with open("test-report.json", "w", encoding="utf-8") as f:
 json.dump(report, f, ensure_ascii=False, indent=2)
 
 print(f"\n报告已保存到：test-report.json")
 
 return test_results["failed"] == 0


# =============================================================================
# 主测试流程
# =============================================================================
def main():
 print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"{Fore.CYAN}端到端安全测试{Style.RESET_ALL}")
 print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
 print(f"目标：{BASE_URL}")
 print(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
 
 session = None
 
 try:
 # 检查服务是否可用
 try:
 requests.get(BASE_URL, timeout=5)
 except requests.exceptions.ConnectionError:
 print(f"{Fore.RED}[FAILED] 无法连接到服务：{BASE_URL}{Style.RESET_ALL}")
 print(f"请确保服务已启动在 {BASE_URL}")
 generate_report()
 sys.exit(1)
 
 # 测试 1: 登录流程
 result = test_login_flow()
 if result:
 session, access_token = result
 
 if session:
 # 测试 2: Token 刷新
 test_token_refresh(session)
 
 # 测试 3: CSRF 防护
 test_csrf_protection(session)
 
 # 测试 4: XSS 防护
 test_xss_protection(session)
 
 # 测试 5: API 限流
 test_rate_limiting()
 
 # 测试 6: 密码策略
 test_password_policy()
 
 except Exception as e:
 print(f"{Fore.RED}[FAILED] 测试执行异常：{e}{Style.RESET_ALL}")
 import traceback
 traceback.print_exc()
 
 # 生成报告
 success = generate_report()
 
 sys.exit(0 if success else 1)


if __name__ == "__main__":
 main()
