from PIL import Image

from app.utils.pptx.visual_regression import build_baseline_manifest, compare_baseline_manifest, compare_images, write_baseline_manifest


def test_baseline_manifest_is_stable_and_hashes_semantic_metadata(tmp_path):
    slides = [{"id": "s1", "slide_type": "cover", "elements": [], "render_metadata": {"token_version": "1.0"}}]
    first = build_baseline_manifest(slides)
    second = build_baseline_manifest(slides)
    assert first == second
    assert first["sha256"]

    path = tmp_path / "baseline.json"
    assert write_baseline_manifest(path, slides) == first
    assert path.exists()


def test_baseline_comparison_reports_changed_slide():
    expected = build_baseline_manifest([{"id": "s1", "slide_type": "cover", "elements": []}])
    actual = build_baseline_manifest([{"id": "s1", "slide_type": "summary", "elements": []}])
    result = compare_baseline_manifest(expected, actual)
    assert result["matches"] is False
    assert result["changed_slides"][0]["index"] == 1


def test_pixel_comparison_reports_small_changes(tmp_path):
    expected_path = tmp_path / "expected.png"
    actual_path = tmp_path / "actual.png"
    Image.new("RGB", (10, 10), "white").save(expected_path)
    actual = Image.new("RGB", (10, 10), "white")
    actual.putpixel((0, 0), (0, 0, 0))
    actual.save(actual_path)

    result = compare_images(expected_path, actual_path, threshold=0.02)
    assert result["matches"] is True
    assert result["changed_ratio"] == 0.01
