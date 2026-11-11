"""image_generation 的 HTTP 生命周期、下载保护、保存与 API 重试测试。"""

import base64
import httpx
import pytest
from fastapi import HTTPException

import app.utils.image_generation as ig


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=self)


class FakeStreamResponse(FakeResponse):
    def __init__(self, events, **kwargs):
        super().__init__(**kwargs)
        self._events = events

    async def aiter_bytes(self):
        for event in self._events:
            yield event


class FakeStreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return False


class FakeClient:
    def __init__(self, responses=None, post_response=None):
        self.responses = list(responses or [])
        self.post_response = post_response
        self.calls = []
        self.posts = []
        self.is_closed = False

    def stream(self, method, url, timeout=None, follow_redirects=None):
        self.calls.append((method, url, timeout, follow_redirects))
        return FakeStreamContext(self.responses.pop(0))

    async def post(self, url, headers=None, json=None):
        self.posts.append((url, headers, json))
        if isinstance(self.post_response, Exception):
            raise self.post_response
        return self.post_response

    async def aclose(self):
        self.is_closed = True


class TestHttpClientLifecycle:
    @pytest.mark.asyncio
    async def test_creates_and_reuses_client(self, monkeypatch):
        created = []

        def factory(**kwargs):
            client = FakeClient()
            created.append((client, kwargs))
            return client

        monkeypatch.setattr(ig, "_http_client", None)
        monkeypatch.setattr(ig.httpx, "AsyncClient", factory)

        first = await ig.get_http_client()
        second = await ig.get_http_client()

        assert first is second
        assert len(created) == 1
        assert created[0][1]["limits"] is not None

    @pytest.mark.asyncio
    async def test_recreates_closed_client(self, monkeypatch):
        closed = FakeClient()
        closed.is_closed = True
        monkeypatch.setattr(ig, "_http_client", closed)
        monkeypatch.setattr(ig.httpx, "AsyncClient", lambda **kwargs: FakeClient())

        client = await ig.get_http_client()

        assert client is not closed

    @pytest.mark.asyncio
    async def test_returns_client_created_while_waiting_for_lock(self, monkeypatch):
        winner = FakeClient()

        class WinningLock:
            async def __aenter__(self):
                monkeypatch.setattr(ig, "_http_client", winner)
                return self

            async def __aexit__(self, *_args):
                return False

        monkeypatch.setattr(ig, "_http_client", None)
        monkeypatch.setattr(ig, "_http_client_lock", WinningLock())

        assert await ig.get_http_client() is winner

    @pytest.mark.asyncio
    async def test_close_open_client(self, monkeypatch):
        client = FakeClient()
        monkeypatch.setattr(ig, "_http_client", client)

        await ig.close_http_client()

        assert client.is_closed is True
        assert ig._http_client is None

    @pytest.mark.asyncio
    async def test_close_without_client_is_noop(self, monkeypatch):
        monkeypatch.setattr(ig, "_http_client", None)

        await ig.close_http_client()

        assert ig._http_client is None

    @pytest.mark.asyncio
    async def test_close_already_closed_client(self, monkeypatch):
        client = FakeClient()
        client.is_closed = True
        monkeypatch.setattr(ig, "_http_client", client)

        await ig.close_http_client()

        assert ig._http_client is client


