from app.utils.pptx.design_tokens import resolve_design_tokens
from app.utils.pptx.scenario import classify_scenario
from app.utils.pptx.templates import TemplateManager


def test_scenario_classifier_uses_general_for_weak_evidence():
    result = classify_scenario("一份演示文稿")
    assert result.scenario == "general"
    assert result.confidence < 0.6


def test_scenario_classifier_identifies_product_pitch():
    result = classify_scenario("产品路演融资发布")
    assert result.scenario == "product_pitch"
    assert result.confidence >= 0.6


def test_template_manager_returns_three_ranked_candidates():
    result = TemplateManager().recommend_for_scenario("季度经营汇报")
    assert len(result["templates"]) >= 3
    assert result["templates"][0] == "business_report"


def test_design_tokens_migrate_legacy_template_fields():
    config = TemplateManager().get_config("minimal")
    tokens = resolve_design_tokens(config)
    assert tokens.version == "1.0"
    assert tokens.typography["body_size"] >= 14
    assert tokens.typography["title_size"] >= 24
    assert tokens.colors["primary"].startswith("#")


def test_generation_pages_share_one_token_version_and_palette():
    manager = TemplateManager()
    tokens = manager.resolve_design_tokens("business_report", version="business-report-v1")
    page_tokens = [tokens for _ in range(50)]

    assert {page.version for page in page_tokens} == {"business-report-v1"}
    assert {tuple(page.colors["chart_series"]) for page in page_tokens} == {
        tuple(tokens.colors["chart_series"])
    }
    assert all(page is tokens for page in page_tokens)
