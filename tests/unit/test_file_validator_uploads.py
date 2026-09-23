"""file_validator 文本/代码文件与二进制伪装的上传契约回归（FV1）。"""
import io
import tarfile
import zipfile

import pytest

from app.core.file_validator import (
    detect_mime_type,
    validate_file_content,
    validate_file_path,
)


TEXT_CASES = {
    "main.py": b"import os\n\nprint(1)\n",
    "svc.py": b"# comment\nx = 1\n",
    "app.js": b"const a = 1;\nexport default a\n",
    "view.jsx": b"export default function App() { return null }\n",
    "index.ts": b"export const x: number = 1\n",
    "view.tsx": b"export const App = () => null\n",
    "Comp.vue": b"<template><div/></template>\n",
    "Main.java": b"class Main {}\n",
    "util.c": b"int main(void) { return 0; }\n",
    "util.cpp": b"int main() { return 0; }\n",
    "main.go": b"package main\nfunc main() {}\n",
    "lib.rs": b"fn main() {}\n",
    "app.rb": b"puts 1\n",
    "index.html": b"<!DOCTYPE html><html></html>\n",
    "style.css": b"body { color: red; }\n",
    "style.scss": b"$x: 1;\n",
    "config.yaml": b"a: 1\nb: 2\n",
    "config.yml": b"a: 1\n",
    "pyproject.toml": b"[tool]\nname = 'x'\n",
    "setup.ini": b"[meta]\nname = x\n",
    "data.xml": b"<root><a/></root>\n",
    "readme.md": b"# Title\n",
    "notes.txt": b"hello\n",
    "doc.rst": b"Title\n=====\n",
    "array.json": b"[1, 2, 3]\n",
    "object.json": b'{"a": 1}\n',
}


@pytest.mark.parametrize("filename", sorted(TEXT_CASES))
def test_text_and_code_uploads_are_accepted(filename):
    detected_mime, safe_filename = validate_file_content(TEXT_CASES[filename], filename)

    assert detected_mime
    assert safe_filename


@pytest.mark.parametrize("filename", sorted(TEXT_CASES))
def test_text_and_code_uploads_are_accepted_from_path(tmp_path, filename):
    path = tmp_path / filename
    path.write_bytes(TEXT_CASES[filename])

    detected_mime, safe_filename = validate_file_path(path, filename)

    assert detected_mime
    assert safe_filename


@pytest.mark.parametrize(
    "filename,content",
    [
        ("fake.py", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32),
        ("fake.css", b"PK\x03\x04" + b"\x00" * 32),
        ("fake.txt", b"\x1f\x8b\x08" + b"\x00" * 32),
    ],
)
def test_binary_content_disguised_as_text_is_rejected(filename, content):
    with pytest.raises(ValueError):
        validate_file_content(content, filename)


def test_docx_zip_container_is_accepted():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")

    detected_mime, _ = validate_file_content(buffer.getvalue(), "report.docx")

    assert detected_mime == "application/zip"


def test_svg_with_script_is_still_rejected():
    with pytest.raises(ValueError):
        validate_file_content(b"<svg onload=alert(1)></svg>", "evil.svg")


def _make_tar() -> bytes:
    buffer = io.BytesIO()
    payload = b"hello\n"
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("notes.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_tar_magic_is_detected_at_offset_257():
    """tar 魔数在偏移 257，不在文件头（FV4）。"""
    data = _make_tar()

    assert data[:16] != b"ustar"
    assert data[257:262] == b"ustar"
    assert detect_mime_type(data) == "application/x-tar"


def test_tar_upload_is_accepted():
    detected_mime, safe_filename = validate_file_content(_make_tar(), "notes.tar")

    assert detected_mime == "application/x-tar"
    assert safe_filename.endswith(".tar")


def test_tar_upload_is_accepted_from_path(tmp_path):
    path = tmp_path / "notes.tar"
    path.write_bytes(_make_tar())

    detected_mime, safe_filename = validate_file_path(path, "notes.tar")

    assert detected_mime == "application/x-tar"
    assert safe_filename.endswith(".tar")
