#!/usr/bin/env python3
"""
SiliconFlow API 连通性测试

测试真实 API key 是否可用
"""
import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings


async def test_siliconflow_api():
    """测试 SiliconFlow API 连通性"""
    print("\n" + "="*70)
    print("SiliconFlow API 连通性测试")
    print("="*70)
    
    print(f"\n配置信息:")
    print(f"  API Key: {settings.SILICONFLOW_API_KEY[:10]}...{settings.SILICONFLOW_API_KEY[-5:]}")
    print(f"  Base URL: {settings.SILICONFLOW_BASE_URL}")
    print(f"  允许模型：{settings.ALLOWED_MODELS}")
    
    # 测试 API 连通性
    print(f"\n测试 API 连通性...")
    
    headers = {
        "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 测试模型列表 API
            response = await client.get(
                f"{settings.SILICONFLOW_BASE_URL}/models",
                headers=headers
            )
            
            if response.status_code == 200:
                models = response.json()
                print(f"\n[PASS] API 连通性测试通过")
                print(f"  状态码：{response.status_code}")
                print(f"  可用模型数：{len(models.get('data', []))}")
                
                # 检查是否包含允许的模型
                allowed_models = settings.ALLOWED_MODELS.split(',')
                available_models = [m['id'] for m in models.get('data', [])]
                
                print(f"\n模型可用性检查:")
                for model in allowed_models:
                    if model in available_models:
                        print(f"  [PASS] {model}: 可用")
                    else:
                        print(f"  [WARN] {model}: 不可用")
                
                return True
                
            elif response.status_code == 401:
                print(f"\n[FAIL] API Key 无效")
                print(f"  状态码：{response.status_code}")
                print(f"  错误：{response.text}")
                return False
                
            elif response.status_code == 403:
                print(f"\n[FAIL] API Key 无权限")
                print(f"  状态码：{response.status_code}")
                print(f"  错误：{response.text}")
                return False
                
            else:
                print(f"\n[FAIL] API 请求失败")
                print(f"  状态码：{response.status_code}")
                print(f"  错误：{response.text}")
                return False
                
        except httpx.TimeoutException:
            print(f"\n[FAIL] 请求超时")
            return False
        except Exception as e:
            print(f"\n[FAIL] 测试异常：{e}")
            return False


async def test_chat_completion():
    """测试聊天补全 API"""
    print("\n" + "-"*70)
    print("聊天补全 API 测试")
    print("-"*70)
    
    headers = {
        "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-coder",
        "messages": [
            {"role": "user", "content": "Hello, please respond with just 'OK'"}
        ],
        "max_tokens": 10
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{settings.SILICONFLOW_BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                print(f"\n[PASS] 聊天补全测试通过")
                print(f"  响应：{content.strip()}")
                print(f"  使用 token 数：{result['usage']['total_tokens']}")
                return True
            else:
                print(f"\n[FAIL] 聊天补全测试失败")
                print(f"  状态码：{response.status_code}")
                print(f"  错误：{response.text}")
                return False
                
        except Exception as e:
            print(f"\n[FAIL] 测试异常：{e}")
            return False


async def main():
    """主测试函数"""
    results = {}
    
    # 测试 1: API 连通性
    results['api_connectivity'] = await test_siliconflow_api()
    
    # 测试 2: 聊天补全
    if results['api_connectivity']:
        results['chat_completion'] = await test_chat_completion()
    
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
    
    if passed == total:
        print("\n[SUCCESS] 所有 API 测试通过！API key 有效可用。")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
