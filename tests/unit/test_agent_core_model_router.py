"""`agent_core.FileModelRouter.get_model_for_task` 关键词匹配误判回归。

原实现用 `kw in requirement` 子串匹配所有关键词，单个 ASCII 关键词会命中
无关单词（"ui" 命中 "build"，"api" 命中 "capital"），把任务误路由到
前端/后端模型。修复后 ASCII 关键词按整词匹配，CJK 关键词仍按子串匹配。
"""
from app.utils.agent_core import FileModelRouter


def _router() -> FileModelRouter:
    router = FileModelRouter()
    router.frontend_model = "FRONT"
    router.backend_model = "BACK"
    return router


def test_ui_inside_build_does_not_route_to_frontend():
    # "build" 含子串 "ui"，原实现凭空多出 1 个前端命中，与真实后端命中
    # ("api") 打平后按默认落到前端模型；修复后应正确路由到后端
    assert _router().get_model_for_task("Build a REST API service") == "BACK"


def test_api_inside_other_word_does_not_route_to_backend():
    # "capital" 含子串 "api"，原实现会误判为后端需求
    assert _router().get_model_for_task("Analyse the capital market reports") == "FRONT"


def test_whole_word_keywords_still_route():
    assert _router().get_model_for_task("Build a REST API with a database") == "BACK"
    assert _router().get_model_for_task("Create a Vue page") == "FRONT"


def test_cjk_keywords_match_by_substring():
    assert _router().get_model_for_task("开发一个前端页面") == "FRONT"
    assert _router().get_model_for_task("实现用户后端接口") == "BACK"