class TestDownload:
    @pytest.mark.asyncio
    async def test_rejects_blocked_url(self, monkeypatch):
        monkeypatch.setattr(ig, "check_outbound_url", lambda *a, **k: "blocked")

        with pytest.raises(ValueError, match="被拒绝: blocked"):
            await ig._download_image_bytes("https://example.com/a.png")

    @pytest.mark.asyncio
    async def test_redirect_without_location(self, monkeypatch):
        client = FakeClient([FakeResponse(status_code=302)])
        monkeypatch.setattr(ig, "check_outbound_url", lambda *a, **k: None)
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        with pytest.raises(ValueError, match="缺少 Location"):
            await ig._download_image_bytes("https://example.com/a.png")

    @pytest.mark.asyncio
    async def test_redirect_resolved_relative(self, monkeypatch):
        client = FakeClient(
            [
                FakeResponse(status_code=301, headers={"location": "/next.png"}),
                FakeStreamResponse([b"data"]),
            ]
        )
        monkeypatch.setattr(ig, "check_outbound_url", lambda *a, **k: None)
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        content = await ig._download_image_bytes("https://example.com/a.png")

        assert content == b"data"
        assert client.calls[1][1] == "https://example.com/next.png"

    @pytest.mark.asyncio
    async def test_too_many_redirects(self, monkeypatch):
        responses = [
            FakeResponse(status_code=302, headers={"location": f"/{i}.png"})
            for i in range(ig._MAX_DOWNLOAD_REDIRECTS + 1)
        ]
        client = FakeClient(responses)
        monkeypatch.setattr(ig, "check_outbound_url", lambda *a, **k: None)
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        with pytest.raises(ValueError, match="重定向次数超过上限"):
            await ig._download_image_bytes("https://example.com/a.png")

    @pytest.mark.asyncio
    async def test_size_cap_truncates(self, monkeypatch):
        class LimitedStream(FakeStreamResponse):
            async def aiter_bytes(self):
                yield b"a" * (ig._MAX_DOWNLOAD_BYTES + 10)
                yield b"tail"

        client = FakeClient([LimitedStream([])])
        monkeypatch.setattr(ig, "check_outbound_url", lambda *a, **k: None)
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        content = await ig._download_image_bytes("https://example.com/a.png")

        assert len(content) == ig._MAX_DOWNLOAD_BYTES

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, monkeypatch):
        client = FakeClient([FakeResponse(status_code=500)])
        monkeypatch.setattr(ig, "check_outbound_url", lambda *a, **k: None)
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        with pytest.raises(httpx.HTTPStatusError):
            await ig._download_image_bytes("https://example.com/a.png")


def _async(value):
    async def factory():
        return value
    return factory()


class TestSaveResponse:
    @pytest.mark.asyncio
    async def test_base64_entry_saved(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path)
        payload = base64.b64encode(b"bytes").decode()

        images, paths = await ig._save_images_from_response(
            {"data": [{"b64_json": payload}]}, "p", "jpg"
        )

        assert images == [f"data:image/jpeg;base64,{payload}"]
        assert (tmp_path / paths[0].split("/")[-1]).read_bytes() == b"bytes"

    @pytest.mark.asyncio
    async def test_url_download_failure_logged(self, monkeypatch, tmp_path):
        errors = []
        monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(ig.logger, "error", lambda message: errors.append(message))

        async def fail(_url, timeout=60.0):
            raise OSError("network")

        monkeypatch.setattr(ig, "_download_image_bytes", fail)

        images, paths = await ig._save_images_from_response(
            {"data": [{"url": "https://example.com/a.png"}]}, "p", "png"
        )

        assert images == []
        assert paths == []
        assert "从 URL 下载图片失败" in errors[0]

    @pytest.mark.asyncio
    async def test_empty_data(self):
        assert await ig._save_images_from_response({}, "p", "png") == ([], [])

    @pytest.mark.asyncio
    async def test_entry_without_payload_is_skipped(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path)

        async def fake_download(_url, timeout=60.0):
            return b"img"

        monkeypatch.setattr(ig, "_download_image_bytes", fake_download)
        images, paths = await ig._save_images_from_response(
            {"data": [{}, {"url": "https://example.com/a.png"}]}, "p", "png"
        )

        assert len(images) == 1
        assert len(paths) == 1


class TestConverters:
    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="图片文件不存在"):
            ig.image_to_base64(str(tmp_path / "absent.png"))

    def test_oversize_file(self, monkeypatch, tmp_path):
        path = tmp_path / "a.png"
        path.write_bytes(b"x")
        monkeypatch.setattr(ig, "MAX_IMAGE_SIZE", 0)

        with pytest.raises(ValueError, match="图片文件过大"):
            ig.image_to_base64(str(path))

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "a.bmp"
        path.write_bytes(b"x")

        with pytest.raises(ValueError, match="不支持的图片格式"):
            ig.image_to_base64(str(path))

    def test_jpg_uses_jpeg_mime(self, tmp_path):
        path = tmp_path / "a.JPG"
        path.write_bytes(b"x")

        assert ig.image_to_base64(str(path)).startswith("data:image/jpeg;base64,")

    def test_png_mime(self, tmp_path):
        path = tmp_path / "a.png"
        path.write_bytes(b"x")

        assert ig.image_to_base64(str(path)).startswith("data:image/png;base64,")

    def test_base64_to_image_strips_data_prefix(self, tmp_path):
        payload = "data:image/png;base64," + base64.b64encode(b"raw").decode()
        output = tmp_path / "nested" / "out.png"

        result = ig.base64_to_image(payload, str(output))

        assert result == str(output)
        assert output.read_bytes() == b"raw"


