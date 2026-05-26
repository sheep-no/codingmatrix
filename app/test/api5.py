import httpx
import json

async def test_gaopin_api():
    """测试高品图像 API 是否正常返回 JSON"""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.gaopinimages.com/"
    }

    params = {
        "keyType": 1,
        "sortOrder": "1",
        "from": 1,
        "size": 3,
        "qk": "校园",  # 测试关键词
        "style": 1
    }

    async with httpx.AsyncClient(headers=headers) as client:
        resp = await client.get(
            "https://www.gaopinimages.com/crest/search/searchImageV2",
            params=params,
            timeout=10.0
        )

        print(f"状态码: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type', 'unknown')}")
        print(f"\n原始响应前 500 字符:\n{resp.text[:500]}")
        print(resp.text)
        # 尝试解析 JSON
        try:
            data = resp.json()
            print(f"\n[SUCCESS] JSON 解析成功!")
            print(f"return_code: {data.get('return_code')}")
            print(f"total: {data.get('return_data', {}).get('total', 0)}")

            # 打印第一条图片数据
            images = data.get('return_data', {}).get('data', [])
            if images:
                img = images[0]
                print(f"\n第一条图片:")
                print(f"  title: {img.get('title')}")
                print(f"  thumbnailUrl300C: {img.get('thumbnailUrl300C', '')[:60]}...")
            else:
                print("\n[WARNING] 无图片数据")

        except json.JSONDecodeError as e:
            print(f"\n[ERROR] JSON 解析失败: {e}")
            print(f"响应可能是 HTML: {'<html' in resp.text[:100].lower()}")

# 运行
import asyncio
asyncio.run(test_gaopin_api())