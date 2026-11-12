"""vision_api 全分支回归。"""

import base64
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import vision_api as va


class _Upload:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


@pytest.fixture(autouse=True)
def no_temp_leak(monkeypatch):
    yield


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_no_input(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(file=None, image_url=None, token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(
                file=_Upload("a.exe", b"x"), token={"sub": "u"}
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_without_filename(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(file=_Upload(None, b"x"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_too_large(self, monkeypatch):
        monkeypatch.setattr(va, "MAX_IMAGE_SIZE", 2)
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(
                file=_Upload("a.png", b"abcd"), token={"sub": "u"}
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_success(self, monkeypatch):
        seen = {}

        async def fake_analyze(path, prompt=None, model=None):
            seen["content"] = Path(path).read_bytes()
            return {"description": "d", "model_used": "m", "objects": [1], "text": "t"}

        monkeypatch.setattr(va, "analyze_image", fake_analyze)
        result = await va.api_analyze_image(
            file=_Upload("a.PNG", b"data"), prompt="p", model="m", token={"sub": "u"}
        )
        assert result.description == "d"
        assert result.objects == [1]
        assert seen["content"] == b"data"

    @pytest.mark.asyncio
    async def test_upload_analyze_error(self, monkeypatch):
        monkeypatch.setattr(va, "analyze_image", AsyncMock(side_effect=RuntimeError("x")))
        monkeypatch.setattr(va.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(
                file=_Upload("a.png", b"data"), token={"sub": "u"}
            )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_data_uri_too_large_string(self, monkeypatch):
        monkeypatch.setattr(va, "MAX_IMAGE_SIZE", 2)
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(
                file=None, image_url="data:image/png;base64," + "a" * 10, token={"sub": "u"}
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_non_data_uri(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_analyze_image(
                file=None, image_url="http://x/a.png", token={"sub": "u"}
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_data_uri_success_jpeg(self, monkeypatch):
        async def fake_analyze(path, prompt=None, model=None):
            assert path.endswith(".jpg")
            return {"description": "d", "model_used": "m"}

        monkeypatch.setattr(va, "analyze_image", fake_analyze)
        payload = base64.b64encode(b"abc").decode()
        result = await va.api_analyze_image(
            file=None, image_url=f"data:image/jpeg;base64,{payload}",
            prompt=None, model=None, token={"sub": "u"},
        )
        assert result.text == ""
        assert result.objects == []

    @pytest.mark.asyncio
    async def test_data_uri_unknown_mime_defaults_png(self, monkeypatch):
        seen = {}

        async def fake_analyze(path, prompt=None, model=None):
            seen["path"] = path
            return {"description": "d", "model_used": "m"}

        monkeypatch.setattr(va, "analyze_image", fake_analyze)
        payload = base64.b64encode(b"abc").decode()
        await va.api_analyze_image(
            file=None, image_url=f"data:application/octet-stream;base64,{payload}",
            token={"sub": "u"},
        )
        assert seen["path"].endswith(".png")

    @pytest.mark.asyncio
    async def test_cleanup_error_is_swallowed(self, monkeypatch, tmp_path):
        async def fake_analyze(path, prompt=None, model=None):
            return {"description": "d", "model_used": "m"}

        monkeypatch.setattr(va, "analyze_image", fake_analyze)
        monkeypatch.setattr(
            Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(RuntimeError("x"))
        )
        result = await va.api_analyze_image(
            file=_Upload("a.png", b"data"), token={"sub": "u"}
        )
        assert result.description == "d"


class TestOCR:
    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_ocr(file=_Upload("a.txt", b"x"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_too_large(self, monkeypatch):
        monkeypatch.setattr(va, "MAX_IMAGE_SIZE", 2)
        with pytest.raises(HTTPException) as exc:
            await va.api_ocr(file=_Upload("a.png", b"abcd"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        monkeypatch.setattr(va, "extract_text_from_image", AsyncMock(return_value="txt"))
        result = await va.api_ocr(file=_Upload("a.png", b"data"), token={"sub": "u"})
        assert result.text == "txt"

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch):
        monkeypatch.setattr(
            va, "extract_text_from_image", AsyncMock(side_effect=RuntimeError("x"))
        )
        monkeypatch.setattr(va.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await va.api_ocr(file=_Upload("a.png", b"data"), token={"sub": "u"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_cleanup_error(self, monkeypatch):
        monkeypatch.setattr(va, "extract_text_from_image", AsyncMock(return_value="t"))
        monkeypatch.setattr(
            Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(RuntimeError("x"))
        )
        assert (await va.api_ocr(file=_Upload("a.png", b"d"), token={"sub": "u"})).text == "t"


class TestCodeFromImage:
    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_code_from_image(file=_Upload("a.txt", b"x"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_too_large(self, monkeypatch):
        monkeypatch.setattr(va, "MAX_IMAGE_SIZE", 2)
        with pytest.raises(HTTPException) as exc:
            await va.api_code_from_image(file=_Upload("a.png", b"abcd"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        result = {
            "description": "d",
            "technology_stack": ["vue"],
            "code_structure": "c",
            "raw_description": "r",
        }
        gen = AsyncMock(return_value=result)
        monkeypatch.setattr(va, "generate_code_from_image", gen)
        response = await va.api_code_from_image(
            file=_Upload("a.png", b"data"), requirement="req", token={"sub": "u"}
        )
        assert response.technology_stack == ["vue"]
        gen.assert_awaited_once()
        assert gen.await_args.kwargs["requirement"] == "req"

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch):
        monkeypatch.setattr(
            va, "generate_code_from_image", AsyncMock(side_effect=RuntimeError("x"))
        )
        monkeypatch.setattr(va.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await va.api_code_from_image(file=_Upload("a.png", b"d"), token={"sub": "u"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_cleanup_error(self, monkeypatch):
        monkeypatch.setattr(
            va,
            "generate_code_from_image",
            AsyncMock(return_value={"description": "d", "technology_stack": [], "code_structure": "c", "raw_description": "r"}),
        )
        monkeypatch.setattr(
            Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(RuntimeError("x"))
        )
        assert (await va.api_code_from_image(file=_Upload("a.png", b"d"), token={"sub": "u"})).description == "d"


class TestSafety:
    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        with pytest.raises(HTTPException) as exc:
            await va.api_check_safety(file=_Upload("a.txt", b"x"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_too_large(self, monkeypatch):
        monkeypatch.setattr(va, "MAX_IMAGE_SIZE", 2)
        with pytest.raises(HTTPException) as exc:
            await va.api_check_safety(file=_Upload("a.png", b"abcd"), token={"sub": "u"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        monkeypatch.setattr(
            va, "check_image_safety",
            AsyncMock(return_value={"safe": False, "reason": "r", "flags": ["f"]}),
        )
        result = await va.api_check_safety(file=_Upload("a.png", b"d"), token={"sub": "u"})
        assert result.safe is False
        assert result.flags == ["f"]

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch):
        monkeypatch.setattr(
            va, "check_image_safety", AsyncMock(side_effect=RuntimeError("x"))
        )
        monkeypatch.setattr(va.logger, "error", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            await va.api_check_safety(file=_Upload("a.png", b"d"), token={"sub": "u"})
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_cleanup_error(self, monkeypatch):
        monkeypatch.setattr(
            va, "check_image_safety",
            AsyncMock(return_value={"safe": True, "reason": "", "flags": []}),
        )
        monkeypatch.setattr(
            Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(RuntimeError("x"))
        )
        assert (await va.api_check_safety(file=_Upload("a.png", b"d"), token={"sub": "u"})).safe is True
