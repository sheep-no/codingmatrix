"""Kolors 图像 API 全分支回归：缓存、上传、权限、生成与快捷入口。"""

import io
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.v1 import kolors_api as ka


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value

    def __iter__(self):
        return iter(self._value)


class _DB:
    def __init__(self, results=(), fail_on_execute=None):
        self._results = list(results)
        self._fail = fail_on_execute
        self.executed = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement):
        if self._fail is not None:
            raise self._fail
        self.executed.append(statement)
        return _Result(self._results.pop(0))

    def add(self, record):
        self.added.append(record)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _Request:
    def __init__(self, content_type="application/json", body=None, form_data=None):
        self.headers = {"content-type": content_type}
        self._body = body
        self._form = form_data

    async def json(self):
        return self._body

    async def form(self):
        return self._form


def _history(metadata):
    return SimpleNamespace(metadata_json=json.dumps(metadata))


def _token(user_id=1):
    return {"sub": str(user_id)}


@pytest.mark.asyncio
async def test_save_upload_file_writes_with_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "TEMP_DIR", tmp_path)
    upload = UploadFile(file=io.BytesIO(b"payload"), filename="photo.JPG")
    path = await ka._save_upload_file(upload)
    assert path.startswith(str(tmp_path))
    assert path.endswith(".JPG")
    assert (tmp_path / path.rsplit("/", 1)[-1]).read_bytes() == b"payload"


@pytest.mark.asyncio
async def test_save_upload_file_rejects_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(ka, "MAX_IMAGE_SIZE", 1)
    upload = UploadFile(file=io.BytesIO(b"too big"), filename=None)
    with pytest.raises(HTTPException) as exc:
        await ka._save_upload_file(upload)
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_save_upload_file_defaults_to_png(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "TEMP_DIR", tmp_path)
    upload = UploadFile(file=io.BytesIO(b"x"), filename=None)
    path = await ka._save_upload_file(upload)
    assert path.endswith(".png")


@pytest.mark.asyncio
async def test_get_cached_image_hit(monkeypatch):
    db = _DB([_history({"type": "image", "path": "/tmp/a.png"})])
    path = await ka.get_cached_image(
        db, 1, "p", None, None, fingerprint=None
    )
    assert path == "/tmp/a.png"


@pytest.mark.asyncio
async def test_get_cached_image_with_conversation_and_fingerprint():
    db = _DB([_history({"type": "image", "path": "/tmp/a.png", "fingerprint": "f1"})])
    path = await ka.get_cached_image(db, 1, "p", 5, 9, fingerprint="f1")
    assert path == "/tmp/a.png"


@pytest.mark.asyncio
async def test_get_cached_image_returns_none_when_missing():
    assert await ka.get_cached_image(_DB([None]), 1, "p", None, None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"type": "text", "path": "/tmp/a.png"},
        {"type": "image"},
        {"type": "image", "path": "/tmp/a.png", "fingerprint": "other"},
    ],
)
async def test_get_cached_image_rejects_mismatched_metadata(metadata):
    assert (
        await ka.get_cached_image(
            _DB([_history(metadata)]), 1, "p", None, None, fingerprint="target"
        )
        is None
    )


@pytest.mark.asyncio
async def test_get_cached_image_swallows_errors(monkeypatch):
    logged = []

    class _Logger:
        def info(self, *a, **k):
            pass

        def error(self, msg):
            logged.append(msg)

    monkeypatch.setattr(ka, "logger", _Logger())
    db = _DB(fail_on_execute=ValueError("boom"))
    assert await ka.get_cached_image(db, 1, "p", None, None) is None
    assert logged


