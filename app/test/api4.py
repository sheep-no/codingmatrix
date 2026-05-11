import json

import httpx
import asyncio

token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzIiwiZXhwIjoxNzc1Njk3OTk1LCJpYXQiOjE3NzU2OTYxOTUsInR5cGUiOiJhY2Nlc3MiLCJyZWZyZXNoX3VudGlsIjoxNzc2MTI4MTk1LCJwZXJtaXNzaW9uX2xldmVsIjoic3VwZXIifQ.wPNTXXwW0QTapy87uZl5Qem5mGxobTgbG7gaTmnnlQo"# async def test_stream():
#     """测试流式直接代码生成（else body.stream=true）"""
#     url = "http://localhost:8080/api/v1/code"
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {token}"
#     }
#     data = {
#         "prompt": "写一个Python函数，计算斐波那契数列的第n项",
#         "model": "Qwen/Qwen2.5-Coder-7B-Instruct",
#         "stream": True,
#         "use_reasoning": False
#     }
#
#     async with httpx.AsyncClient(timeout=60.0) as client:
#         async with client.stream("POST", url, headers=headers, json=data) as resp:
#             print(f"Status: {resp.status_code}")
#             async for line in resp.aiter_lines():
#                 if line:
#                     print(line)


async def test_non_stream():
    """测试非流式直接代码生成（else body.stream=false）"""
    url = "http://localhost:8080/api/v1/code"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"}
    data = {
        "prompt": "写出pptx，ppt主题为校园安全共5页，你只需给出ppt结构和内容建议,不要给出除内容以外的东西",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "stream": True,
        "use_reasoning": False
    }
    contents=[]
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(url, headers=headers, json=data)
        print(f"Status: {resp.status_code}")
        async for line in resp.aiter_lines():
            if line.strip():  # 跳过空行
                try:
                    # 解析单行JSON
                    response_data = json.loads(line)
                    content = response_data.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        contents.append(content)
                except json.JSONDecodeError as e:
                    if "conversation_id" in line:
                        break
                    print(f"JSON解析错误: {str(e)}，原始数据: {line}")
    print(f"合并后字符串: {''.join(contents)}")


if __name__ == "__main__":
    print("=== 测试流式直接代码生成 ===")
    # asyncio.run(test_stream())

    print("\n" + "=" * 50 + "\n")

    print("=== 测试非流式直接代码生成 ===")
    asyncio.run(test_non_stream())