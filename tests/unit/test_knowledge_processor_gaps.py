"""knowledge_processor 边界补测：解析回退、分块边界与空向量过滤。"""

import sys
import types

import pytest

from app.utils.aicloud import knowledge_processor as kp


def _chunk(content="原文", index=0):
    return kp.DocumentChunk(
        content=content, chunk_index=index, metadata={}, content_hash="h"
    )


def test_parse_text_file_falls_back_to_gbk(tmp_path):
    path = tmp_path / "gbk.txt"
    path.write_bytes("中文".encode("gbk"))

    assert kp.parse_text_file(str(path)) == "中文"


def test_parse_text_file_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        kp.parse_text_file(str(tmp_path / "missing.txt"))


def test_parse_pdf_uses_pypdf2(tmp_path, monkeypatch):
    pages = [types.SimpleNamespace(extract_text=lambda: "page-1")]
    fake = types.SimpleNamespace(
        PdfReader=lambda _handle: types.SimpleNamespace(pages=pages)
    )
    monkeypatch.setitem(sys.modules, "PyPDF2", fake)
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF")

    assert kp.parse_pdf_file(str(path)) == "page-1\n"


def test_parse_pdf_falls_back_to_pdfplumber(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "PyPDF2", None)
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PyPDF2":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pages = [types.SimpleNamespace(extract_text=lambda: "plumber")]

    class _Pdf:
        def __enter__(self):
            return types.SimpleNamespace(pages=pages)

        def __exit__(self, *_args):
            return False

    plumber = types.SimpleNamespace(open=lambda _path: _Pdf())
    monkeypatch.setitem(sys.modules, "pdfplumber", plumber)
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF")

    assert "plumber" in kp.parse_pdf_file(str(path))


def test_parse_pdf_raises_when_no_library(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"PyPDF2", "pdfplumber"}:
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError):
        kp.parse_pdf_file(str(tmp_path / "doc.pdf"))


def test_parse_pdf_wraps_unexpected_errors(tmp_path, monkeypatch):
    class _Broken:
        def __init__(self, _handle):
            raise RuntimeError("corrupt")

    monkeypatch.setitem(sys.modules, "PyPDF2", types.SimpleNamespace(PdfReader=_Broken))
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF")

    with pytest.raises(RuntimeError, match="corrupt"):
        kp.parse_pdf_file(str(path))


def test_parse_docx_reads_paragraphs(tmp_path, monkeypatch):
    paragraphs = [types.SimpleNamespace(text="a"), types.SimpleNamespace(text="b")]
    monkeypatch.setitem(
        sys.modules, "docx", types.SimpleNamespace(Document=lambda _p: types.SimpleNamespace(paragraphs=paragraphs))
    )

    assert kp.parse_docx_file(str(tmp_path / "a.docx")) == "a\nb"


def test_parse_docx_raises_when_library_missing(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError):
        kp.parse_docx_file(str(tmp_path / "a.docx"))


def test_parse_docx_wraps_unexpected_errors(tmp_path, monkeypatch):
    def boom(_path):
        raise RuntimeError("bad docx")

    monkeypatch.setitem(sys.modules, "docx", types.SimpleNamespace(Document=boom))

    with pytest.raises(RuntimeError, match="bad docx"):
        kp.parse_docx_file(str(tmp_path / "a.docx"))


def test_parse_document_dispatches_by_suffix(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(kp, "parse_text_file", lambda path: called.append(("text", path)) or "t")
    monkeypatch.setattr(kp, "parse_pdf_file", lambda path: called.append(("pdf", path)) or "p")
    monkeypatch.setattr(kp, "parse_docx_file", lambda path: called.append(("docx", path)) or "d")

    assert kp.parse_document("a.pdf") == "p"
    assert kp.parse_document("a.docx") == "d"
    assert kp.parse_document("a.csv") == "t"
    assert kp.parse_document("a.unknown") == "t"
    assert [kind for kind, _ in called] == ["pdf", "docx", "text", "text"]


def test_chunk_text_returns_empty_for_blank():
    assert kp.chunk_text("   \n ") == []


def test_chunk_text_respects_paragraph_boundary():
    text = "第一段内容。" + "填充" * 200 + "。"

    chunks = kp.chunk_text(text, chunk_size=50, chunk_overlap=5)

    assert chunks
    assert chunks[0].content


def test_chunk_text_clamps_excessive_overlap():
    chunks = kp.chunk_text("abcdefghij", chunk_size=4, chunk_overlap=100)

    assert chunks[0].content == "abcd"
    assert chunks[-1].content.endswith("j")
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunk_text_skips_whitespace_only_slice():
    chunks = kp.chunk_text("abcd" + " " * 10 + "efgh", chunk_size=4, chunk_overlap=0)

    assert [chunk.content for chunk in chunks] == ["abcd", "ef", "gh"]


async def test_embed_chunks_rejects_non_sequence_vector(monkeypatch):
    async def fake_get_embedding(*_args, **_kwargs):
        return "not-a-vector"

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", fake_get_embedding)

    assert await kp.embed_chunks([_chunk()]) == []


async def test_embed_chunks_returns_lists(monkeypatch):
    async def fake_get_embedding(*_args, **_kwargs):
        return (0.1, 0.2)

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", fake_get_embedding)
    chunk = _chunk()
    results = await kp.embed_chunks([chunk])

    assert results == [(chunk, [0.1, 0.2])]


def test_cosine_similarity_rejects_dimension_mismatch():
    assert kp.cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_cosine_similarity_rejects_zero_vectors():
    assert kp.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert kp.cosine_similarity([1.0, 1.0], [0.0, 0.0]) == 0.0


def test_search_similar_chunks_drops_non_positive_scores():
    good = _chunk("good")
    orthogonal = _chunk("orth")

    results = kp.search_similar_chunks(
        [1.0, 0.0],
        [(good, [1.0, 0.0]), (orthogonal, [0.0, 1.0])],
    )

    assert results == [(good, pytest.approx(1.0))]


def test_search_similar_chunks_honors_top_k_and_order():
    first = _chunk("a")
    second = _chunk("b")

    results = kp.search_similar_chunks(
        [1.0, 0.0],
        [(first, [0.5, 0.5]), (second, [1.0, 0.0])],
        top_k=1,
    )

    assert results == [(second, pytest.approx(1.0))]
