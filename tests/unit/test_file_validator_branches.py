"""file_validator 的文件拒绝、MIME 嗅探与 SVG/压缩包深度校验测试。"""

import io
import zipfile

import pytest

import app.core.file_validator as fv
from app.core.config import settings as app_settings
from app.core.file_validator import (
    detect_mime_type,
    generate_safe_filename,
    is_safe_filename,
    validate_archive_content,
    validate_file_content,
    validate_file_path,
    validate_svg_content,
)


def _zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class TestContentRejections:
    def test_empty_content(self):
        with pytest.raises(ValueError, match="文件不能为空"):
            validate_file_content(b"", "a.txt")

    def test_oversized_content(self, monkeypatch):
        monkeypatch.setattr(app_settings, "MAX_UPLOAD_SIZE_MB", 0)

        with pytest.raises(ValueError, match="文件大小超过限制"):
            validate_file_content(b"x", "a.txt")

    def test_missing_extension(self):
        with pytest.raises(ValueError, match="文件必须包含扩展名"):
            validate_file_content(b"hello", "file")

    def test_disallowed_mime(self):
        with pytest.raises(ValueError, match="不允许的文件类型"):
            validate_file_content(b"\x00\x01binary", "a.bin")

    def test_extension_mime_mismatch(self):
        with pytest.raises(ValueError, match="不匹配"):
            validate_file_content(b"%PDF-1.4", "a.png")

    def test_unknown_extension_skips_mime_match(self):
        mime, safe = validate_file_content(b"plain text", "notes.custom")

        assert mime == "text/plain"
        assert safe.endswith(".custom")

    def test_svg_with_script_rejected(self):
        with pytest.raises(ValueError, match="SVG 文件包含不允许的内容"):
            validate_file_content(b"<svg><script>x</script></svg>", "a.svg")

    def test_safe_svg_accepted(self):
        mime, _ = validate_file_content(b"<svg><rect/></svg>", "a.svg")

        assert mime == "image/svg+xml"

    def test_zip_with_unsafe_entry_rejected(self):
        payload = _zip_bytes({"../escape.txt": "x"})

        with pytest.raises(ValueError, match="压缩包包含不允许的文件类型"):
            validate_file_content(payload, "a.zip")


