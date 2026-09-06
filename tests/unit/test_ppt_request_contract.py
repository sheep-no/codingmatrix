from app.api.v1.aiGeneratorPptx import PPTGenerationRequest


def test_ppt_request_preserves_frontend_options():
    request = PPTGenerationRequest.model_validate({
        "prompt": "季度业务汇报",
        "template": "modern",
        "slide_count": 8,
        "options": {"auto_images": False, "enable_animation": True},
    })

    assert request.topic == "季度业务汇报"
    assert request.template == "modern"
    assert request.options == {"auto_images": False, "enable_animation": True}
