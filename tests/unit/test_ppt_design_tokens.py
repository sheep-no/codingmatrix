import json

from app.utils.pptx.design_tokens import resolve_design_tokens
from app.utils.pptx.scenario import classify_scenario
from app.utils.pptx.templates import TemplateManager


def test_scenario_classifier_uses_general_for_weak_evidence():
    result = classify_scenario("一份演示文稿")
    assert result.scenario == "general"
    assert result.confidence < 0.6


def test_scenario_classifier_falls_back_for_single_keyword():
    result = classify_scenario("季度")
    assert result.scenario == "general"
    assert result.confidence == 1 / 3


def test_scenario_classifier_identifies_product_pitch():
    result = classify_scenario("产品路演融资发布")
    assert result.scenario == "product_pitch"
    assert result.confidence >= 0.6


def test_template_manager_returns_three_ranked_candidates():
    result = TemplateManager().recommend_for_scenario("季度经营汇报")
    assert len(result["templates"]) >= 3
    assert result["templates"][0] == "business_report"
    assert result["candidates"][0]["preview"]["primary_color"].startswith("#")
    assert result["candidates"][0]["version"] == "1.0"


def test_design_tokens_migrate_legacy_template_fields():
    config = TemplateManager().get_config("minimal")
    tokens = resolve_design_tokens(config)
    assert tokens.version == "1.0"
    assert tokens.typography["body_size"] >= 14
    assert tokens.typography["title_size"] >= 24
    assert tokens.colors["primary"].startswith("#")
    assert set(tokens.colors) >= {"background", "surface", "success", "warning", "error"}
    assert set(tokens.spacing) >= {"grid_columns", "grid_gutter", "block_gap"}
    assert set(tokens.shapes) >= {"shadow", "divider_width", "icon_size"}
    assert set(tokens.image) >= {"mask", "tone", "credit_position"}
    assert set(tokens.chart) >= {"grid_color", "legend_position", "show_labels", "source_style"}


def test_outline_creation_auto_classifies_scenario():
    from app.schema.ppt_outline import OutlineCreateRequest
    from app.services.ppt_outline_service import PPTOutlineService

    draft = PPTOutlineService().create("1", OutlineCreateRequest(topic="产品路演融资发布", num_slides=1))
    assert draft.scenario == "product_pitch"


def test_custom_template_round_trip_persists_migrated_tokens_and_version(tmp_path):
    manager = TemplateManager(template_dir=str(tmp_path))
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "template_id": "legacy",
                "name": "Legacy",
                "name_zh": "旧模板",
                "category": "minimal",
                "description": "旧式扁平模板",
                "primary_color": "123456",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = manager.load_custom_template(str(legacy_path))
    assert config.schema_version == 2
    assert config.version == "1.0"
    config.version = "legacy-v2"
    manager.save_custom_template(config)
    saved = json.loads((tmp_path / "legacy.json").read_text(encoding="utf-8"))

    assert saved["schema_version"] == 2
    assert saved["version"] == "legacy-v2"
    assert all(saved[group] for group in ("colors", "typography", "spacing", "shapes", "image", "chart"))
    reloaded = manager.load_custom_template(str(legacy_path))
    assert resolve_design_tokens(reloaded).version == "legacy-v2"


def test_generation_pages_share_one_token_version_and_palette():
    manager = TemplateManager()
    tokens = manager.resolve_design_tokens("business_report", version="business-report-v1")
    page_tokens = [tokens for _ in range(50)]

    assert {page.version for page in page_tokens} == {"business-report-v1"}
    assert {tuple(page.colors["chart_series"]) for page in page_tokens} == {
        tuple(tokens.colors["chart_series"])
    }
    assert all(page is tokens for page in page_tokens)
