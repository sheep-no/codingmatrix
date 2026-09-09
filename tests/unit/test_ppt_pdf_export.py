import pytest


@pytest.mark.asyncio
async def test_pdf_export_converts_pptx_to_requested_path(tmp_path, monkeypatch):
    from app.api.v1 import aiGeneratorPptx

    pptx_path = tmp_path / "task.pptx"
    pdf_path = tmp_path / "task.pdf"
    pptx_path.write_bytes(b"pptx")

    def fake_run(command, **_kwargs):
        (tmp_path / "task.pdf").write_bytes(b"pdf")
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    await aiGeneratorPptx._convert_pptx_to_pdf(pptx_path, pdf_path)
    assert pdf_path.read_bytes() == b"pdf"