class TestPathRejections:
    def _settings(self, monkeypatch, max_mb=10):
        monkeypatch.setattr(app_settings, "MAX_UPLOAD_SIZE_MB", max_mb)

    def test_empty_file(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.txt"
        path.write_bytes(b"")

        with pytest.raises(ValueError, match="文件不能为空"):
            validate_file_path(path, "a.txt")

    def test_oversized_file(self, tmp_path, monkeypatch):
        self._settings(monkeypatch, max_mb=0)
        path = tmp_path / "a.txt"
        path.write_bytes(b"x")

        with pytest.raises(ValueError, match="文件大小超过限制"):
            validate_file_path(path, "a.txt")

    def test_missing_extension(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a"
        path.write_bytes(b"hello")

        with pytest.raises(ValueError, match="文件必须包含扩展名"):
            validate_file_path(path, "a")

    def test_disallowed_mime(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.bin"
        path.write_bytes(b"\x00\x01")

        with pytest.raises(ValueError, match="不允许的文件类型"):
            validate_file_path(path, "a.bin")

    def test_mime_mismatch(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.png"
        path.write_bytes(b"%PDF-1.4")

        with pytest.raises(ValueError, match="不匹配"):
            validate_file_path(path, "a.png")

    def test_svg_dangerous_pattern_rejected(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.svg"
        path.write_bytes(b"<svg onload=alert(1)></svg>")

        with pytest.raises(ValueError, match="SVG 文件包含不允许的内容"):
            validate_file_path(path, "a.svg")

    def test_svg_safe_file_accepted(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.svg"
        path.write_bytes(b"<svg><rect/></svg>")

        mime, safe = validate_file_path(path, "a.svg")

        assert mime == "image/svg+xml"
        assert safe.endswith(".svg")

    def test_zip_unsafe_entry_rejected(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.zip"
        path.write_bytes(_zip_bytes({"../escape.txt": "x"}))

        with pytest.raises(ValueError, match="压缩包包含不允许的文件名"):
            validate_file_path(path, "a.zip")

    def test_zip_with_safe_entries_accepted(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.zip"
        path.write_bytes(_zip_bytes({"inside.txt": "x"}))

        mime, _ = validate_file_path(path, "a.zip")

        assert mime == "application/zip"

    def test_corrupt_zip_wrapped_error(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.zip"
        path.write_bytes(b"PK\x03\x04not-a-real-archive")

        with pytest.raises(ValueError, match="压缩包验证失败"):
            validate_file_path(path, "a.zip")

    def test_non_zip_archive_skips_zip_block(self, tmp_path, monkeypatch):
        self._settings(monkeypatch)
        path = tmp_path / "a.tar"
        path.write_bytes(b"ustar")

        with pytest.raises(ValueError, match="不匹配"):
            validate_file_path(path, "a.tar")


class TestDetectMime:
    @pytest.mark.parametrize(
        "prefix,expected",
        [
            (b"\x89PNG\r\n\x1a\n", "image/png"),
            (b"\xff\xd8\xff", "image/jpeg"),
            (b"GIF87a", "image/gif"),
            (b"GIF89a", "image/gif"),
            (b"%PDF", "application/pdf"),
            (b"PK\x03\x04", "application/zip"),
            (b"PK\x05\x06", "application/zip"),
            (b"\x1f\x8b\x08", "application/x-gzip"),
            (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
            (b"Rar!\x1a\x07", "application/x-rar-compressed"),
            (b"{", "application/json"),
            (b"<?xml", "application/xml"),
            (b"<svg", "image/svg+xml"),
            (b"<!DOCTYPE html", "text/html"),
            (b"<html", "text/html"),
            (b"#", "text/plain"),
        ],
    )
    def test_magic_signatures(self, prefix, expected):
        assert detect_mime_type(prefix + b"payload") == expected

    def test_tar_signature_at_offset(self):
        content = b"\x00" * 257 + b"ustar" + b"\x00"

        assert detect_mime_type(content) == "application/x-tar"

    def test_json_object_in_text(self):
        assert detect_mime_type(b'  {"a": 1}  ') == "application/json"

    def test_invalid_json_falls_through(self):
        assert detect_mime_type(b"  {not json}") == "text/plain"

    def test_svg_in_text(self):
        assert detect_mime_type(b"prefix <SVG xmlns='x'>") == "image/svg+xml"

    def test_xml_in_text(self):
        assert detect_mime_type(b"prefix <?xml version='1.0'?>") == "application/xml"

    def test_binary_with_nul_is_octet_stream(self):
        assert detect_mime_type(b"abc\x00def") == "application/octet-stream"

    def test_invalid_utf8_is_octet_stream(self):
        assert detect_mime_type(b"\xff\xfe\xfd") == "application/octet-stream"


class TestSvgContent:
    @pytest.mark.parametrize(
        "payload",
        [
            b"<script>",
            b"javascript:void(0)",
            b"vbscript:x",
            b"onerror=x",
            b"onload=x",
            b"onclick=x",
            b"onmouseover=x",
            b"onmouseout=x",
            b"onfocus=x",
            b"onblur=x",
            b"<!ENTITY x>",
            b"<!DOCTYPE svg>",
            b"system",
            b"public",
            b"<iframe>",
            b"<object>",
            b"<embed>",
        ],
    )
    def test_dangerous_patterns(self, payload, capsys):
        assert validate_svg_content(payload) is False
        assert "检测到 SVG 中的危险模式" in capsys.readouterr().out

    def test_safe_svg(self):
        assert validate_svg_content(b"<svg><rect/></svg>") is True

    def test_decode_failure_logged(self, capsys):
        class BrokenContent:
            def decode(self, *_args, **_kwargs):
                raise RuntimeError("boom")

        assert validate_svg_content(BrokenContent()) is False
        assert "SVG 验证错误" in capsys.readouterr().out


class TestArchiveContent:
    def test_non_zip_returns_true(self):
        assert validate_archive_content(b"anything", ".tar") is True

    def test_absolute_path_rejected(self, capsys):
        payload = _zip_bytes({"/etc/passwd": "x"})

        assert validate_archive_content(payload, ".zip") is False
        assert "绝对路径" in capsys.readouterr().out

    def test_traversal_rejected(self, capsys):
        payload = _zip_bytes({"../x": "x"})

        assert validate_archive_content(payload, ".zip") is False
        assert "路径穿越" in capsys.readouterr().out

    def test_unsafe_name_component_rejected(self, capsys):
        payload = _zip_bytes({"bad:name.txt": "x"})

        assert validate_archive_content(payload, ".zip") is False
        assert "不安全的文件名组件" in capsys.readouterr().out

    def test_zip_bomb_size_rejected(self, monkeypatch, capsys):
        class Info:
            filename = "big.txt"
            file_size = 501 * 1024 * 1024
            compress_size = 1024

        class FakeZip:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def infolist(self):
                return [Info()]

        monkeypatch.setattr(fv.zipfile, "ZipFile", FakeZip)

        assert validate_archive_content(b"x", ".zip") is False
        assert "解压大小超过限制" in capsys.readouterr().out

    def test_high_compression_ratio_rejected(self, monkeypatch, capsys):
        class Info:
            filename = "compress.txt"
            file_size = 10000
            compress_size = 1

        class FakeZip:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def infolist(self):
                return [Info()]

        monkeypatch.setattr(fv.zipfile, "ZipFile", FakeZip)

        assert validate_archive_content(b"x", ".zip") is False
        assert "压缩比异常" in capsys.readouterr().out

    def test_safe_zip(self):
        assert validate_archive_content(_zip_bytes({"ok.txt": "x"}), ".zip") is True

    def test_corrupt_zip_logs_error(self, capsys):
        assert validate_archive_content(b"not a zip", ".zip") is False
        assert "压缩包验证错误" in capsys.readouterr().out


class TestFilenameHelpers:
    @pytest.mark.parametrize("name", ["a/b.txt", "a\\b.txt", "..", "a<b", "a>b", "a:b", 'a"b', "a|b", "a?b", "a*b", "a\x00b", "x" * 256])
    def test_unsafe_names(self, name):
        assert is_safe_filename(name) is False

    def test_safe_name(self):
        assert is_safe_filename("report_2026.txt") is True

    def test_generate_keeps_lowercase_extension(self):
        name = generate_safe_filename("Report.PNG")

        assert name.endswith(".png")
        assert len(name) == 32 + 4

    def test_generate_single_char_extension(self):
        assert generate_safe_filename("main.c").endswith(".c")

    def test_generate_rejects_invalid_extension(self):
        with pytest.raises(ValueError, match="无效的扩展名"):
            generate_safe_filename("weird.file-name")
