"""丢弃重复的 http.response.start 消息。

slowapi 的 ``SlowAPIASGIMiddleware`` 会为每个 ``http.response.body`` 分块
重新发送一次 ``http.response.start``（以便在发送前注入限流响应头）。
位于它外层的 ``GZipMiddleware`` 收到第二个 start 时，会因为响应已带
``Content-Encoding`` 而切换为「不压缩直接透传」，导致压缩流中混入明文，
浏览器解析出 ``ERR_CONTENT_DECODING_FAILED``。

本中间件放在 GZip 与 slowapi 之间，仅保留第一个 start 消息，
让响应头只发送一次，从而保证压缩流完整。
"""


class ResponseStartDedupMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start":
                if started:
                    return
                started = True
            await send(message)

        await self.app(scope, receive, send_wrapper)
