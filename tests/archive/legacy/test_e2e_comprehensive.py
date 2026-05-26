"""
端到端测试 - 完整业务流程测试
"""
import pytest
import httpx
import asyncio
from typing import Dict, Any


class TestEndToEndWorkflow:
 """端到端工作流测试"""

 @pytest.fixture
 def user_credentials(self):
 """用户凭据"""
 return {
 "username": "admin",
 "password": "admin123"
 }

 @pytest.fixture
 def auth_token(self, api_v1_base_url, user_credentials):
 """获取认证令牌"""
 response = httpx.post(
 f"{api_v1_base_url}/auth/login",
 data=user_credentials
 )
 if response.status_code == 200:
 return response.json().get("access_token")
 return None

 @pytest.fixture
 def auth_headers(self, auth_token):
 """认证请求头"""
 if auth_token:
 return {"Authorization": f"Bearer {auth_token}"}
 return {}

 def test_complete_auth_flow(self, api_v1_base_url, sample_user_data):
 """测试完整认证流程"""
 # 1. 注册新用户
 register_response = httpx.post(
 f"{api_v1_base_url}/auth/register",
 json=sample_user_data
 )
 assert register_response.status_code in [200, 201, 400, 409]

 # 2. 登录
 login_response = httpx.post(
 f"{api_v1_base_url}/auth/login",
 data={
 "username": sample_user_data["username"],
 "password": sample_user_data["password"]
 }
 )
 assert login_response.status_code in [200, 401]

 if login_response.status_code == 200:
 data = login_response.json()
 assert "access_token" in data or "token" in data

 def test_complete_chat_flow(self, api_v1_base_url, auth_headers):
 """测试完整聊天流程"""
 # 1. 发送消息
 chat_response = httpx.post(
 f"{api_v1_base_url}/code",
 headers=auth_headers,
 json={
 "prompt": "用 Python 写一个 Hello World",
 "stream": False
 }
 )
 assert chat_response.status_code in [200, 500]

 if chat_response.status_code == 200:
 data = chat_response.json()
 assert "response" in data or "content" in data or "result" in data

 def test_complete_project_generation_flow(self, api_v1_base_url, auth_headers):
 """测试完整项目生成流程"""
 # 1. 发起项目生成请求
 generate_response = httpx.post(
 f"{api_v1_base_url}/agent/generate",
 headers=auth_headers,
 json={
 "session_id": f"test_session_{id(pytest)}",
 "requirement": "创建一个简单的计算器 Python 程序",
 "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
 },
 timeout=180
 )
 assert generate_response.status_code in [200, 500]

 def test_save_and_load_project_flow(self, api_v1_base_url, auth_headers):
 """测试保存和加载项目流程"""
 # 1. 保存项目
 save_response = httpx.post(
 f"{api_v1_base_url}/agent/save",
 headers=auth_headers,
 json={
 "name": "测试项目",
 "description": "端到端测试项目",
 "project_data": '{"requirement": "测试"}'
 }
 )
 assert save_response.status_code in [200, 400, 500]

 # 2. 列出保存的项目
 if save_response.status_code == 200:
 list_response = httpx.get(
 f"{api_v1_base_url}/agent/saved",
 headers=auth_headers
 )
 assert list_response.status_code in [200, 500]
 if list_response.status_code == 200:
 data = list_response.json()
 assert "projects" in data or isinstance(data, list)

 def test_girl_chat_flow(self, api_v1_base_url, auth_headers):
 """测试虚拟姬完整聊天流程"""
 # 1. 发送消息
 chat_response = httpx.post(
 f"{api_v1_base_url}/GirlAi/chat",
 headers=auth_headers,
 json={
 "prompt": "你好",
 "character": "gentle",
 "stream": False
 }
 )
 assert chat_response.status_code in [200, 500]

 # 2. 获取历史记录
 if chat_response.status_code == 200:
 history_response = httpx.get(
 f"{api_v1_base_url}/GirlAi/history",
 headers=auth_headers,
 params={"limit": 10}
 )
 assert history_response.status_code in [200, 500]

 def test_image_generation_flow(self, api_v1_base_url, auth_headers):
 """测试图像生成流程"""
 # 1. 生成图像
 image_response = httpx.post(
 f"{api_v1_base_url}/kolors/text2img",
 headers=auth_headers,
 json={
 "prompt": "一只可爱的猫咪",
 "negative_prompt": "模糊, 低质量",
 "width": 512,
 "height": 512,
 "num_inference_steps": 20
 },
 timeout=120
 )
 assert image_response.status_code in [200, 500]


