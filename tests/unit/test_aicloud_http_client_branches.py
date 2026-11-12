"""Branch coverage for app/utils/aicloud/http_client.py."""

import asyncio

import httpx
import pytest

from app.utils.aicloud import http_client


@pytest.fixture(autouse=True)
def _reset_client():
    yield
    http_client._http_client = None
    http_client._http_client_loop = None


class TestGetHttpClient:
    async def test_reuses_open_client_in_same_loop(self):
        first = await http_client.get_http_client()
        second = await http_client.get_http_client()
        assert first is second
        await http_client.close_http_client()

    async def test_recreates_when_client_closed(self):
        client = await http_client.get_http_client()
        await client.aclose()

        replacement = await http_client.get_http_client()

        assert replacement is not client
        await http_client.close_http_client()

    async def test_inner_double_check_returns_client_created_by_race_winner(self, monkeypatch):
        winner = httpx.AsyncClient()

        class RacingLock:
            async def __aenter__(self):
                # Another coroutine populated the singleton before we got the lock.
                http_client._http_client = winner
                http_client._http_client_loop = asyncio.get_running_loop()
                return self

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(http_client, "_http_client_lock", RacingLock())
        http_client._http_client = None

        result = await http_client.get_http_client()

        assert result is winner
        await winner.aclose()
        await http_client.close_http_client()


class TestCloseHttpClient:
    async def test_noop_without_client(self):
        http_client._http_client = None
        await http_client.close_http_client()
        assert http_client._http_client is None

    async def test_noop_when_already_closed(self):
        class ClosedClient:
            is_closed = True

        http_client._http_client = ClosedClient()
        http_client._http_client_loop = asyncio.get_running_loop()

        await http_client.close_http_client()

        assert http_client._http_client is None
        assert http_client._http_client_loop is None

    async def test_outer_stale_but_inner_check_fresh_returns_existing(self, monkeypatch):
        existing = object()
        loop = asyncio.get_running_loop()

        class FakeClient:
            is_closed = False

        existing = FakeClient()

        class FreshLock:
            async def __aenter__(self):
                # Re-reading the loop inside the lock shows the client is current again.
                http_client._http_client = existing
                http_client._http_client_loop = loop
                return self

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(http_client, "_http_client_lock", FreshLock())
        http_client._http_client = FakeClient()
        http_client._http_client_loop = object()  # pretend another loop created it

        result = await http_client.get_http_client()

        assert result is existing


def _response(status_code, request=None):
    request = request or httpx.Request("POST", "https://example.test/v1/chat")
    return httpx.Response(status_code, request=request)


class TestCallWithRetry:
    async def test_returns_non_http_result(self):
        async def func():
            return "plain"

        assert await http_client.call_with_retry(func) == "plain"

    async def test_returns_200_response(self):
        response = _response(200)

        async def func():
            return response

        assert await http_client.call_with_retry(func) is response

    async def test_retries_503_with_longer_backoff(self, monkeypatch):
        response = _response(503)
        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        async def func():
            return response

        monkeypatch.setattr(http_client.asyncio, "sleep", fake_sleep)

        with pytest.raises(httpx.HTTPStatusError):
            await http_client.call_with_retry(func, max_retries=2)

        assert slept == [3.0, 6.0]

    async def test_retries_500_then_succeeds(self, monkeypatch):
        calls = {"n": 0}
        ok = _response(200)
        bad = _response(500)

        async def func():
            calls["n"] += 1
            return bad if calls["n"] == 1 else ok

        async def fake_sleep(_seconds):
            return None

        monkeypatch.setattr(http_client.asyncio, "sleep", fake_sleep)

        result = await http_client.call_with_retry(func, max_retries=3)

        assert result is ok
        assert calls["n"] == 2

    async def test_other_status_returned_untouched(self):
        response = _response(404)

        async def func():
            return response

        assert await http_client.call_with_retry(func) is response

    async def test_retries_timeout_then_raises_last_error(self, monkeypatch):
        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(http_client.asyncio, "sleep", fake_sleep)

        async def func():
            raise httpx.ReadTimeout("slow")

        with pytest.raises(httpx.ReadTimeout):
            await http_client.call_with_retry(func, max_retries=2)

        assert slept == [1.0, 2.0]

    async def test_retries_network_error_then_succeeds(self, monkeypatch):
        calls = {"n": 0}

        async def fake_sleep(_seconds):
            return None

        monkeypatch.setattr(http_client.asyncio, "sleep", fake_sleep)

        async def func():
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("boom")
            return "done"

        assert await http_client.call_with_retry(func, max_retries=2) == "done"

    async def test_network_error_with_429_response_is_raised(self):
        request = httpx.Request("POST", "https://example.test/v1/chat")
        error = httpx.HTTPStatusError(
            "busy", request=request, response=httpx.Response(429, request=request)
        )

        async def func():
            raise error

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await http_client.call_with_retry(func, max_retries=3)

        assert exc_info.value is error

    async def test_unexpected_exception_is_reraised(self):
        async def func():
            raise ValueError("bad")

        with pytest.raises(ValueError):
            await http_client.call_with_retry(func, max_retries=3)

    async def test_exhausted_response_retries_raise_status_error(self, monkeypatch):
        response = _response(502)

        async def fake_sleep(_seconds):
            return None

        async def func():
            return response

        monkeypatch.setattr(http_client.asyncio, "sleep", fake_sleep)

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await http_client.call_with_retry(func, max_retries=2)

        assert exc_info.value.response.status_code == 502

    async def test_no_retries_raises_runtime_error(self):
        async def func():
            return _response(500)

        with pytest.raises(RuntimeError):
            await http_client.call_with_retry(func, max_retries=0)
