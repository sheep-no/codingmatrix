from app.agent.llm_client import (
    MAX_CONCURRENT_PER_MODEL,
    concurrency_limit_for,
    get_model_semaphore,
)


def test_glm_flash_concurrency_limits():
    assert concurrency_limit_for("glm-4.7-flash") == 1
    assert concurrency_limit_for("GLM-4.7-Flash") == 1
    assert concurrency_limit_for("glm-4-flash-250414") == 20
    assert concurrency_limit_for("glm-z1-flash") == 6


def test_unknown_model_uses_default_limit():
    assert concurrency_limit_for("Qwen/Qwen3-8B") == MAX_CONCURRENT_PER_MODEL
    assert concurrency_limit_for("") == MAX_CONCURRENT_PER_MODEL


def test_equivalent_model_spellings_share_one_semaphore():
    """同一模型的写法差异不得各自建信号量，否则并发上限形同虚设。"""
    spellings = [
        "glm-4.7-flash",
        "GLM-4.7-Flash",
        "zhipu/glm-4.7-flash",
        " GLM-4.7-Flash ",
    ]

    semaphores = {id(get_model_semaphore(name)) for name in spellings}

    assert len(semaphores) == 1


def test_distinct_models_keep_distinct_semaphores():
    assert id(get_model_semaphore("glm-4.7-flash")) != id(
        get_model_semaphore("glm-4-flash-250414")
    )
