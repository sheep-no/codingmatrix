from app.utils.model_defaults import MODEL_DEFAULTS, get_default_model


def test_default_models_are_resolved_from_unified_config():
    assert get_default_model("code") == "Qwen/Qwen3.5-4B"
    assert get_default_model("reasoning") == "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    assert get_default_model("visual") == "Qwen/Qwen3.5-4B"
    assert get_default_model("embedding") == "BAAI/bge-m3"
    assert MODEL_DEFAULTS["ppt"] == MODEL_DEFAULTS["visual"]