class TestGenerationEntrypoints:
    @pytest.mark.asyncio
    async def test_empty_prompt_rejected(self):
        with pytest.raises(ValueError, match="prompt 不能为空"):
            await ig.text_to_image("   ")

    @pytest.mark.asyncio
    async def test_text_to_image_clamps_and_forwards_seed(self, monkeypatch):
        captured = {}

        async def fake_call(data, timeout, api_key_token=None):
            captured.update(data)
            return {"data": []}

        monkeypatch.setattr(ig, "_call_kolors_api", fake_call)

        result = await ig.text_to_image(
            "cat", width=1, height=9999, num_inferences=0, num_images=99, seed=7
        )

        assert captured["image_size"] == "256x1280"
        assert captured["num_inference_steps"] == 1
        assert captured["batch_size"] == 4
        assert captured["seed"] == 7
        assert result["config"]["width"] == 256
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_text_to_image_omits_seed_when_none(self, monkeypatch):
        captured = {}

        async def fake_call(data, timeout, api_key_token=None):
            captured.update(data)
            return {"data": []}

        monkeypatch.setattr(ig, "_call_kolors_api", fake_call)

        await ig.text_to_image("cat")

        assert "seed" not in captured

    @pytest.mark.asyncio
    async def test_image_to_image_forwards_optional_dims(self, monkeypatch, tmp_path):
        reference = tmp_path / "ref.png"
        reference.write_bytes(b"img")
        captured = {}

        async def fake_call(data, timeout, api_key_token=None):
            captured.update(data)
            return {"data": []}

        monkeypatch.setattr(ig, "_call_kolors_api", fake_call)

        result = await ig.image_to_image(
            str(reference), "paint", width=512, height=768, seed=3
        )

        assert captured["width"] == 512
        assert captured["height"] == 768
        assert captured["seed"] == 3
        assert captured["init_image"].startswith("data:image/png;base64,")
        assert result["reference_image"] == str(reference)

    @pytest.mark.asyncio
    async def test_image_to_image_skips_falsy_dims(self, monkeypatch, tmp_path):
        reference = tmp_path / "ref.png"
        reference.write_bytes(b"img")
        captured = {}

        async def fake_call(data, timeout, api_key_token=None):
            captured.update(data)
            return {"data": []}

        monkeypatch.setattr(ig, "_call_kolors_api", fake_call)

        await ig.image_to_image(str(reference), "paint", width=0, height=None)

        assert "width" not in captured
        assert "height" not in captured

    @pytest.mark.asyncio
    async def test_inpaint_forwards_two_images(self, monkeypatch, tmp_path):
        image = tmp_path / "img.png"
        image.write_bytes(b"img")
        mask = tmp_path / "mask.png"
        mask.write_bytes(b"mask")
        captured = {}

        async def fake_call(data, timeout, api_key_token=None):
            captured.update(data)
            return {"data": []}

        monkeypatch.setattr(ig, "_call_kolors_api", fake_call)

        result = await ig.inpaint_image(str(image), str(mask), "fix", seed=9)

        assert captured["mask_image"].startswith("data:image/png;base64,")
        assert captured["seed"] == 9
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_avatar_known_and_unknown_style(self, monkeypatch):
        prompts = []

        async def fake_text_to_image(**kwargs):
            prompts.append(kwargs["prompt"])
            return {"success": True}

        monkeypatch.setattr(ig, "text_to_image", fake_text_to_image)

        await ig.generate_avatar("hero", "anime")
        await ig.generate_avatar("hero", "unknown")

        assert "日系动漫风格" in prompts[0]
        assert prompts[1].startswith(", hero")

    @pytest.mark.asyncio
    async def test_landscape_known_and_unknown_style(self, monkeypatch):
        prompts = []

        async def fake_text_to_image(**kwargs):
            prompts.append(kwargs["prompt"])
            return {"success": True}

        monkeypatch.setattr(ig, "text_to_image", fake_text_to_image)

        await ig.generate_landscape("mountain", "oil_painting")
        await ig.generate_landscape("mountain", "unknown")

        assert prompts[0].startswith("油画风格")
        assert prompts[1].startswith("mountain")

    @pytest.mark.asyncio
    async def test_icon_uses_style_suffix(self, monkeypatch):
        captured = {}

        async def fake_text_to_image(**kwargs):
            captured.update(kwargs)
            return {"success": True}

        monkeypatch.setattr(ig, "text_to_image", fake_text_to_image)

        await ig.generate_icon("star")

        assert "扁平化图标设计" in captured["prompt"]
        assert captured["guidance_scale"] == 9.0


