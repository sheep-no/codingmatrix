#!/usr/bin/env python3
"""
AI Project 功能完整测试脚本

测试范围:
1. Token 生成与验证
2. 项目生成 API (非流式)
3. 项目生成 API (流式)
4. 生成的项目验证
5. 项目清理

使用方法:
 python tests/test_ai_project_full.py
"""

import asyncio
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import httpx
import pytest

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.security import create_access_token
from app.core.config import settings

# 测试配置
TEST_CONFIG = {
 "base_url": "http://localhost:8000",
 "timeout": 300.0, # 5 分钟超时
 "test_requirement": "创建一个简单的 FastAPI 项目，包含一个 GET /hello 端点，返回 {'message': 'Hello World'}",
 "output_base": "./test_projects",
}


class AIProjectTester:
 """AI Project 功能测试器"""
 
 def __init__(self):
 self.base_url = TEST_CONFIG["base_url"]
 self.timeout = TEST_CONFIG["timeout"]
 self.token = None
 self.headers = None
 self.test_projects = []
 
 def setup(self):
 """测试前准备"""
 print("\n" + "="*70)
 print("AI Project 功能完整测试")
 print("="*70)
 
 # 创建测试输出目录
 os.makedirs(TEST_CONFIG["output_base"], exist_ok=True)
 
 # 生成测试 Token
 self.token = create_access_token(
 sub="test_user",
 permission_level="normal"
 )
 self.headers = {
 "Authorization": f"Bearer {self.token}",
 "Content-Type": "application/json"
 }
 
 print(f"\n[PASS] 测试环境初始化完成")
 print(f" - API 地址：{self.base_url}")
 print(f" - Token 生成：成功")
 print(f" - 输出目录：{TEST_CONFIG['output_base']}")
 
 def teardown(self):
 """测试后清理"""
 print("\n" + "="*70)
 print("清理测试文件")
 print("="*70)
 
 for proj_dir in self.test_projects:
 if os.path.exists(proj_dir):
 shutil.rmtree(proj_dir)
 print(f" - 删除：{proj_dir}")
 
 print("\n[PASS] 清理完成")
 
 async def test_generate_project(self):
 """测试 1: 非流式项目生成"""
 print("\n" + "-"*70)
 print("测试 1: 非流式项目生成")
 print("-"*70)
 
 start_time = time.time()
 
 # 生成时间戳作为输出目录
 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
 output_dir = f"{TEST_CONFIG['output_base']}/test_{timestamp}"
 self.test_projects.append(output_dir)
 
 # 请求体
 payload = {
 "requirement": TEST_CONFIG["test_requirement"],
 "model": "deepseek-coder",
 "max_thinking_tokens": 2000,
 "max_output_tokens": 4000,
 "temperature": 0.7,
 "enable_venv_validation": False,
 "session_id": f"test_session_{timestamp}"
 }
 
 print(f"\n请求参数:")
 print(f" - 需求：{TEST_CONFIG['test_requirement'][:50]}...")
 print(f" - 模型：deepseek-coder")
 print(f" - 输出目录：{output_dir}")
 
 async with httpx.AsyncClient(timeout=self.timeout) as client:
 try:
 response = await client.post(
 f"{self.base_url}/api/v1/agent/generate",
 json=payload,
 headers=self.headers
 )
 
 elapsed = time.time() - start_time
 
 if response.status_code == 200:
 result = response.json()
 print(f"\n[PASS] 项目生成成功")
 print(f" - 耗时：{elapsed:.2f}秒")
 print(f" - 创建文件数：{result.get('total_files_created', 0)}")
 print(f" - 输出目录：{result.get('output_dir')}")
 print(f" - 验证通过：{result.get('validation', {}).get('runnable', False)}")
 
 # 验证生成的项目
 await self._verify_project(result.get('output_dir'))
 
 return True
 else:
 print(f"\n[FAIL] 项目生成失败")
 print(f" - 状态码：{response.status_code}")
 print(f" - 错误：{response.text}")
 return False
 
 except httpx.TimeoutException:
 print(f"\n[FAIL] 请求超时 ({self.timeout}秒)")
 return False
 except httpx.ConnectError as e:
 print(f"\n[WARN] 无法连接到服务器")
 print(f" - 错误：{e}")
 print(f" - 提示：请先启动应用 'python -m uvicorn app.main:app --reload'")
 return "skip"
 except Exception as e:
 print(f"\n[FAIL] 测试异常")
 print(f" - 错误：{e}")
 return False
 
 async def test_generate_project_stream(self):
 """测试 2: 流式项目生成"""
 print("\n" + "-"*70)
 print("测试 2: 流式项目生成 (SSE)")
 print("-"*70)
 
 start_time = time.time()
 
 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
 output_dir = f"{TEST_CONFIG['output_base']}/test_stream_{timestamp}"
 self.test_projects.append(output_dir)
 
 payload = {
 "requirement": TEST_CONFIG["test_requirement"],
 "model": "deepseek-coder",
 "max_thinking_tokens": 2000,
 "max_output_tokens": 4000,
 "temperature": 0.7,
 "enable_venv_validation": False,
 "session_id": f"test_stream_{timestamp}"
 }
 
 print(f"\n开始流式生成...")
 
 events_received = []
 
 async with httpx.AsyncClient(timeout=self.timeout) as client:
 try:
 async with client.stream(
 "POST",
 f"{self.base_url}/api/v1/agent/generate_stream",
 json=payload,
 headers=self.headers
 ) as response:
 
 if response.status_code != 200:
 print(f"\n[FAIL] 流式请求失败")
 print(f" - 状态码：{response.status_code}")
 print(f" - 错误：{await response.aread()}")
 return False
 
 print(f"\n[INFO] 开始接收 SSE 事件...")
 
 async for line in response.aiter_lines():
 if line.startswith("data: "):
 data = line[6:]
 if data == "[DONE]":
 break
 
 try:
 event = json.loads(data)
 events_received.append(event)
 event_type = event.get('type', 'unknown')
 
 if event_type == 'thinking':
 content = event.get('content', '')[:50]
 print(f" - [Thinking] {content}...")
 elif event_type == 'step_start':
 step = event.get('step', '?')
 print(f" - [Step {step}] 开始")
 elif event_type == 'file_created':
 file_path = event.get('file_path', '?')
 print(f" - [File] 创建：{file_path}")
 elif event_type == 'complete':
 print(f" - [Complete] 生成完成")
 elif event_type == 'error':
 print(f" - [Error] {event.get('message', '未知错误')}")
 
 except json.JSONDecodeError:
 continue
 
 elapsed = time.time() - start_time
 print(f"\n[PASS] 流式生成完成")
 print(f" - 耗时：{elapsed:.2f}秒")
 print(f" - 接收事件数：{len(events_received)}")
 
 return True
 
 except httpx.TimeoutException:
 print(f"\n[FAIL] 请求超时")
 return False
 except Exception as e:
 print(f"\n[FAIL] 测试异常：{e}")
 return False
 
 async def _verify_project(self, project_dir: str):
 """验证生成的项目"""
 print(f"\n验证生成的项目...")
 print(f" - 目录：{project_dir}")
 
 if not project_dir or not os.path.exists(project_dir):
 print(f" - [WARN] 项目目录不存在，跳过验证")
 return
 
 # 检查关键文件
 expected_files = ["main.py", "requirements.txt", "README.md"]
 found_files = []
 
 for file in expected_files:
 file_path = os.path.join(project_dir, file)
 if os.path.exists(file_path):
 found_files.append(file)
 print(f" - [PASS] 找到文件：{file}")
 else:
 print(f" - [WARN] 未找到文件：{file}")
 
 # 检查文件内容
 main_py = os.path.join(project_dir, "main.py")
 if os.path.exists(main_py):
 with open(main_py, 'r', encoding='utf-8') as f:
 content = f.read()
 if "FastAPI" in content or "fastapi" in content:
 print(f" - [PASS] main.py 包含 FastAPI 代码")
 else:
 print(f" - [WARN] main.py 可能不完整")
 
 # 检查 requirements.txt
 req_file = os.path.join(project_dir, "requirements.txt")
 if os.path.exists(req_file):
 with open(req_file, 'r', encoding='utf-8') as f:
 content = f.read()
 if "fastapi" in content.lower():
 print(f" - [PASS] requirements.txt 包含 fastapi 依赖")
 else:
 print(f" - [WARN] requirements.txt 可能不完整")
 
 print(f"\n项目验证完成：{len(found_files)}/{len(expected_files)} 个关键文件")
 
 async def test_health_check(self):
 """测试 0: 健康检查"""
 print("\n" + "-"*70)
 print("测试 0: API 健康检查")
 print("-"*70)
 
 async with httpx.AsyncClient(timeout=10.0) as client:
 try:
 response = await client.get(f"{self.base_url}/api/v1/health")
 
 if response.status_code == 200:
 print(f"\n[PASS] API 健康检查通过")
 print(f" - 状态：正常运行")
 return True
 else:
 print(f"\n[FAIL] API 健康检查失败")
 print(f" - 状态码：{response.status_code}")
 return False
 except httpx.ConnectError:
 print(f"\n[SKIP] 无法连接到 API 服务器")
 print(f" 提示：请先启动应用 'python -m uvicorn app.main:app --reload'")
 return "skip"
 except Exception as e:
 print(f"\n[FAIL] 测试异常：{e}")
 return False


