import pytest
from pydantic import ValidationError

from app.schema.ppt_outline import OutlineCreateRequest, OutlineUpdateRequest
from app.utils.pptx.templates.manager import TemplateManager


def test_registered_templates_are_accepted_by_outline_contract():
    for template in TemplateManager().list_templates():
        request = OutlineCreateRequest(topic="Quarterly report", template_id=template["id"])
        assert request.template_id == template["id"]


def test_legacy_alias_is_normalized_for_create_and_update():
    assert OutlineCreateRequest(topic="Report", template_id="business").template_id == "business_report"
    assert OutlineUpdateRequest(template_id="creative").template_id == "pitch_deck"


def test_automatic_selection_uses_scenario():
    request = OutlineCreateRequest(topic="Lesson", template_id="auto", scenario="education")
    assert request.template_id == "education"


@pytest.mark.parametrize("model,values", [
    (OutlineCreateRequest, {"topic": "Report"}),
    (OutlineUpdateRequest, {}),
])
def test_unknown_template_rejected_before_generation(model, values):
    with pytest.raises(ValidationError, match="模板"):
        model(**values, template_id="missing-template")
