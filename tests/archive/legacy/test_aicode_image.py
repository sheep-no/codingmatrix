"""
测试 AI code 图片理解功能

流程：
1. 上传图片
2. 调用 AI code 接口分析图片
"""
import asyncio
import httpx
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.security import create_access_token

API_BASE = "http://localhost:8000"
TEST_IMAGE = "/workspace/src/public/logo.jpg"


def get_auth_headers():
    """生成认证头"""
    token = create_access_token(sub="999999", permission_level="user")
    return {"Authorization": f"Bearer {token}"}


def image_to_base64(image_path: str) -> str:
    """将图片转为 base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


async def test_aicode_image():
    """测试 AI code 图片理解"""
    # 读取图片
    img_path = Path(TEST_IMAGE)
    if not img_path.exists():
        print(f"测试图片不存在: {TEST_IMAGE}")
        return

    print(f"1. 读取图片: {TEST_IMAGE}")

    # 先上传图片获取 file_id
    print("2. 上传图片...")
    with open(TEST_IMAGE, 'rb') as f:
        files = {'file': ('logo.jpg', f, 'image/jpeg')}
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{API_BASE}/api/v1/files/upload",
                    files=files,
                    headers=get_auth_headers(),
                    timeout=30.0
                )
                if resp.status_code == 200:
                    result = resp.json()
                    file_id = result.get('file_id') or result.get('id')
                    print(f"   上传成功: file_id={file_id}")
                else:
                    print(f"   上传失败: {resp.status_code} {resp.text}")
                    return
            except Exception as e:
                print(f"   上传请求失败: {e}")
                return

    # 调用 AI code 接口分析图片
    print("3. 调用 AI code 接口分析图片...")
    payload = {
        "prompt": "请描述这张图片的内容",
        "image_path": str(file_id),
        "model": "THUDM/GLM-4.1V-9B-Thinking",
        "stream": False
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{API_BASE}/api/v1/code",
                json=payload,
                headers=get_auth_headers(),
                timeout=60.0
            )
            print(f"   响应状态: {resp.status_code}")
            if resp.status_code == 200:
                result = resp.json()
                print(f"   AI 回复: {result}")
            else:
                print(f"   失败: {resp.text}")
        except Exception as e:
            print(f"   请求失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_aicode_image())