@pytest.mark.asyncio
async def test_cache_image_to_history_persists_and_logs(monkeypatch):
    calls = []

    async def _save(**kwargs):
        calls.append(kwargs)
        return 12

    monkeypatch.setattr(ka, "save_history_to_db", _save)
    db = _DB()
    await ka.cache_image_to_history(
        db, 4, None, "prompt", "/tmp/a.png", 7, fingerprint="fp"
    )
    assert calls[0]["conversation_id"] is None
    assert calls[0]["metadata"]["fingerprint"] == "fp"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_cache_image_to_history_rolls_back_on_error(monkeypatch):
    async def _save(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ka, "save_history_to_db", _save)
    db = _DB()
    await ka.cache_image_to_history(db, 4, 2, "p", "/tmp/a.png", None)
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_save_image_generation_history_success(monkeypatch):
    monkeypatch.setattr(ka, "normalize_image_references", lambda paths: list(paths))
    db = _DB()
    await ka.save_image_generation_history(
        db=db,
        user_id=3,
        prompt="p",
        negative_prompt="",
        image_paths=["/tmp/a.png"],
        generation_type="text-to-image",
        params={"w": 1},
        seed=5,
    )
    assert db.commits == 1
    assert db.added[0].negative_prompt is None


@pytest.mark.asyncio
async def test_save_image_generation_history_rolls_back_on_error():
    class _BadDB(_DB):
        def add(self, record):
            raise TypeError("bad record")

    db = _BadDB()
    await ka.save_image_generation_history(
        db, 3, "p", "", ["/tmp/a.png"], "t", {}, None
    )
    assert db.rollbacks == 1


def test_load_custom_image_styles_parses_markdown(monkeypatch):
    skill = "# Neon Glow\nbright neon\nlines\n# Ink Wash\nsoft ink\n"

    class _Registry:
        def get(self, name):
            return skill

    import app.services.skill_registry as registry_module

    monkeypatch.setattr(registry_module, "get_registry", lambda: _Registry())
    styles = ka._load_custom_image_styles()
    assert styles["neon_glow"] == "bright neon\nlines"
    assert styles["ink_wash"] == "soft ink"


def test_load_custom_image_styles_skips_leading_text_and_empty_tail(monkeypatch):
    skill = "intro line\n# Style Only"

    class _Registry:
        def get(self, name):
            return skill

    import app.services.skill_registry as registry_module

    monkeypatch.setattr(registry_module, "get_registry", lambda: _Registry())
    assert ka._load_custom_image_styles() == {}


def test_load_custom_image_styles_handles_missing_or_bad(monkeypatch):
    import app.services.skill_registry as registry_module

    class _Registry:
        def get(self, name):
            return None

    monkeypatch.setattr(registry_module, "get_registry", lambda: _Registry())
    assert ka._load_custom_image_styles() == {}

    def _boom():
        raise RuntimeError("no registry")

    monkeypatch.setattr(registry_module, "get_registry", _boom)
    assert ka._load_custom_image_styles() == {}


def test_get_style_prompts_merges_custom(monkeypatch):
    monkeypatch.setattr(ka, "_load_custom_image_styles", lambda: {"custom": "desc"})
    styles = ka.get_style_prompts()
    assert styles["custom"] == "desc"
    assert "realistic" in styles


@pytest.mark.asyncio
async def test_generated_resource_serves_owned_history_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "OUTPUT_DIR", tmp_path)
    target = tmp_path / "a.png"
    target.write_bytes(b"img")
    db = _DB([[json.dumps({"type": "image", "path": str(target)})]])
    response = await ka.get_generated_resource("a.png", token=_token(), db=db)
    assert str(response.path) == str(target)


@pytest.mark.asyncio
async def test_generated_resource_falls_back_to_generation_history(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "OUTPUT_DIR", tmp_path)
    (tmp_path / "a.png").write_bytes(b"img")
    db = _DB([[], [["a.png"]]])
    response = await ka.get_generated_resource("a.png", token=_token(), db=db)
    assert str(response.path).endswith("a.png")


@pytest.mark.asyncio
async def test_generated_resource_rejects_traversal_and_bad_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "OUTPUT_DIR", tmp_path)
    with pytest.raises(HTTPException):
        await ka.get_generated_resource("../a.png", token=_token(), db=_DB([[]]))
    with pytest.raises(HTTPException):
        await ka.get_generated_resource("a.txt", token=_token(), db=_DB([[]]))


@pytest.mark.asyncio
async def test_generated_resource_rejects_unowned_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "OUTPUT_DIR", tmp_path)
    (tmp_path / "a.png").write_bytes(b"img")
    with pytest.raises(HTTPException):
        await ka.get_generated_resource("a.png", token=_token(), db=_DB([[], []]))


