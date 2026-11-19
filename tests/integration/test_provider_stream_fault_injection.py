"""Socket-level fault injection for provider streaming through the real HTTP client."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from app.utils.aicloud import llm_caller
from app.utils.aicloud.adapters import openai as openai_module
from app.utils.aicloud.adapters.openai import OpenAIAdapter
from app.utils.aicloud.providers import ModelProvider, ProviderConfig


class _ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        config = self.server.config
        config["requests"] += 1
        attempt = config["requests"]

        if config["mode"] == "rate_limit_then_ok" and attempt == 1:
            self._send(429, b"busy", {"Retry-After": "30"})
            return
        if config["mode"] == "partial":
            self._send_partial()
            return
        self._send(
            200,
            b'data: {"choices":[{"delta":{"content":"recovered"}}]}\n\ndata: [DONE]\n\n',
            {"Content-Type": "text/event-stream"},
        )

    def _send(self, status, body, headers):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _send_partial(self):
        body = b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", "4096")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *_args):
        return None


@pytest.fixture
def provider_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
    server.config = {"mode": "ok", "requests": 0}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
async def provider_client(monkeypatch):
    client = httpx.AsyncClient(trust_env=False, timeout=5.0)

    async def get_client():
        return client

    monkeypatch.setattr(openai_module, "get_http_client", get_client)
    try:
        yield client
    finally:
        await client.aclose()


def _adapter(server):
    port = server.server_address[1]
    return OpenAIAdapter(
        ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="test-key",
            base_url=f"http://127.0.0.1:{port}/v1",
        )
    )


@pytest.mark.asyncio
async def test_stream_rate_limit_retries_over_real_http(
    provider_server, provider_client, monkeypatch
):
    provider_server.config["mode"] = "rate_limit_then_ok"
    monkeypatch.setattr(llm_caller, "_MODEL_COOLDOWN_MIN", 0.0)
    monkeypatch.setattr(llm_caller, "_MODEL_COOLDOWN_MAX", 0.0)
    adapter = _adapter(provider_server)

    stream = await llm_caller._invoke_adapter_with_retry(
        lambda: adapter.call_llm("injected-model", "prompt", stream=True),
        model="injected-model",
        stream=True,
        skip_semaphore=True,
    )

    assert [chunk async for chunk in stream] == [
        '{"choices":[{"delta":{"content":"recovered"}}]}\n'
    ]
    assert provider_server.config["requests"] == 2


@pytest.mark.asyncio
async def test_stream_disconnect_after_first_chunk_is_not_retried(
    provider_server, provider_client
):
    provider_server.config["mode"] = "partial"
    adapter = _adapter(provider_server)

    stream = await llm_caller._invoke_adapter_with_retry(
        lambda: adapter.call_llm("injected-model", "prompt", stream=True),
        model="injected-model",
        stream=True,
        skip_semaphore=True,
    )
    iterator = stream.__aiter__()

    assert await iterator.__anext__() == '{"choices":[{"delta":{"content":"first"}}]}\n'
    with pytest.raises(httpx.TransportError):
        await iterator.__anext__()

    await stream.aclose()
    assert provider_server.config["requests"] == 1
