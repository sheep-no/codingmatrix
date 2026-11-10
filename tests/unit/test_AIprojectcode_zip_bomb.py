"""项目压缩包解压必须有解压后体积上限。

压缩包本身限制 50MB，但 zip 的压缩比可以极高；原实现只校验条目路径与扩展名，
直接把 `zf.read()` 的内容写盘，构造的 zip bomb 可解压出数十 GB 占满磁盘。
"""

import io
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

import app.api.v1.AiProjectCode as code_api


def _zip_bytes(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def _upload(payload: bytes) -> UploadFile:
    return UploadFile(filename="proj.zip", file=io.BytesIO(payload))


async def _run_upload(payload: bytes):
    return await code_api.upload_project_zip(
        file=_upload(payload),
        project_name="proj",
        token={"sub": "1"},
    )


@pytest.mark.asyncio
async def test_zip_bomb_total_size_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path / "user_uploads"))
    monkeypatch.setattr(code_api, "USER_UPLOADS_MAX_UNCOMPRESSED_SIZE", 1024)

    payload = _zip_bytes({"a.py": b"0" * 4096})

    with pytest.raises(HTTPException) as excinfo:
        await _run_upload(payload)

    assert excinfo.value.status_code == 413
    assert "解压后总大小超过限制" in excinfo.value.detail
    assert not (tmp_path / "user_uploads" / "1" / "proj").exists()


@pytest.mark.asyncio
async def test_single_entry_size_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path / "user_uploads"))
    monkeypatch.setattr(code_api, "USER_UPLOADS_MAX_ENTRY_SIZE", 100)

    payload = _zip_bytes({"big.py": b"x" * 500, "small.py": b"x" * 10})

    with pytest.raises(HTTPException) as excinfo:
        await _run_upload(payload)

    assert excinfo.value.status_code == 413
    assert "单文件限制" in excinfo.value.detail


@pytest.mark.asyncio
async def test_normal_zip_still_extracts(monkeypatch, tmp_path):
    monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path / "user_uploads"))

    payload = _zip_bytes({"a.py": b"print(1)", "src/b.js": b"console.log(1)"})

    result = await _run_upload(payload)

    assert result.file_count == 2
    assert (tmp_path / "user_uploads" / "1" / "proj" / "src" / "b.js").exists()


@pytest.mark.asyncio
async def test_disallowed_entries_stay_filtered(monkeypatch, tmp_path):
    """体积校验必须基于过滤后的 safe_files，恶意条目不应参与统计或被写入。"""
    monkeypatch.setattr(code_api, "USER_UPLOADS_DIR", str(tmp_path / "user_uploads"))

    payload = _zip_bytes({"ok.py": b"print(1)", "evil.exe": b"MZ", "../escape.py": b"x"})

    result = await _run_upload(payload)

    assert result.file_count == 1
    assert not (tmp_path / "escape.py").exists()