@pytest.mark.asyncio
async def test_generated_resource_rejects_file_missing_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "OUTPUT_DIR", tmp_path)
    metadata = json.dumps({"type": "image", "path": str(tmp_path / "b.png")})
    with pytest.raises(HTTPException):
        await ka.get_generated_resource("b.png", token=_token(), db=_DB([[metadata]]))


@pytest.mark.asyncio
async def test_generated_resource_skips_malformed_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "OUTPUT_DIR", tmp_path)
    (tmp_path / "a.png").write_bytes(b"img")
    db = _DB([[json.dumps({"type": "text"}), "not-json", json.dumps({"type": "image", "path": str(tmp_path / "a.png")})]])
    response = await ka.get_generated_resource("a.png", token=_token(), db=db)
    assert str(response.path).endswith("a.png")


@pytest.mark.asyncio
async def test_text_to_image_style_and_history(monkeypatch):
    captured = {}

    async def _compress(db, user_id, conversation_id, max_messages):
        return "earlier chat"

    async def _generate(**kwargs):
        captured.update(kwargs)
        return {"success": True, "images": [], "paths": ["/tmp/g.png"]}

    monkeypatch.setattr(ka, "compress_conversation_history", _compress)
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "get_style_prompts", lambda: {"anime": "动漫"})
    monkeypatch.setattr(ka, "text_to_image", _generate)
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    monkeypatch.setattr(ka, "save_image_generation_history", _async_noop)

    request = ka.TextToImageRequest(
        prompt="cat", style="anime", conversation_id=3, seed=9
    )
    result = await ka.text_to_image_api(request, token=_token(), db=_DB())
    assert result["success"] is True
    assert captured["prompt"].startswith("动漫，cat")
    assert "[参考历史]" in captured["prompt"]


@pytest.mark.asyncio
async def test_text_to_image_empty_history_keeps_prompt(monkeypatch):
    captured = {}

    async def _generate(**kwargs):
        captured.update(kwargs)
        return {"success": True, "images": [], "paths": ["/tmp/g.png"]}

    monkeypatch.setattr(ka, "compress_conversation_history", _async_none)
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "text_to_image", _generate)
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    monkeypatch.setattr(ka, "save_image_generation_history", _async_noop)
    await ka.text_to_image_api(
        ka.TextToImageRequest(prompt="plain", conversation_id=3),
        token=_token(),
        db=_DB(),
    )
    assert captured["prompt"] == "plain"


@pytest.mark.asyncio
async def test_text_to_image_cache_hit(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_value("/tmp/c.png"))
    result = await ka.text_to_image_api(
        ka.TextToImageRequest(prompt="x"), token=_token(), db=_DB()
    )
    assert result["cached"] is True


@pytest.mark.asyncio
async def test_text_to_image_fingerprint_cache_hit(monkeypatch):
    calls = []

    async def _cache(*args, **kwargs):
        calls.append(kwargs)
        return "/tmp/c.png" if kwargs.get("fingerprint") else None

    monkeypatch.setattr(ka, "get_cached_image", _cache)
    result = await ka.text_to_image_api(
        ka.TextToImageRequest(prompt="x"), token=_token(), db=_DB()
    )
    assert result["cached"] is True
    assert result["message"] == "使用缓存的图片"


