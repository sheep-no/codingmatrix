"""dependency_graph._infer_file_type 路径规则匹配语义测试。

覆盖 DR1（嵌套目录全部漏配）与 DR6（endswith 后缀宽松误报）：
无语言适配器时，PATH_TYPE_RULES 的 fallback 必须按路径段匹配，
使其对 app/api/users.py 之类的嵌套路径生效，且不把 my_config.py
误判为 config.py。
"""

from app.agent.dependency_graph import DependencyGraph


class TestInferFileTypeNestedDirectories:
    def test_nested_backend_directories_are_matched(self):
        graph = DependencyGraph()

        assert graph._infer_file_type("app/api/users.py") == "api"
        assert graph._infer_file_type("app/services/user.py") == "service"
        assert graph._infer_file_type("app/models/user.py") == "model"
        assert graph._infer_file_type("backend/services/user_service.py") == "service"

    def test_nested_tests_directory_is_matched(self):
        graph = DependencyGraph()

        assert graph._infer_file_type("app/tests/test_x.py") == "test"
        assert graph._infer_file_type("src/utils/helpers.py") == "utils"

    def test_top_level_directory_rules_still_apply(self):
        graph = DependencyGraph()

        assert graph._infer_file_type("api/users.py") == "api"
        assert graph._infer_file_type("tests/test_x.py") == "test"


class TestInferFileTypeBoundaries:
    def test_file_name_pattern_requires_path_segment_boundary(self):
        graph = DependencyGraph()

        # my_config.py 不是 config.py，不应命中 ("config.py", "config")
        assert graph._infer_file_type("my_config.py") != "config"
        assert graph._infer_file_type("src/my_config.py") != "config"
        # 完整的 config.py 仍然命中
        assert graph._infer_file_type("app/config.py") == "config"

    def test_suffix_patterns_still_apply(self):
        graph = DependencyGraph()

        assert graph._infer_file_type("app/x_test.py") == "test"
        assert graph._infer_file_type("test_x.py") == "test"
        assert graph._infer_file_type("configs/.env") == "env"
        assert graph._infer_file_type(".env.local") == "env"
        assert graph._infer_file_type("requirements.txt") == "config"

    def test_more_specific_rule_wins_over_shorter_prefix(self):
        graph = DependencyGraph()

        # src/views/ 与 views/ 同时命中时取更长者，避免前端页面被判为后端 view
        assert graph._infer_file_type("src/views/App.vue") == "frontend_page"
        assert graph._infer_file_type("src/components/App.vue") == "frontend_component"
        assert graph._infer_file_type("src/api/client.js") == "frontend_api"
