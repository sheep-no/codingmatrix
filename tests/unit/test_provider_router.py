from app.utils.aicloud.provider_router import ProviderRouter
from app.utils.aicloud.providers import ModelProvider


def test_glm_z1_flash_routes_to_zhipu():
    router = ProviderRouter()
    assert router.route("glm-z1-flash") == ModelProvider.ZHIPU


def test_glm_z1_flash_does_not_fallback_to_siliconflow():
    router = ProviderRouter()
    fallbacks = router.get_fallback_providers(ModelProvider.ZHIPU, "glm-z1-flash")
    assert ModelProvider.SILICONFLOW not in fallbacks


def test_unmapped_zhipu_model_keeps_siliconflow_fallback():
    router = ProviderRouter()
    fallbacks = router.get_fallback_providers(ModelProvider.ZHIPU)
    assert ModelProvider.SILICONFLOW in fallbacks