@pytest.mark.asyncio
async def test_text_to_image_result_without_paths_skips_persist(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(
        ka,
        "text_to_image",
        _async_value({"success": False, "images": [], "paths": []}),
    )
    persisted = []
    monkeypatch.setattr(ka, "cache_image_to_history", lambda **k: persisted.append(k))
    result = await ka.text_to_image_api(
        ka.TextToImageRequest(prompt="x"), token=_token(), db=_DB()
    )
    assert result["success"] is False
    assert persisted == []


@pytest.mark.asyncio
async def test_text_to_image_wraps_provider_error(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "text_to_image", _async_raise(OSError("down")))
    with pytest.raises(HTTPException) as exc:
        await ka.text_to_image_api(
            ka.TextToImageRequest(prompt="x"), token=_token(), db=_DB()
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_image_to_image_json_requires_image():
    request = _Request(body={"prompt": "x"})
    with pytest.raises(HTTPException) as exc:
        await ka.image_to_image_api(request, token=_token(), db=_DB())
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_image_to_image_rejects_foreign_file_and_session(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    request = _Request(body={"prompt": "x", "image_path": "/data/ref.png", "conversation_id": 5})
    with pytest.raises(HTTPException) as exc:
        await ka.image_to_image_api(request, token=_token(), db=_DB([None, None]))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_image_to_image_allows_same_conversation_history(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "compress_conversation_history", _async_none)
    monkeypatch.setattr(ka, "image_to_image", _async_value({"success": True, "paths": ["/tmp/o.png"], "images": []}))
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    monkeypatch.setattr(ka, "save_image_generation_history", _async_noop)
    db = _DB([None, _history({"type": "image"})])
    result = await ka.image_to_image_api(
        _Request(body={"prompt": "x", "image_path": "/data/ref.png", "conversation_id": 5}),
        token=_token(),
        db=db,
    )
    assert result["paths"] == ["/tmp/o.png"]


@pytest.mark.asyncio
async def test_image_to_image_missing_file_without_conversation_skips_history(
    monkeypatch,
):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "image_to_image", _async_raise(OSError("down")))
    with pytest.raises(HTTPException):
        await ka.image_to_image_api(
            _Request(body={"prompt": "x", "image_path": "/data/ref.png"}),
            token=_token(),
            db=_DB([None]),
        )


@pytest.mark.asyncio
async def test_image_to_image_history_context_injected(monkeypatch):
    captured = {}

    async def _history(*args, **kwargs):
        return "old"

    async def _generate(**kwargs):
        captured.update(kwargs)
        return {"success": True, "images": [], "paths": ["/tmp/o.png"]}

    monkeypatch.setattr(ka, "compress_conversation_history", _history)
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "image_to_image", _generate)
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    monkeypatch.setattr(ka, "save_image_generation_history", _async_noop)
    await ka.image_to_image_api(
        _Request(body={"prompt": "x", "image_path": "/data/ref.png", "conversation_id": 4}),
        token=_token(),
        db=_DB([SimpleNamespace(), _history({"type": "image"})]),
    )
    assert "[参考历史]" in captured["prompt"]


@pytest.mark.asyncio
async def test_image_to_image_multipart_upload_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "compress_conversation_history", _async_none)
    monkeypatch.setattr(ka, "image_to_image", _async_value({"success": True, "paths": ["/tmp/o.png"], "images": []}))
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    monkeypatch.setattr(ka, "save_image_generation_history", _async_noop)
    cleaned = []
    monkeypatch.setattr(ka, "cleanup_file", lambda p: cleaned.append(p))

    form = {
        "image": UploadFile(file=io.BytesIO(b"x"), filename="r.png"),
        "prompt": "x",
        "strength": "0.6",
        "width": "512",
        "height": "768",
        "steps": "20",
        "cfg_scale": "6.5",
        "num_images": "2",
        "seed": "-1",
        "mask_url": "",
        "conversation_id": "7",
        "style": "anime",
        "api_key_token": "tok",
    }
    result = await ka.image_to_image_api(
        _Request(content_type="multipart/form-data", form_data=form),
        token=_token(),
        db=_DB(),
    )
    assert result["success"] is True
    assert cleaned


@pytest.mark.asyncio
async def test_image_to_image_multipart_form_path_without_file(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_value("/tmp/c.png"))
    form = {"image_path": "/data/ref.png", "prompt": "x"}
    result = await ka.image_to_image_api(
        _Request(content_type="multipart/form-data", form_data=form),
        token=_token(),
        db=_DB([SimpleNamespace()]),
    )
    assert result["cached"] is True


