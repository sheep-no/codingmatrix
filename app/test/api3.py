# 保存为 test_logs.py
import asyncio
import websockets
import json


async def test_logs():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzIiwiZXhwIjoxNzY3MjcxNjIwLCJpYXQiOjE3NjcyNjk4MjAsInR5cGUiOiJhY2Nlc3MiLCJyZWZyZXNoX3VudGlsIjoxNzY3NzAxODIwLCJwZXJtaXNzaW9uX2xldmVsIjoic3VwZXIifQ.QAhEVfQUXAiTxwWyTRpgiW6XZS74w_ATcZXiGsP8qJY"
    uri = f"ws://localhost:8000/api/v2/Controller/logs?token={token}&log_type=app"

    async with websockets.connect(uri) as ws:
        print("[SUCCESS] 连接成功！")

        # 发送过滤器
        await ws.send(json.dumps({
            "action": "filter",
            "level": "ERROR",
            "keyword": "websocket"
        }))

        # 接收日志
        async for message in ws:
            log = json.loads(message)
            print(log)


# 安装 websockets: pip install websockets
asyncio.run(test_logs())

