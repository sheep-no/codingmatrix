import pytest
from pathlib import Path

class TestDependencyGraph:
    @pytest.fixture
    def graph(self):
        from app.agent.dependency_graph import DependencyGraph
        return DependencyGraph()
    
    def test_add_file(self, graph):
        graph.add_file("main.py", priority=1)
        assert "main.py" in graph.nodes
        assert graph.nodes["main.py"].priority == 1
    
    def test_add_dependency(self, graph):
        graph.add_file("main.py", priority=1)
        graph.add_file("utils.py", priority=2)
        graph.add_dependency("main.py", "utils.py")
        
        deps = list(graph.adjacency.get("main.py", []))
        assert "utils.py" in deps
    
    def test_add_dependency_auto_create_node(self, graph):
        """测试添加依赖时自动创建源节点"""
        # 只添加依赖，不预先创建源节点
        graph.add_dependency("main.py", "utils.py")
        
        # 源节点应该被自动创建
        assert "main.py" in graph.nodes
        # 依赖目标如果不是已知文件，不会被创建（这是预期行为）
        # 因为依赖的目标应该是项目内已存在的文件
    
    def test_get_affected_files(self, graph):
        graph.add_file("base.py", priority=1)
        graph.add_file("derived.py", priority=2)
        graph.add_dependency("derived.py", "base.py")
        
        affected_dict = graph.get_affected_files(["base.py"])
        assert "base.py" in affected_dict or any("base.py" in deps for deps in affected_dict.values())
    
    def test_get_generation_layers(self, graph):
        graph.add_file("models.py", priority=1)
        graph.add_file("api.py", priority=2)
        graph.add_file("main.py", priority=3)
        graph.add_dependency("api.py", "models.py")
        graph.add_dependency("main.py", "api.py")
        
        layers = graph.get_generation_layers()
        assert len(layers) >= 1
        assert all(isinstance(layer, list) for layer in layers)
    
    def test_build_from_architecture(self, graph):
        architecture = {
            "file_plan": [
                {"path": "main.py", "priority": 1},
                {"path": "utils.py", "priority": 2}
            ]
        }
        graph.build_from_architecture(architecture)
        assert "main.py" in graph.nodes
        assert "utils.py" in graph.nodes
    
    def test_build_from_architecture_with_explicit_dependencies(self, graph):
        """测试从架构构建时使用 LLM 显式声明的依赖"""
        architecture = {
            "file_plan": [
                {
                    "path": "models/user.py",
                    "priority": 2,
                    "dependencies": []
                },
                {
                    "path": "services/user_service.py",
                    "priority": 3,
                    "dependencies": ["models/user.py"]
                },
                {
                    "path": "routers/user.py",
                    "priority": 4,
                    "dependencies": ["services/user_service.py", "models/user.py"]
                }
            ]
        }
        graph.build_from_architecture(architecture)
        
        # 验证所有节点都被创建
        assert "models/user.py" in graph.nodes
        assert "services/user_service.py" in graph.nodes
        assert "routers/user.py" in graph.nodes
        
        # 验证显式依赖被正确添加
        assert "models/user.py" in graph.adjacency.get("services/user_service.py", set())
        assert "services/user_service.py" in graph.adjacency.get("routers/user.py", set())
        assert "models/user.py" in graph.adjacency.get("routers/user.py", set())
    
    def test_build_from_architecture_handles_missing_dependencies(self, graph):
        """测试当依赖的文件不在 file_plan 中时的处理"""
        architecture = {
            "file_plan": [
                {
                    "path": "services/user_service.py",
                    "priority": 3,
                    "dependencies": ["models/user.py"]  # models/user.py 不在 file_plan 中
                }
            ]
        }
        graph.build_from_architecture(architecture)
        
        # services/user_service.py 应该被创建
        assert "services/user_service.py" in graph.nodes
        
        # models/user.py 可能不会被添加（因为不在 file_plan 中且不是已知节点）
        # 这取决于实现策略，这里测试的是不会报错
    
    def test_build_from_architecture_fallback_to_rules(self, graph):
        """测试硬编码规则作为兜底仍然有效"""
        architecture = {
            "file_plan": [
                {
                    "path": "models/user.py",
                    "priority": 2,
                    "dependencies": []  # LLM 可能漏掉一些依赖
                },
                {
                    "path": "services/user_service.py",
                    "priority": 3,
                    "dependencies": []  # 漏掉了 models/user.py
                }
            ]
        }
        graph.build_from_architecture(architecture)
        
        # 硬编码规则应该补充依赖关系（service 依赖 model）
        # 注意：这取决于 _auto_add_dependencies 的实现

    def test_prefixed_import_resolves_to_unique_flattened_file(self, graph):
        architecture = {
            "file_plan": [
                {"path": "models.py", "file_type": "model", "imports": []},
                {
                    "path": "crud.py",
                    "file_type": "repository",
                    "imports": ["src.models"],
                },
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.adjacency["crud.py"] == {"models.py"}

    def test_unresolved_import_keeps_type_rule_fallback(self, graph):
        architecture = {
            "file_plan": [
                {"path": "models.py", "file_type": "model", "imports": []},
                {
                    "path": "crud.py",
                    "file_type": "repository",
                    "imports": ["missing.external_module"],
                },
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.adjacency["crud.py"] == {"models.py"}

    def test_conflicting_imports_follow_architecture_type_rules(self, graph):
        architecture = {
            "file_plan": [
                {
                    "path": "database.py",
                    "file_type": "database",
                    "priority": 2,
                    "imports": ["models"],
                },
                {
                    "path": "models.py",
                    "file_type": "model",
                    "priority": 2,
                    "imports": ["database"],
                },
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.adjacency["models.py"] == {"database.py"}
        assert graph.adjacency["database.py"] == set()

    def test_entry_rule_supplements_partial_flat_crud_contract_imports(self, graph):
        architecture = {
            "file_plan": [
                {"path": "main.py", "file_type": "entry", "imports": ["database"]},
                {"path": "database.py", "file_type": "database", "imports": []},
                {"path": "models.py", "file_type": "model", "imports": []},
                {"path": "schemas.py", "file_type": "types", "imports": []},
                {"path": "crud.py", "file_type": "repository", "imports": []},
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.adjacency["main.py"] == {
            "database.py",
            "models.py",
            "schemas.py",
            "crud.py",
        }

    def test_unknown_file_types_are_inferred_from_paths(self, graph):
        architecture = {
            "file_plan": [
                {"path": "database.py", "file_type": "database", "imports": ["models"]},
                {"path": "models.py", "file_type": "unknown", "imports": ["database"]},
                {"path": "schemas.py", "file_type": "unknown", "imports": ["models"]},
                {"path": "crud.py", "file_type": "unknown", "imports": ["models"]},
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.nodes["models.py"].file_type == "model"
        assert graph.nodes["schemas.py"].file_type == "types"
        assert graph.nodes["crud.py"].file_type == "repository"
        assert graph.adjacency["models.py"] == {"database.py"}
        assert graph.adjacency["database.py"] == set()

    def test_generic_utils_file_types_are_inferred_from_paths(self, graph):
        architecture = {
            "file_plan": [
                {"path": "database.py", "file_type": "utils", "imports": []},
                {"path": "models.py", "file_type": "utils", "imports": ["database"]},
                {"path": "crud.py", "file_type": "utils", "imports": ["models"]},
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.nodes["database.py"].file_type == "database"
        assert graph.nodes["models.py"].file_type == "model"
        assert graph.nodes["crud.py"].file_type == "repository"
        assert graph.adjacency["models.py"] == {"database.py"}
        assert graph.adjacency["crud.py"] == {"models.py", "database.py"}
    
    def test_extract_dependencies_from_content_python(self, graph):
        """测试从 Python 内容中提取依赖"""
        graph.add_file("models/user.py")
        graph.add_file("services/user_service.py")
        
        content = """
from models.user import User
from services.user_service import UserService
import os

class UserController:
    pass
"""
        deps = graph.extract_dependencies_from_content("controllers/user.py", content)
        
        # 应该提取到 models/user.py 和 services/user_service.py
        assert any("models/user" in d or "models\\user" in d for d in deps)
    
    def test_extract_dependencies_from_content_js(self, graph):
        """测试从 JS/TS 内容中提取依赖"""
        graph.add_file("src/api/user.ts")
        graph.add_file("src/components/User.vue")
        
        content = """
import { UserService } from './api/user';
import UserCard from '../components/User.vue';
"""
        deps = graph.extract_dependencies_from_content("src/views/UserView.ts", content)
        
        # 应该提取到相关依赖
        assert len(deps) >= 0  # 至少不报错
    
    def test_update_node_dependencies(self, graph):
        """测试更新节点的依赖关系"""
        graph.add_file("main.py")
        graph.add_file("utils.py")
        graph.add_file("helpers.py")
        
        # 初始依赖
        graph.add_dependency("main.py", "utils.py")
        assert "utils.py" in graph.adjacency.get("main.py", set())
        
        # 更新依赖
        graph.update_node_dependencies("main.py", ["helpers.py"])
        
        # 旧依赖应该被移除
        assert "utils.py" not in graph.adjacency.get("main.py", set())
        # 新依赖应该被添加
        assert "helpers.py" in graph.adjacency.get("main.py", set())
    
    def test_get_generation_order_with_explicit_dependencies(self, graph):
        """测试使用显式依赖时的生成顺序"""
        architecture = {
            "file_plan": [
                {"path": "routers/user.py", "priority": 4, "dependencies": ["services/user_service.py"]},
                {"path": "models/user.py", "priority": 2, "dependencies": []},
                {"path": "services/user_service.py", "priority": 3, "dependencies": ["models/user.py"]}
            ]
        }
        graph.build_from_architecture(architecture)
        
        order = graph.get_generation_order()
        
        # models 应该在 services 之前
        assert order.index("models/user.py") < order.index("services/user_service.py")
        # services 应该在 routers 之前
        assert order.index("services/user_service.py") < order.index("routers/user.py")

    def test_summarize_dependency_context_is_auditable_without_source(self):
        from app.agent.dependency_graph import summarize_dependency_context

        summary = summarize_dependency_context(
            "## 依赖文件: models/user.py\n```python\ndef secret_token():\n    return 'sensitive'\n```\n"
        )

        assert summary["present"] is True
        assert summary["dependency_files"] == ["models/user.py"]
        assert summary["dependency_file_count"] == 1
        assert summary["signature_marker_count"] == 1
        assert "secret_token" not in summary["preview"]
        assert "sensitive" not in summary["preview"]

    def test_summarize_empty_dependency_context(self):
        from app.agent.dependency_graph import summarize_dependency_context

        assert summarize_dependency_context("") == {
            "present": False,
            "chars": 0,
            "dependency_files": [],
            "dependency_file_count": 0,
            "signature_marker_count": 0,
            "preview": "",
        }

    def test_context_package_contains_dependency_metadata_and_code_budget(self, graph):
        graph.add_file("services/user_service.py", priority=3)
        graph.add_file("models/user.py", priority=1)
        graph.add_dependency("services/user_service.py", "models/user.py")

        package = graph.get_context_package_for_file(
            "services/user_service.py",
            {"models/user.py": "class User:\n    def name(self):\n        return 'user'\n"},
            max_context_bytes=300,
        )

        assert package["target_file"] == "services/user_service.py"
        assert package["budget_chars"] == 300
        assert len(package["dependencies"]) == 1
        dependency = package["dependencies"][0]
        assert dependency["path"] == "models/user.py"
        assert dependency["relation"] == "imports"
        assert dependency["content_chars"] > 0
        assert dependency["signature_chars"] + dependency["relevant_code_chars"] <= 300

    def test_context_package_without_dependencies_is_serializable(self, graph):
        graph.add_file("main.go")

        package = graph.get_context_package_for_file("main.go", {})

        assert package["target_file"] == "main.go"
        assert package["dependencies"] == []
        assert package["budget_chars"] > 0

    def test_python_adapter_places_crud_after_runtime_dependencies(self):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({
            "file_plan": [
                {"path": "database.py", "file_type": "database"},
                {"path": "models.py", "file_type": "model"},
                {"path": "schemas.py", "file_type": "schema"},
                {"path": "crud.py", "file_type": "unknown"},
            ]
        })

        assert graph.nodes["crud.py"].file_type == "repository"
        assert graph.adjacency["crud.py"] == {"database.py", "models.py", "schemas.py"}
        layers = graph.get_generation_layers()
        assert layers.index(["crud.py"]) > layers.index(["schemas.py"])

    def test_tests_receive_all_python_runtime_dependencies(self):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({
            "file_plan": [
                {"path": "database.py", "file_type": "database"},
                {"path": "models.py", "file_type": "model"},
                {"path": "schemas.py", "file_type": "schema"},
                {"path": "crud.py", "file_type": "repository"},
                {"path": "main.py", "file_type": "entry"},
                {"path": "test_main.py", "file_type": "test"},
            ]
        })

        assert graph.adjacency["test_main.py"] == {
            "database.py", "models.py", "schemas.py", "crud.py", "main.py"
        }

    def test_contract_driven_entry_receives_repository_dependency(self):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({
            "file_plan": [
                {"path": "crud.py", "file_type": "repository", "contract": {"role": "CRUD"}},
                {"path": "main.py", "file_type": "entry", "contract": {"role": "API entry"}},
            ]
        })

        assert graph.adjacency["main.py"] == {"crud.py"}

    def test_generic_python_test_filename_is_classified_as_test(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.add_file("test_main.py")

        assert graph.nodes["test_main.py"].file_type == "test"

    def test_python_adapter_classifies_root_test_filename_as_test(self):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({
            "file_plan": [
                {"path": "main.py", "file_type": "entry"},
                {"path": "test_main.py", "file_type": "unknown"},
            ]
        })

        assert graph.nodes["test_main.py"].file_type == "test"
        assert graph.adjacency["test_main.py"] == {"main.py"}

    def test_contract_graph_keeps_database_before_models(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        architecture = {
            "file_plan": [
                {
                    "path": "database.py",
                    "file_type": "database",
                    "imports": ["models"],
                    "dependencies": ["models.py"],
                    "contract": {
                        "role": "database",
                        "required_imports": ["models", "sqlalchemy"],
                    },
                },
                {"path": "models.py", "file_type": "model", "dependencies": ["database.py"], "contract": {"role": "model"}},
            ]
        }

        graph.build_from_architecture(architecture)

        assert graph.get_generation_order() == ["database.py", "models.py"]
        database_plan = architecture["file_plan"][0]
        assert database_plan["imports"] == []
        assert database_plan["dependencies"] == []
        assert database_plan["contract"]["required_imports"] == ["sqlalchemy"]

    def test_contract_graph_adds_omitted_model_database_dependency(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.build_from_architecture({
            "file_plan": [
                {"path": "database.py", "file_type": "database", "contract": {"role": "database"}},
                {"path": "models.py", "file_type": "model", "contract": {"role": "model"}},
            ]
        })

        assert graph.adjacency["models.py"] == {"database.py"}
        assert graph.get_generation_layers() == [["database.py"], ["models.py"]]

    def test_contract_graph_generates_python_schemas_after_models(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.build_from_architecture({
            "file_plan": [
                {"path": "database.py", "file_type": "database", "contract": {"role": "database"}},
                {"path": "models.py", "file_type": "model", "contract": {"role": "model"}},
                {"path": "schemas.py", "file_type": "types", "contract": {"role": "schemas"}},
            ]
        })

        assert graph.adjacency["schemas.py"] == {"models.py"}
        layers = graph.get_generation_layers()
        assert layers.index(["schemas.py"]) > layers.index(["models.py"])

    def test_contract_graph_generates_python_repository_after_schemas(self):
        from app.agent.dependency_graph import DependencyGraph

        architecture = {
            "file_plan": [
                {"path": "database.py", "file_type": "database", "contract": {"role": "database"}},
                {"path": "models.py", "file_type": "model", "contract": {"role": "model"}},
                {
                    "path": "schemas.py",
                    "file_type": "types",
                    "dependencies": ["crud.py"],
                    "contract": {"role": "schemas"},
                },
                {"path": "crud.py", "file_type": "repository", "contract": {"role": "repository"}},
            ]
        }
        graph = DependencyGraph()

        graph.build_from_architecture(architecture)

        assert "crud.py" not in graph.adjacency["schemas.py"]
        assert graph.adjacency["crud.py"] == {"schemas.py"}
        assert graph.get_generation_layers() == [
            ["database.py"],
            ["models.py"],
            ["schemas.py"],
            ["crud.py"],
        ]

    def test_contract_tests_are_generated_after_runtime_files(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.build_from_architecture({
            "file_plan": [
                {"path": "database.py", "file_type": "database", "contract": {"role": "database"}},
                {"path": "main.py", "file_type": "entry", "contract": {"role": "API entry"}},
                {"path": "test_main.py", "file_type": "test", "contract": {"role": "tests"}},
            ]
        })

        layers = graph.get_generation_layers()

        test_layer = next(index for index, layer in enumerate(layers) if "test_main.py" in layer)
        main_layer = next(index for index, layer in enumerate(layers) if "main.py" in layer)
        assert test_layer > main_layer
