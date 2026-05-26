import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


async def test_websocket():
    uri = "ws://127.0.0.1:8000/api/v2/Controller/sys-status?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzIiwiZXhwIjoxNzY3MTUzNzM0LCJpYXQiOjE3NjcxNTE5MzQsInR5cGUiOiJhY2Nlc3MiLCJyZWZyZXNoX3VudGlsIjoxNzY3MTUzNzM0LCJwZXJtaXNzaW9uX2xldmVsIjoic3VwZXIifQ.qeJRh1vTndrpU91ty6-HgKZiO7cBtRInYlrHZT52650"

    try:
        async with websockets.connect(uri) as ws:
            logging.info("[SUCCESS] 连接成功！")

            # 等待最多5条消息
            for _ in range(5):
                message = await ws.recv()
                print(message)
                # data = json.loads(message)
                # stats = data['data']
                # logging.info(
                #     f"CPU: {stats['cpu']['total_percent']}%, "
                #     f"内存: {stats['memory']['percent']}%, "
                #     f"磁盘: {stats['disk']['percent']}%"
                # )

    except websockets.exceptions.InvalidStatus as e:
        # 握手失败（例如路由不存在）
        logging.error("[ERROR] HTTP %s - %s", e.response.status_code, e.response.body.decode())
    except websockets.exceptions.ConnectionClosed as e:
        # 连接被关闭
        logging.warning("[WS] 关闭码=%s, 原因=%s", e.code, e.reason)
    except Exception as e:
        logging.error("[ERROR] 错误: %s", e)


if __name__ == '__main__':
    asyncio.run(test_websocket())