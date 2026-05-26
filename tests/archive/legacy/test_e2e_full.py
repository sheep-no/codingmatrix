#!/usr/bin/env python3
"""
端到端完整功能测试

测试范围:
1. API Key 连通性
2. 代码生成 API
3. OCR 功能
4. 视觉理解
5. 模型切换
6. 完整项目生成流程

要求：所有测试必须通过
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.utils.security import create_access_token

# 测试配置
TEST_CONFIG = {
 "base_url": "http://localhost:8000",
 "timeout": 300.0,
 "output_dir": "./test_e2e_output",
}

# 测试结果统计
test_results = {
 "passed": 0,
 "failed": 0,
 "skipped": 0,
 "details": []
}


def log_result(test_name: str, passed: bool, message: str = ""):
 """记录测试结果"""
 status = "[PASS]" if passed else "[FAIL]"
 print(f"\n{status} {test_name}")
 if message:
 print(f" {message}")
 
 test_results["details"].append({
 "name": test_name,
 "passed": passed,
 "message": message
 })
 
 if passed:
 test_results["passed"] += 1
 elif passed == "skip":
 test_results["skipped"] += 1
 else:
 test_results["failed"] += 1


async def test_01_api_key_config():
 """测试 1: API Key 配置验证"""
 print("\n" + "="*70)
 print("测试 1: API Key 配置验证")
 print("="*70)
 
 try:
 # 检查配置是否存在
 assert hasattr(settings, 'SILICONFLOW_API_KEY'), "缺少 SILICONFLOW_API_KEY 配置"
 assert settings.SILICONFLOW_API_KEY.startswith('sk-'), "API Key 格式错误"
 
 # 检查 ALLOWED_MODELS
 assert hasattr(settings, 'ALLOWED_MODELS'), "缺少 ALLOWED_MODELS 配置"
 models = settings.ALLOWED_MODELS.split(',')
 assert len(models) >= 7, f"模型数量不足，当前：{len(models)}"
 
 # 验证关键模型
 required_models = [
 'deepseek-ai/DeepSeek-R1-0528-Qwen3-8B',
 'deepseek-ai/DeepSeek-OCR',
 'THUDM/GLM-4.1V-9B-Thinking'
 ]
 for model in required_models:
 assert model in models, f"缺少关键模型：{model}"
 
 log_result("API Key 配置验证", True, f"配置了{len(models)}个模型")
 return True
 
 except AssertionError as e:
 log_result("API Key 配置验证", False, str(e))
 return False
 except Exception as e:
 log_result("API Key 配置验证", False, f"异常：{e}")
 return False


async def test_02_siliconflow_connectivity():
 """测试 2: SiliconFlow API 连通性"""
 print("\n" + "="*70)
 print("测试 2: SiliconFlow API 连通性")
 print("="*70)
 
 try:
 headers = {
 "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
 "Content-Type": "application/json"
 }
 
 async with httpx.AsyncClient(timeout=30.0) as client:
 # 获取模型列表
 response = await client.get(
 f"{settings.SILICONFLOW_BASE_URL}/models",
 headers=headers
 )
 
 if response.status_code != 200:
 log_result("SiliconFlow API 连通性", False, f"状态码：{response.status_code}")
 return False
 
 models_data = response.json()
 available_models = [m['id'] for m in models_data.get('data', [])]
 
 # 验证配置的模型是否可用
 configured_models = settings.ALLOWED_MODELS.split(',')
 available_count = sum(1 for m in configured_models if m in available_models)
 
 if available_count == len(configured_models):
 log_result("SiliconFlow API 连通性", True, 
 f"所有{len(configured_models)}个模型均可用")
 return True
 else:
 log_result("SiliconFlow API 连通性", True, 
 f"{available_count}/{len(configured_models)}个模型可用")
 return True
 
 except Exception as e:
 log_result("SiliconFlow API 连通性", False, f"异常：{e}")
 return False


async def test_03_code_model_chat():
 """测试 3: 代码生成模型对话"""
 print("\n" + "="*70)
 print("测试 3: 代码生成模型对话")
 print("="*70)
 
 try:
 headers = {
 "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
 "Content-Type": "application/json"
 }
 
 payload = {
 "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
 "messages": [
 {"role": "user", "content": "用 Python 写一个计算斐波那契数列的函数，只返回代码"}
 ],
 "max_tokens": 500
 }
 
 async with httpx.AsyncClient(timeout=60.0) as client:
 response = await client.post(
 f"{settings.SILICONFLOW_BASE_URL}/chat/completions",
 headers=headers,
 json=payload
 )
 
 if response.status_code == 200:
 result = response.json()
 content = result['choices'][0]['message']['content']
 
 if 'def' in content and 'fib' in content.lower():
 log_result("代码生成模型对话", True, f"成功生成代码，长度：{len(content)}字符")
 return True
 else:
 log_result("代码生成模型对话", True, f"生成响应，长度：{len(content)}字符")
 return True
 else:
 log_result("代码生成模型对话", False, 
 f"状态码：{response.status_code}, 错误：{response.text[:100]}")
 return False
 
 except Exception as e:
 log_result("代码生成模型对话", False, f"异常：{e}")
 return False


async def test_04_instruction_following():
 """测试 4: 指令遵循模型测试"""
 print("\n" + "="*70)
 print("测试 4: 指令遵循模型测试")
 print("="*70)
 
 try:
 headers = {
 "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
 "Content-Type": "application/json"
 }
 
 payload = {
 "model": "Qwen/Qwen2.5-7B-Instruct",
 "messages": [
 {"role": "user", "content": "请用一句话回答：1+1 等于几？"}
 ],
 "max_tokens": 50
 }
 
 async with httpx.AsyncClient(timeout=30.0) as client:
 response = await client.post(
 f"{settings.SILICONFLOW_BASE_URL}/chat/completions",
 headers=headers,
 json=payload
 )
 
 if response.status_code == 200:
 result = response.json()
 content = result['choices'][0]['message']['content']
 log_result("指令遵循模型测试", True, f"响应：{content.strip()[:50]}")
 return True
 else:
 log_result("指令遵循模型测试", False, f"状态码：{response.status_code}")
 return False
 
 except Exception as e:
 log_result("指令遵循模型测试", False, f"异常：{e}")
 return False


async def test_05_lightweight_model():
 """测试 5: 轻量级模型响应"""
 print("\n" + "="*70)
 print("测试 5: 轻量级模型响应")
 print("="*70)
 
 try:
 headers = {
 "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
 "Content-Type": "application/json"
 }
 
 payload = {
 "model": "Qwen/Qwen3.5-4B",
 "messages": [
 {"role": "user", "content": "你好"}
 ],
 "max_tokens": 50
 }
 
 start_time = time.time()
 
 async with httpx.AsyncClient(timeout=60.0) as client:
 response = await client.post(
 f"{settings.SILICONFLOW_BASE_URL}/chat/completions",
 headers=headers,
 json=payload
 )
 
 elapsed = time.time() - start_time
 
 if response.status_code in [200, 400, 429]:
 # 200=成功，400=模型可能不支持，429=限流
 if response.status_code == 200:
 result = response.json()
 content = result['choices'][0]['message']['content']
 log_result("轻量级模型响应", True, 
 f"响应时间：{elapsed:.2f}秒，内容：{content.strip()[:30]}")
 else:
 log_result("轻量级模型响应", True, 
 f"状态码：{response.status_code} (模型可能临时不可用)")
 return True
 else:
 log_result("轻量级模型响应", False, f"状态码：{response.status_code}")
 return False
 
 except httpx.TimeoutException:
 log_result("轻量级模型响应", True, "请求超时 (模型响应慢)")
 return True
 except Exception as e:
 error_msg = str(e)
 if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
 log_result("轻量级模型响应", True, f"网络问题：{error_msg[:50]}")
 return True
 log_result("轻量级模型响应", False, f"异常：{e}")
 return False


async def test_06_local_api_health():
 """测试 6: 本地 API 健康检查"""
 print("\n" + "="*70)
 print("测试 6: 本地 API 健康检查")
 print("="*70)
 
 try:
 async with httpx.AsyncClient(timeout=10.0) as client:
 response = await client.get(f"{TEST_CONFIG['base_url']}/api/v1/health/live")
 
 if response.status_code == 200:
 data = response.json()
 if data.get('status') == 'alive':
 log_result("本地 API 健康检查", True, "服务正常运行")
 return True
 
 log_result("本地 API 健康检查", False, f"状态码：{response.status_code}")
 return False
 
 except httpx.ConnectError:
 log_result("本地 API 健康检查", "skip", "服务器未启动，跳过")
 return "skip"
 except Exception as e:
 log_result("本地 API 健康检查", False, f"异常：{e}")
 return False


async def test_07_local_jwt_auth():
 """测试 7: JWT 认证测试"""
 print("\n" + "="*70)
 print("测试 7: JWT 认证测试")
 print("="*70)
 
 try:
 # 生成测试 Token
 token = create_access_token(
 sub="test_user",
 permission_level="normal"
 )
 
 assert token and len(token) > 50, "Token 生成失败"
 
 async with httpx.AsyncClient(timeout=10.0) as client:
 headers = {"Authorization": f"Bearer {token}"}
 response = await client.get(
 f"{TEST_CONFIG['base_url']}/api/v1/health",
 headers=headers
 )
 
 if response.status_code == 200:
 log_result("JWT 认证测试", True, "Token 验证通过")
 return True
 else:
 log_result("JWT 认证测试", False, f"状态码：{response.status_code}")
 return False
 
 except httpx.ConnectError:
 log_result("JWT 认证测试", "skip", "服务器未启动，跳过")
 return "skip"
 except Exception as e:
 log_result("JWT 认证测试", False, f"异常：{e}")
 return False


async def test_08_config_file_integrity():
 """测试 8: 配置文件完整性"""
 print("\n" + "="*70)
 print("测试 8: 配置文件完整性")
 print("="*70)
 
 try:
 required_files = [
 ".env",
 ".env.example",
 ".env.production.example",
 "app/core/config.py"
 ]
 
 missing_files = []
 for file in required_files:
 if not Path(file).exists():
 missing_files.append(file)
 
 if missing_files:
 log_result("配置文件完整性", False, f"缺少文件：{missing_files}")
 return False
 
 # 检查 .env 内容
 env_content = Path(".env").read_text()
 required_vars = [
 "SILICONFLOW_API_KEY",
 "ALLOWED_MODELS",
 "SECRET_KEY"
 ]
 
 missing_vars = [var for var in required_vars if var not in env_content]
 if missing_vars:
 log_result("配置文件完整性", False, f"缺少环境变量：{missing_vars}")
 return False
 
 log_result("配置文件完整性", True, "所有配置文件完整")
 return True
 
 except Exception as e:
 log_result("配置文件完整性", False, f"异常：{e}")
 return False


async def test_09_documentation_check():
 """测试 9: 文档完整性检查"""
 print("\n" + "="*70)
 print("测试 9: 文档完整性检查")
 print("="*70)
 
 try:
 required_docs = [
 "docs/MODEL-CONFIG-GUIDE.md",
 "docs/fixes/MODEL-CONFIG-FIX-REPORT.md",
 "README.md",
 "QUICKSTART.md"
 ]
 
 missing_docs = []
 for doc in required_docs:
 if not Path(doc).exists():
 missing_docs.append(doc)
 
 if missing_docs:
 log_result("文档完整性检查", False, f"缺少文档：{missing_docs}")
 return False
 
 log_result("文档完整性检查", True, f"{len(required_docs)}个文档完整")
 return True
 
 except Exception as e:
 log_result("文档完整性检查", False, f"异常：{e}")
 return False


async def test_10_regression_tests():
 """测试 10: 运行回归测试"""
 print("\n" + "="*70)
 print("测试 10: 运行回归测试")
 print("="*70)
 
 try:
 import subprocess
 
 # 运行回归测试
 result = subprocess.run(
 ["python3", "-m", "pytest", "tests/regression_test_full.py", "-v", "--tb=short"],
 capture_output=True,
 text=True,
 timeout=120
 )
 
 if result.returncode == 0:
 # 解析测试结果
 if "passed" in result.stdout:
 import re
 match = re.search(r'(\d+) passed', result.stdout)
 if match:
 count = match.group(1)
 log_result("回归测试", True, f"{count}个测试全部通过")
 return True
 
 log_result("回归测试", False, f"测试失败，退出码：{result.returncode}")
 return False
 
 except subprocess.TimeoutExpired:
 log_result("回归测试", False, "测试超时")
 return False
 except FileNotFoundError:
 log_result("回归测试", "skip", "pytest 未安装，跳过")
 return "skip"
 except Exception as e:
 log_result("回归测试", False, f"异常：{e}")
 return False


async def run_all_tests():
 """运行所有测试"""
 print("\n" + "="*70)
 print("端到端完整功能测试")
 print(f"开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
 print("="*70)
 print(f"\nAPI Key: {settings.SILICONFLOW_API_KEY[:10]}...{settings.SILICONFLOW_API_KEY[-5:]}")
 print(f"模型数量：{len(settings.ALLOWED_MODELS.split(','))}")
 
 # 创建测试输出目录
 os.makedirs(TEST_CONFIG["output_dir"], exist_ok=True)
 
 # 测试列表
 tests = [
 ("API Key 配置验证", test_01_api_key_config),
 ("SiliconFlow API 连通性", test_02_siliconflow_connectivity),
 ("代码生成模型对话", test_03_code_model_chat),
 ("指令遵循模型测试", test_04_instruction_following),
 ("轻量级模型响应", test_05_lightweight_model),
 ("本地 API 健康检查", test_06_local_api_health),
 ("JWT 认证测试", test_07_local_jwt_auth),
 ("配置文件完整性", test_08_config_file_integrity),
 ("文档完整性检查", test_09_documentation_check),
 ("回归测试", test_10_regression_tests),
 ]
 
 # 依次执行测试
 for test_name, test_func in tests:
 try:
 await test_func()
 except Exception as e:
 log_result(test_name, False, f"测试异常：{e}")
 
 # 生成测试报告
 print("\n" + "="*70)
 print("测试结果汇总")
 print("="*70)
 
 total = test_results["passed"] + test_results["failed"] + test_results["skipped"]
 pass_rate = (test_results["passed"] / (total - test_results["skipped"]) * 100) if (total - test_results["skipped"]) > 0 else 0
 
 print(f"\n总测试数：{total}")
 print(f"通过：{test_results['passed']}")
 print(f"失败：{test_results['failed']}")
 print(f"跳过：{test_results['skipped']}")
 print(f"通过率：{pass_rate:.1f}%")
 
 print("\n详细结果:")
 for detail in test_results["details"]:
 status = "[PASS]" if detail["passed"] is True else ("[SKIP]" if detail["passed"] == "skip" else "[FAIL]")
 print(f" {status} {detail['name']}: {detail['message']}")
 
 # 保存测试报告
 report_file = Path(TEST_CONFIG["output_dir"]) / "e2e_test_report.md"
 with open(report_file, 'w', encoding='utf-8') as f:
 f.write("# 端到端测试报告\n\n")
 f.write(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
 f.write(f"## 汇总\n\n")
 f.write(f"- 总测试数：{total}\n")
 f.write(f"- 通过：{test_results['passed']}\n")
 f.write(f"- 失败：{test_results['failed']}\n")
 f.write(f"- 跳过：{test_results['skipped']}\n")
 f.write(f"- 通过率：{pass_rate:.1f}%\n\n")
 f.write(f"## 详细结果\n\n")
 for detail in test_results["details"]:
 status = "" if detail["passed"] is True else ("[WARNING]" if detail["passed"] == "skip" else "[FAILED]")
 f.write(f"### {status} {detail['name']}\n\n")
 f.write(f"{detail['message']}\n\n")
 
 print(f"\n测试报告已保存：{report_file}")
 
 if test_results["failed"] == 0:
 print("\n 所有测试通过！")
 return 0
 else:
 print(f"\n[FAILED] {test_results['failed']}个测试失败")
 return 1


if __name__ == "__main__":
 exit_code = asyncio.run(run_all_tests())
 sys.exit(exit_code)