@pytest.mark.asyncio
async def test_image_to_image_wraps_provider_error(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "image_to_image", _async_raise(TypeError("bad")))
    with pytest.raises(HTTPException) as exc:
        await ka.image_to_image_api(
            _Request(body={"prompt": "x", "image_path": "/data/ref.png"}),
            token=_token(),
            db=_DB([SimpleNamespace()]),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_image_to_image_failure_result_skips_cache(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "image_to_image", _async_value({"success": False, "paths": [], "images": []}))
    cached = []
    monkeypatch.setattr(ka, "cache_image_to_history", lambda **k: cached.append(k))
    result = await ka.image_to_image_api(
        _Request(body={"prompt": "x", "image_path": "/data/ref.png"}),
        token=_token(),
        db=_DB([SimpleNamespace()]),
    )
    assert result["cached"] is False
    assert cached == []


@pytest.mark.asyncio
async def test_inpaint_multipart_paths_without_files(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_value("/tmp/c.png"))
    form = {"image_path": "/data/a.png", "mask_path": "/data/m.png", "prompt": "x"}
    result = await ka.inpaint_api(
        _Request(content_type="multipart/form-data", form_data=form),
        token=_token(),
        db=_DB([SimpleNamespace(conversation_id=None), SimpleNamespace()]),
    )
    assert result["cached"] is True


@pytest.mark.asyncio
async def test_inpaint_requires_image():
    with pytest.raises(HTTPException) as exc:
        await ka.inpaint_api(_Request(body={"prompt": "x"}), token=_token(), db=_DB())
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_inpaint_rejects_foreign_file():
    with pytest.raises(HTTPException) as exc:
        await ka.inpaint_api(
            _Request(body={"prompt": "x", "image_path": "/data/a.png"}),
            token=_token(),
            db=_DB([None]),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inpaint_rejects_session_mismatch():
    record = SimpleNamespace(conversation_id=99)
    with pytest.raises(HTTPException) as exc:
        await ka.inpaint_api(
            _Request(body={"prompt": "x", "image_path": "/data/a.png", "conversation_id": 1}),
            token=_token(),
            db=_DB([record]),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inpaint_rejects_foreign_mask():
    record = SimpleNamespace(conversation_id=None)
    with pytest.raises(HTTPException) as exc:
        await ka.inpaint_api(
            _Request(body={"prompt": "x", "image_path": "/data/a.png", "mask_path": "/data/m.png"}),
            token=_token(),
            db=_DB([record, None]),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inpaint_cache_hit(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_value("/tmp/c.png"))
    record = SimpleNamespace(conversation_id=None)
    result = await ka.inpaint_api(
        _Request(body={"prompt": "x", "image_path": "/data/a.png"}),
        token=_token(),
        db=_DB([record]),
    )
    assert result["cached"] is True


@pytest.mark.asyncio
async def test_inpaint_empty_history_and_failed_result(monkeypatch):
    captured = {}

    async def _inpaint(**kwargs):
        captured.update(kwargs)
        return {"success": False, "paths": [], "images": []}

    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "compress_conversation_history", _async_none)
    monkeypatch.setattr(ka, "inpaint_image", _inpaint)
    cached = []
    monkeypatch.setattr(ka, "cache_image_to_history", lambda **k: cached.append(k))
    result = await ka.inpaint_api(
        _Request(body={"prompt": "plain", "image_path": "/data/a.png", "conversation_id": 4}),
        token=_token(),
        db=_DB([SimpleNamespace(conversation_id=4)]),
    )
    assert captured["prompt"] == "plain"
    assert result["success"] is False
    assert cached == []


@pytest.mark.asyncio
async def test_inpaint_success_with_history(monkeypatch):
    captured = {}

    async def _compress(db, user_id, conversation_id, max_messages):
        return "old"

    async def _inpaint(**kwargs):
        captured.update(kwargs)
        return {"success": True, "paths": ["/tmp/o.png"], "images": []}

    monkeypatch.setattr(ka, "compress_conversation_history", _compress)
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "inpaint_image", _inpaint)
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    record = SimpleNamespace(conversation_id=4)
    result = await ka.inpaint_api(
        _Request(body={"prompt": "x", "image_path": "/data/a.png", "mask_path": "/data/m.png", "conversation_id": 4}),
        token=_token(),
        db=_DB([record, record]),
    )
    assert result["paths"] == ["/tmp/o.png"]
    assert "[参考历史]" in captured["prompt"]


@pytest.mark.asyncio
async def test_inpaint_multipart_uploads_and_cleans(tmp_path, monkeypatch):
    monkeypatch.setattr(ka, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "inpaint_image", _async_value({"success": True, "paths": ["/tmp/o.png"], "images": []}))
    monkeypatch.setattr(ka, "cache_image_to_history", _async_noop)
    cleaned = []
    monkeypatch.setattr(ka, "cleanup_file", lambda p: cleaned.append(p))
    form = {
        "image": UploadFile(file=io.BytesIO(b"i"), filename="a.png"),
        "mask": UploadFile(file=io.BytesIO(b"m"), filename="m.png"),
        "prompt": "x",
    }
    result = await ka.inpaint_api(
        _Request(content_type="multipart/form-data", form_data=form),
        token=_token(),
        db=_DB(),
    )
    assert result["success"] is True
    assert len(cleaned) == 2


@pytest.mark.asyncio
async def test_inpaint_wraps_provider_error(monkeypatch):
    monkeypatch.setattr(ka, "get_cached_image", _async_none)
    monkeypatch.setattr(ka, "inpaint_image", _async_raise(RuntimeError("no")))
    with pytest.raises(HTTPException) as exc:
        await ka.inpaint_api(
            _Request(body={"prompt": "x", "image_path": "/data/a.png"}),
            token=_token(),
            db=_DB([SimpleNamespace(conversation_id=None)]),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,provider,kind",
    [
        (ka.generate_avatar_api, "generate_avatar", "avatar"),
        (ka.generate_landscape_api, "generate_landscape", "landscape"),
        (ka.generate_icon_api, "generate_icon", "icon"),
    ],
)
async def test_shortcut_endpoints_persist_and_return(monkeypatch, endpoint, provider, kind):
    persisted = []

    async def _save(**kwargs):
        persisted.append(kwargs)

    monkeypatch.setattr(
        ka, provider, _async_value({"success": True, "paths": ["/tmp/a.png"], "images": []})
    )
    monkeypatch.setattr(ka, "save_image_generation_history", _save)
    result = await endpoint(prompt="x", token=_token(), db=_DB())
    assert result["paths"] == ["/tmp/a.png"]
    assert persisted[0]["generation_type"] == kind


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,provider",
    [
        (ka.generate_avatar_api, "generate_avatar"),
        (ka.generate_landscape_api, "generate_landscape"),
        (ka.generate_icon_api, "generate_icon"),
    ],
)
async def test_shortcut_endpoints_failure_skips_persist(monkeypatch, endpoint, provider):
    monkeypatch.setattr(ka, provider, _async_value({"success": False, "paths": []}))
    persisted = []
    monkeypatch.setattr(ka, "save_image_generation_history", lambda **k: persisted.append(k))
    result = await endpoint(prompt="x", token=_token(), db=_DB())
    assert result["success"] is False
    assert persisted == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,provider",
    [
        (ka.generate_avatar_api, "generate_avatar"),
        (ka.generate_landscape_api, "generate_landscape"),
        (ka.generate_icon_api, "generate_icon"),
    ],
)
async def test_shortcut_endpoints_wrap_error(monkeypatch, endpoint, provider):
    monkeypatch.setattr(ka, provider, _async_raise(OSError("x")))
    with pytest.raises(HTTPException) as exc:
        await endpoint(prompt="x", token=_token(), db=_DB())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_config_payload():
    payload = await ka.get_config()
    assert payload["max_num_images"] == 4
    assert payload["supported_formats"]


@pytest.mark.asyncio
async def test_get_styles_counts_custom(monkeypatch):
    monkeypatch.setattr(ka, "_load_custom_image_styles", lambda: {"mine": "d"})
    payload = await ka.get_styles()
    assert payload["custom_count"] == 1
    assert "mine" in payload["custom_styles"]


async def _async_none(*args, **kwargs):
    return None


async def _async_noop(*args, **kwargs):
    return None


def _async_value(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


def _async_raise(exc):
    async def _inner(*args, **kwargs):
        raise exc

    return _inner
