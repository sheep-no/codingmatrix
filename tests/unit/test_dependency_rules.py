"""
依赖规则定义单元测试

覆盖：
- DEPENDENCY_RULES 结构完整性
- PATH_TYPE_RULES 规则正确性
- EXTENSION_TYPE_MAP 映射完整性
- 规则之间的引用一致性
"""

import pytest
from app.agent.dependency_rules import (
    DEPENDENCY_RULES,
    PATH_TYPE_RULES,
    EXTENSION_TYPE_MAP,
)


class TestDependencyRules:
    def test_is_dict(self):
        assert isinstance(DEPENDENCY_RULES, dict)

    def test_config_has_no_deps(self):
        assert DEPENDENCY_RULES["config"] == []

    def test_env_has_no_deps(self):
        assert DEPENDENCY_RULES["env"] == []

    def test_model_depends_on_database(self):
        assert "database" in DEPENDENCY_RULES["model"]

    def test_service_depends_on_model(self):
        assert "model" in DEPENDENCY_RULES["service"]

    def test_api_depends_on_service(self):
        assert "service" in DEPENDENCY_RULES["api"]

    def test_test_depends_on_model(self):
        assert "model" in DEPENDENCY_RULES["test"]

    def test_frontend_types_depends_on_api(self):
        assert "api" in DEPENDENCY_RULES["frontend_types"]

    def test_frontend_component_depends_on_frontend_api(self):
        assert "frontend_api" in DEPENDENCY_RULES["frontend_component"]

    def test_all_deps_referenced_exist(self):
        """All dependency targets should be valid rule keys."""
        all_types = set(DEPENDENCY_RULES.keys())
        for type_name, deps in DEPENDENCY_RULES.items():
            for dep in deps:
                assert dep in all_types, f"{type_name} depends on unknown type: {dep}"

    def test_no_self_dependency(self):
        for type_name, deps in DEPENDENCY_RULES.items():
            assert type_name not in deps, f"{type_name} has self-dependency"

    def test_readme_no_deps(self):
        assert DEPENDENCY_RULES["readme"] == []

    def test_docs_no_deps(self):
        assert DEPENDENCY_RULES["docs"] == []

    def test_repository_depends_on_model(self):
        assert "model" in DEPENDENCY_RULES["repository"]

    def test_migration_depends_on_model_and_database(self):
        assert "model" in DEPENDENCY_RULES["migration"]
        assert "database" in DEPENDENCY_RULES["migration"]


class TestPathTypeRules:
    def test_is_list_of_tuples(self):
        assert isinstance(PATH_TYPE_RULES, list)
        for rule in PATH_TYPE_RULES:
            assert isinstance(rule, tuple)
            assert len(rule) == 2

    def test_requirements_txt_is_config(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["requirements.txt"] == "config"

    def test_package_json_is_config(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["package.json"] == "config"

    def test_env_is_env(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict[".env"] == "env"

    def test_dockerfile_is_dockerfile(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["Dockerfile"] == "dockerfile"

    def test_docker_compose(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["docker-compose.yml"] == "docker_compose"
        assert rules_dict["docker-compose.yaml"] == "docker_compose"

    def test_models_dir_is_model(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["models/"] == "model"
        assert rules_dict["models.py"] == "model"

    def test_services_dir_is_service(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["services/"] == "service"

    def test_api_dir_is_api(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["api/"] == "api"

    def test_frontend_components(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["src/components/"] == "frontend_component"
        assert rules_dict["src/pages/"] == "frontend_page"

    def test_test_dirs(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["tests/"] == "test"
        assert rules_dict["test/"] == "test"

    def test_migration_dir(self):
        rules_dict = dict(PATH_TYPE_RULES)
        assert rules_dict["migrations/"] == "migration"

    def test_all_types_referenced_in_rules(self):
        """All types used in PATH_TYPE_RULES should exist in DEPENDENCY_RULES."""
        all_types = set(DEPENDENCY_RULES.keys())
        for path, file_type in PATH_TYPE_RULES:
            assert file_type in all_types, f"Path '{path}' maps to unknown type: {file_type}"


class TestExtensionTypeMap:
    def test_is_dict(self):
        assert isinstance(EXTENSION_TYPE_MAP, dict)

    def test_js_is_frontend_component(self):
        assert EXTENSION_TYPE_MAP[".js"] == "frontend_component"

    def test_ts_is_frontend_types(self):
        assert EXTENSION_TYPE_MAP[".ts"] == "frontend_types"

    def test_vue_is_frontend_component(self):
        assert EXTENSION_TYPE_MAP[".vue"] == "frontend_component"

    def test_html_is_frontend_page(self):
        assert EXTENSION_TYPE_MAP[".html"] == "frontend_page"

    def test_css_is_frontend_style(self):
        assert EXTENSION_TYPE_MAP[".css"] == "frontend_style"

    def test_json_is_config(self):
        assert EXTENSION_TYPE_MAP[".json"] == "config"

    def test_yaml_is_config(self):
        assert EXTENSION_TYPE_MAP[".yaml"] == "config"
        assert EXTENSION_TYPE_MAP[".yml"] == "config"

    def test_sql_is_migration(self):
        assert EXTENSION_TYPE_MAP[".sql"] == "migration"

    def test_env_is_env(self):
        assert EXTENSION_TYPE_MAP[".env"] == "env"

    def test_md_is_docs(self):
        assert EXTENSION_TYPE_MAP[".md"] == "docs"

    def test_all_ext_types_in_dependency_rules(self):
        """All types in EXTENSION_TYPE_MAP should exist in DEPENDENCY_RULES."""
        all_types = set(DEPENDENCY_RULES.keys())
        for ext, file_type in EXTENSION_TYPE_MAP.items():
            assert file_type in all_types, f"Extension {ext} maps to unknown type: {file_type}"

    def test_all_extensions_start_with_dot(self):
        for ext in EXTENSION_TYPE_MAP.keys():
            assert ext.startswith("."), f"Extension {ext} doesn't start with dot"


class TestCrossReference:
    def test_no_circular_dependency(self):
        """Detect circular dependencies using DFS."""
        visited = set()
        in_stack = set()

        def dfs(node):
            if node in in_stack:
                return True  # circular
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in DEPENDENCY_RULES.get(node, []):
                if dfs(dep):
                    return True
            in_stack.remove(node)
            return False

        for type_name in DEPENDENCY_RULES:
            visited.clear()
            in_stack.clear()
            assert not dfs(type_name), f"Circular dependency detected involving: {type_name}"
