from app.agent.llm_client import concurrency_limit_for, MAX_CONCURRENT_PER_MODEL


def test_glm_flash_concurrency_limits():
    assert concurrency_limit_for("glm-4.7-flash") == 1
    assert concurrency_limit_for("GLM-4.7-Flash") == 1
    assert concurrency_limit_for("glm-4-flash-250414") == 20
    assert concurrency_limit_for("glm-z1-flash") == 6


def test_unknown_model_uses_default_limit():
    assert concurrency_limit_for("Qwen/Qwen3-8B") == MAX_CONCURRENT_PER_MODEL
    assert concurrency_limit_for("") == MAX_CONCURRENT_PER_MODEL