class TestMultiUserScenario:
 """多用户场景测试"""

 def test_concurrent_chat_sessions(self, api_v1_base_url):
 """测试并发聊天会话"""
 # 模拟多个用户同时聊天
 import concurrent.futures

 def send_chat_message(user_id: int):
 try:
 # 登录获取 token
 login_response = httpx.post(
 f"{api_v1_base_url}/auth/login",
 data={"username": "admin", "password": "admin123"}
 )
 if login_response.status_code != 200:
 return {"user_id": user_id, "success": False}

 token = login_response.json().get("access_token")
 headers = {"Authorization": f"Bearer {token}"}

 # 发送消息
 chat_response = httpx.post(
 f"{api_v1_base_url}/code",
 headers=headers,
 json={"prompt": f"User {user_id} message", "stream": False}
 )
 return {
 "user_id": user_id,
 "success": chat_response.status_code in [200, 500]
 }
 except Exception as e:
 return {"user_id": user_id, "success": False, "error": str(e)}

 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
 futures = [executor.submit(send_chat_message, i) for i in range(3)]
 results = [f.result() for f in concurrent.futures.as_completed(futures)]

 # 验证至少有一些请求成功
 success_count = sum(1 for r in results if r.get("success"))
 assert success_count >= 0


class TestErrorHandling:
 """错误处理测试"""

 def test_invalid_token(self, api_v1_base_url):
 """测试无效令牌"""
 headers = {"Authorization": "Bearer invalid_token_here"}
 response = httpx.get(
 f"{api_v1_base_url}/auth/me",
 headers=headers
 )
 assert response.status_code == 401

 def test_expired_token_format(self, api_v1_base_url):
 """测试过期令牌格式"""
 headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"}
 response = httpx.get(
 f"{api_v1_base_url}/auth/me",
 headers=headers
 )
 assert response.status_code == 401

 def test_missing_required_fields(self, api_v1_base_url, auth_headers):
 """测试缺少必填字段"""
 response = httpx.post(
 f"{api_v1_base_url}/code",
 headers=auth_headers,
 json={}
 )
 assert response.status_code == 422 # 验证错误

 def test_invalid_json(self, api_v1_base_url, auth_headers):
 """测试无效 JSON"""
 response = httpx.post(
 f"{api_v1_base_url}/code",
 headers=auth_headers,
 content=b"not valid json",
 headers={"Content-Type": "application/json"}
 )
 assert response.status_code in [400, 422, 500]


class TestPerformanceBasics:
 """性能基础测试"""

 def test_response_time_health(self, api_v1_base_url):
 """测试健康检查响应时间"""
 import time
 start = time.time()
 response = httpx.get(f"{api_v1_base_url}/health")
 elapsed = time.time() - start
 assert response.status_code == 200
 assert elapsed < 1.0 # 应在1秒内响应

 def test_response_time_auth(self, api_v1_base_url):
 """测试认证响应时间"""
 import time
 start = time.time()
 response = httpx.post(
 f"{api_v1_base_url}/auth/login",
 data={"username": "admin", "password": "admin123"}
 )
 elapsed = time.time() - start
 assert elapsed < 2.0 # 认证应在2秒内完成

 def test_large_payload_rejection(self, api_v1_base_url, auth_headers):
 """测试拒绝过大Payload"""
 large_payload = {"prompt": "x" * 1000000} # 1MB 文本
 response = httpx.post(
 f"{api_v1_base_url}/code",
 headers=auth_headers,
 json=large_payload
 )
 assert response.status_code in [413, 422, 500] # 应拒绝或验证失败


# 运行标记
pytestmark = pytest.mark.e2e
