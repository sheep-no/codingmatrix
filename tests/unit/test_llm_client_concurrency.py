import pytest

from app.agent.llm_client import (
    MAX_CACHED_MODEL_SEMAPHORES,
    MAX_CONCURRENT_PER_MODEL,
    concurrency_limit_for,
    get_model_semaphore,
)


@pytest.fixture(autouse=True)
def _clean_semaphore_cache():
    """LC8 相关用例会灌入大量动态模型名，用后清理避免污染其它测试。"""
    import app.agent.llm_client as llm_client

    yield
    llm_client._model_semaphores.clear()
    llm_client._model_semaphore_limits.clear()


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


def test_semaphore_cache_is_bounded():
    """LC8：大量动态模型名不得让模块级缓存无界增长。"""
    import app.agent.llm_client as llm_client

    for index in range(MAX_CACHED_MODEL_SEMAPHORES * 3):
        get_model_semaphore(f"dynamic-model-{index}")

    assert len(llm_client._model_semaphores) <= MAX_CACHED_MODEL_SEMAPHORES


def test_in_use_semaphore_not_evicted():
    """LC8：正在使用（槽位被占）的信号量不得被回收，否则并发上限失效。"""
    import app.agent.llm_client as llm_client

    held = get_model_semaphore("held-model")
    held._value -= 1  # 模拟已有一个任务持有槽位

    for index in range(MAX_CACHED_MODEL_SEMAPHORES * 3):
        get_model_semaphore(f"filler-model-{index}")

    assert llm_client._model_semaphores.get("held-model") is held
