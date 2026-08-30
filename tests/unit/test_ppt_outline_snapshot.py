from pathlib import Path


def test_incremental_ppt_source_updates_snapshot_after_render():
    source_path = "app/api/v1/aiGeneratorPptx.py"
    source = Path(source_path).read_text(encoding="utf-8")

    render_marker = "generate_pptx_file_enhanced(filepath, merged_outline, new_req, update_progress=update_progress)"
    snapshot_marker = "json.dump(new_slides, f, ensure_ascii=False, indent=2)"

    assert render_marker in source
    assert snapshot_marker in source
    assert source.index(render_marker) < source.index(snapshot_marker)
