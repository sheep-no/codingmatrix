"""Batch 25 coverage gaps: cache validity, chunking, outline and evaluation."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from PIL import Image

from app.agent import evaluation_matrix as eval_module
from app.agent.database_profiles import DEFAULT_DATABASE_PROFILES
from app.agent.dependency_rules import infer_file_type_fallback
from app.agent.evaluation_matrix import (
    FIXED_CRUD_CASES,
    EvaluationRegistry,
    _p95,
    _summarize_strategy,
)
from app.core.time import utcnow_naive
from app.db import add_history as add_history_module
from app.models.file import File
from app.schema.ppt_outline import OutlineSlide, OutlineUpdateRequest
from app.utils.dynamic_chunker import DynamicChunker
from app.utils.pptx.visual_regression import compare_images
from app.utils.pptx.visual_regression import build_baseline_manifest, compare_baseline_manifest


def test_parse_cache_invalid_when_expiry_in_past():
    file = File(filename="a.txt", file_path="/x", file_size=1, user_id=1)
    file.parsed_content = "cached"
    file.parsed_at = utcnow_naive() - timedelta(hours=2)
    file.cache_expire_at = utcnow_naive() - timedelta(hours=1)

    assert file.is_parse_cache_valid() is False


def test_package_init_file_is_config_type():
    assert (
        infer_file_type_fallback("pkg/__init__.py", package_init_filename="__init__.py")
        == "config"
    )


def test_chunker_ignores_zero_duration():
    chunker = DynamicChunker()
    before = chunker.get_chunk_size()

    assert chunker.adjust_chunk_size(0, 1024) == before
    assert chunker.upload_speed_history == []


def test_chunker_keeps_size_between_thresholds():
    chunker = DynamicChunker()
    before = chunker.get_chunk_size()

    # 5MB / 1s = 5MB/s：既不快也不慢
    assert chunker.adjust_chunk_size(1.0, 5 * 1024 * 1024) == before
    assert chunker.upload_speed_history == [5 * 1024 * 1024]


def test_invalidate_history_caches_swallows_import_failure(monkeypatch):
    records = []

    class _Capture:
        def warning(self, message):
            records.append(message)

    monkeypatch.setattr(add_history_module, "logger", _Capture())
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "app.utils.cache_decorator":
            raise RuntimeError("cache down")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    asyncio.run(add_history_module.invalidate_history_caches())

    assert records == ["缓存失效失败: cache down"]


def test_compare_images_reports_size_mismatch(tmp_path: Path):
    expected = tmp_path / "expected.png"
    actual = tmp_path / "actual.png"
    Image.new("RGB", (4, 4), "white").save(expected)
    Image.new("RGB", (5, 5), "white").save(actual)

    result = compare_images(expected, actual)

    assert result["reason"] == "image_size_mismatch"
    assert result["changed_ratio"] == 1.0


def test_baseline_comparison_matching_slides_stays_clean():
    manifest = build_baseline_manifest(
        [{"id": "s1", "slide_type": "cover", "elements": []}]
    )
    result = compare_baseline_manifest(manifest, manifest)
    assert result == {"matches": True, "changed_slides": []}


def test_outline_slide_requires_content_or_asset():
    with pytest.raises(ValueError, match="内容块或素材意图"):
        OutlineSlide(id="slide-1", position=0)


def test_outline_update_template_none_passes_through():
    assert OutlineUpdateRequest().template_id is None
    assert OutlineUpdateRequest.resolve_template(None) is None
    assert OutlineUpdateRequest(template_id="modern").template_id == "modern"


def test_registry_rejects_duplicate_case():
    duplicate = FIXED_CRUD_CASES[0]
    with pytest.raises(ValueError, match="duplicate evaluation case"):
        EvaluationRegistry(cases=[duplicate, duplicate])


def test_registry_build_report_uses_registered_cases():
    registry = EvaluationRegistry(cases=[])
    assert registry.cases == ()
    assert registry.build_report([]).missing_case_ids == ()


def test_p95_of_empty_and_single_values():
    assert _p95([]) == 0.0
    assert _p95([1.25]) == 1.25


def test_strategy_summary_for_empty_records():
    summary = _summarize_strategy("spec_first", [])

    assert summary.strategy == "spec_first"
    assert summary.total == 0
    assert summary.p95_seconds == 0.0


def test_database_registry_all_deduplicates_profiles():
    profiles = DEFAULT_DATABASE_PROFILES.all()
    assert len(profiles) == len(set(profiles))
    assert len(profiles) >= 1