async def run_tests():
 """运行所有测试"""
 tester = AIProjectTester()
 tester.setup()
 
 results = {}
 
 # 测试 0: 健康检查
 results["health"] = await tester.test_health_check()
 
 if results["health"] == "skip":
 print("\n" + "="*70)
 print("测试跳过：API 服务器未运行")
 print("="*70)
 print("\n运行测试前请先启动 API 服务器:")
 print(" python -m uvicorn app.main:app --reload")
 tester.teardown()
 return 0
 
 if not results["health"]:
 print("\n测试终止：API 不可用")
 tester.teardown()
 return 1
 
 # 测试 1: 非流式生成
 results["generate"] = await tester.test_generate_project()
 
 # 测试 2: 流式生成
 results["stream"] = await tester.test_generate_project_stream()
 
 # 汇总结果
 print("\n" + "="*70)
 print("测试结果汇总")
 print("="*70)
 
 passed = sum(1 for v in results.values() if v is True)
 total = len(results)
 
 print(f"\n总测试数：{total}")
 print(f"通过：{passed}")
 print(f"失败：{total - passed}")
 print(f"通过率：{passed/total*100:.1f}%")
 
 tester.teardown()
 
 if passed == total:
 print("\n[SUCCESS] 所有测试通过!")
 return 0
 else:
 print(f"\n[WARNING] {total - passed} 个测试失败")
 return 1


if __name__ == "__main__":
 exit_code = asyncio.run(run_tests())
 sys.exit(exit_code)