class TestKolorsApi:
    @pytest.mark.asyncio
    async def test_success_returns_json(self, monkeypatch):
        client = FakeClient(post_response=FakeResponse(payload={"data": []}))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        result = await ig._call_kolors_api({"prompt": "x"}, httpx.Timeout(1.0))

        assert result == {"data": []}
        assert client.posts[0][1]["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_user_key_is_used(self, monkeypatch):
        client = FakeClient(post_response=FakeResponse(payload={}))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        class Manager:
            def get_key_by_token(self, token):
                assert token == "tok"
                return "user-key"

        monkeypatch.setattr(
            "app.services.apikey_manager.get_apikey_manager", lambda: Manager()
        )

        await ig._call_kolors_api({}, httpx.Timeout(1.0), api_key_token="tok")

        assert client.posts[0][1]["Authorization"] == "Bearer user-key"

    @pytest.mark.asyncio
    async def test_user_key_lookup_failure_falls_back(self, monkeypatch):
        client = FakeClient(post_response=FakeResponse(payload={}))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))
        warnings = []
        monkeypatch.setattr(ig.logger, "warning", lambda message: warnings.append(message))

        monkeypatch.setattr(
            "app.services.apikey_manager.get_apikey_manager",
            lambda: (_ for _ in ()).throw(RuntimeError("db down")),
        )

        await ig._call_kolors_api({}, httpx.Timeout(1.0), api_key_token="tok")

        assert any("获取用户 API Key 失败" in message for message in warnings)

    @pytest.mark.asyncio
    async def test_unknown_token_keeps_system_key(self, monkeypatch):
        client = FakeClient(post_response=FakeResponse(payload={}))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        class Manager:
            def get_key_by_token(self, token):
                return None

        monkeypatch.setattr(
            "app.services.apikey_manager.get_apikey_manager", lambda: Manager()
        )

        await ig._call_kolors_api({}, httpx.Timeout(1.0), api_key_token="unknown")

        assert client.posts[0][1]["Authorization"] == f"Bearer {ig.settings.SILICONFLOW_API_KEY}"

    @pytest.mark.asyncio
    async def test_server_error_retries_then_raises(self, monkeypatch):
        client = FakeClient(post_response=FakeResponse(status_code=503, text="down"))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(ig.asyncio, "sleep", fake_sleep)

        with pytest.raises(HTTPException) as excinfo:
            await ig._call_kolors_api({}, httpx.Timeout(1.0))

        assert excinfo.value.status_code == 503
        assert sleeps == [1.0, 2.0, 4.0]
        assert len(client.posts) == 3

    @pytest.mark.asyncio
    async def test_client_error_breaks_without_retry(self, monkeypatch):
        client = FakeClient(post_response=FakeResponse(status_code=400, text="bad"))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        with pytest.raises(HTTPException) as excinfo:
            await ig._call_kolors_api({}, httpx.Timeout(1.0))

        assert excinfo.value.status_code == 400
        assert len(client.posts) == 1

    @pytest.mark.asyncio
    async def test_timeout_retries_then_504(self, monkeypatch):
        client = FakeClient(post_response=httpx.TimeoutException("slow"))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        async def fake_sleep(_seconds):
            pass

        monkeypatch.setattr(ig.asyncio, "sleep", fake_sleep)

        with pytest.raises(HTTPException) as excinfo:
            await ig._call_kolors_api({}, httpx.Timeout(1.0), max_retries=2)

        assert excinfo.value.status_code == 504
        assert len(client.posts) == 2

    @pytest.mark.asyncio
    async def test_network_error_retries_then_502(self, monkeypatch):
        client = FakeClient(post_response=httpx.ConnectError("no route"))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))

        async def fake_sleep(_seconds):
            pass

        monkeypatch.setattr(ig.asyncio, "sleep", fake_sleep)

        with pytest.raises(HTTPException) as excinfo:
            await ig._call_kolors_api({}, httpx.Timeout(1.0), max_retries=1)

        assert excinfo.value.status_code == 502

    @pytest.mark.asyncio
    async def test_unexpected_error_breaks_with_500(self, monkeypatch):
        client = FakeClient(post_response=RuntimeError("boom"))
        monkeypatch.setattr(ig, "get_http_client", lambda: _async(client))
        errors = []
        monkeypatch.setattr(ig.logger, "error", lambda *a, **k: errors.append(a))

        with pytest.raises(HTTPException) as excinfo:
            await ig._call_kolors_api({}, httpx.Timeout(1.0))

        assert excinfo.value.status_code == 500
        assert len(client.posts) == 1
        assert errors
