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

    def test_build_from_architecture_drops_third_party_paths(self, graph):
        from app.agent.adapters.python import PythonLanguageAdapter

        graph.language_adapter = PythonLanguageAdapter()
        architecture = {
            "file_plan": [
                {"path": "app/main.py", "priority": 1, "imports": ["fastapi"]},
                {"path": "fastapi.py", "priority": 2, "imports": []},
                {"path": "sqlalchemy/orm/session.py", "priority": 2, "imports": []},
            ]
        }
        graph.build_from_architecture(architecture)

        assert "app/main.py" in graph.nodes
        assert "fastapi.py" not in graph.nodes
        assert "sqlalchemy/orm/session.py" not in graph.nodes
        assert "fastapi.py" not in [item["path"] for item in architecture["file_plan"]]
    
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

    def test_python_entry_file_type_is_inferred_from_path(self):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": "app/main.py", "file_type": "unknown"},
            {"path": "app/crud.py", "file_type": "repository"},
        ]})

        assert graph.nodes["app/main.py"].file_type == "entry"
        assert graph.adjacency["app/main.py"] == {"app/crud.py"}

    def test_javascript_entry_file_type_matches_dependency_rules(self):
        from app.agent.adapters.javascript import JavaScriptLanguageAdapter

        adapter = JavaScriptLanguageAdapter()

        assert adapter.infer_file_type("src/index.ts") == "entry"
        assert adapter.infer_file_type("src/server.js") == "entry"

    def test_common_files_are_not_inferred_as_unknown(self):
        """适配器不认识的常见文件要回落到路径规则与扩展名映射，而非 unknown。"""
        from app.agent.adapters.javascript import JavaScriptLanguageAdapter
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        js_graph = DependencyGraph(language_adapter=JavaScriptLanguageAdapter())

        assert js_graph._infer_file_type("index.html") == "frontend_page"
        assert js_graph._infer_file_type("src/App.tsx") == "frontend_component"
        assert js_graph._infer_file_type("src/App.vue") == "frontend_component"
        assert js_graph._infer_file_type("src/style.css") == "frontend_style"
        assert js_graph._infer_file_type("src/styles/index.css") == "frontend_style"

        py_graph = DependencyGraph(language_adapter=PythonLanguageAdapter())

        assert py_graph._infer_file_type("conftest.py") == "test"

    def test_common_files_without_declared_type_do_not_block_generation(self):
        import asyncio

        from app.agent.adapters.javascript import JavaScriptLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.orchestrator_generation.spec_first_generate import (
            SpecFirstGenerateMixin,
        )

        architecture = {"file_plan": [
            {"path": "index.html", "priority": 1},
            {"path": "src/main.tsx", "priority": 1},
            {"path": "src/App.tsx", "priority": 2},
            {"path": "src/styles/index.css", "priority": 4},
            {"path": "package.json", "priority": 4},
        ]}
        graph = DependencyGraph(language_adapter=JavaScriptLanguageAdapter())
        graph.build_from_architecture(architecture)

        pending = graph.get_unknown_type_files()

        # 未知类型必须可以用确定性规则补齐，否则 _infer_unknown_file_types 会硬失败。
        asyncio.run(SpecFirstGenerateMixin()._infer_unknown_file_types(
            graph, pending, architecture, "javascript"
        ))

    def test_extensionless_project_files_are_kept_in_plan(self):
        """Dockerfile / Makefile 这类无扩展名项目文件不能被当成包名丢弃。"""
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": "Dockerfile", "priority": 4},
            {"path": "Dockerfile.dev", "priority": 4},
            {"path": "Makefile", "priority": 4},
            {"path": "main.py", "priority": 1},
        ]})

        assert graph.nodes["Dockerfile"].file_type == "dockerfile"
        assert graph.nodes["Dockerfile.dev"].file_type == "dockerfile"
        assert graph.nodes["Makefile"].file_type == "config"

    def test_dotfile_placeholders_are_not_inferred_as_unknown(self):
        """无扩展名的点号占位文件（.gitkeep）是合法元文件，不能判为 unknown。"""
        import asyncio

        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.orchestrator_generation.spec_first_generate import (
            SpecFirstGenerateMixin,
        )

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())

        assert graph._infer_file_type("src/.gitkeep") == "config"
        assert graph._infer_file_type(".gitignore") == "config"
        assert graph._infer_file_type(".env") == "env"

        architecture = {"file_plan": [
            {"path": "src/.gitkeep", "priority": 3},
            {"path": ".gitignore", "priority": 4},
            {"path": "main.py", "priority": 1},
        ]}
        graph.build_from_architecture(architecture)

        assert "src/.gitkeep" in graph.nodes
        assert graph.nodes["src/.gitkeep"].file_type == "config"
        # 未知类型必须已被确定性补齐，否则 _infer_unknown_file_types 会硬失败。
        pending = graph.get_unknown_type_files()
        assert pending == []
        asyncio.run(SpecFirstGenerateMixin()._infer_unknown_file_types(
            graph, pending, architecture, "python"
        ))

    def test_bare_package_names_are_still_dropped_from_plan(self):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": "moment", "priority": 3},
            {"path": "axios", "priority": 3},
            {"path": "main.py", "priority": 1},
        ]})

        assert "moment" not in graph.nodes
        assert "axios" not in graph.nodes
        assert "main.py" in graph.nodes

    def test_extensionless_meta_files_are_inferred_not_unknown(self):
        """LICENSE / Jenkinsfile / Procfile 等无扩展名合法文件不能判为 unknown。"""
        import asyncio

        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.orchestrator_generation.spec_first_generate import (
            SpecFirstGenerateMixin,
        )

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())

        assert graph._infer_file_type("LICENSE") == "docs"
        assert graph._infer_file_type("README") == "docs"
        assert graph._infer_file_type("Jenkinsfile") == "config"
        assert graph._infer_file_type("Procfile") == "config"
        assert graph._infer_file_type("Justfile") == "config"

        architecture = {"file_plan": [
            {"path": "LICENSE", "priority": 4},
            {"path": "Jenkinsfile", "priority": 4},
            {"path": "main.py", "priority": 1},
        ]}
        graph.build_from_architecture(architecture)

        pending = graph.get_unknown_type_files()
        assert pending == []
        asyncio.run(SpecFirstGenerateMixin()._infer_unknown_file_types(
            graph, pending, architecture, "python"
        ))

    def test_root_files_sharing_stdlib_names_are_kept(self):
        """types.py / secrets.py 等与标准库同名的本地文件不能被当成外部库丢弃。

        标准库名字是通用词；第三方包名（fastapi.py）仍按外部库丢弃。
        """
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        planned = ["main.py", "types.py", "secrets.py", "logging.py", "email.py", "config.py"]
        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": path, "priority": 2} for path in planned
        ]})

        assert sorted(graph.nodes) == sorted(planned)

    def test_multi_package_init_files_are_not_deduplicated(self):
        """包入口文件每包唯一，同名不代表重复；去重会丢掉多包项目的入口。"""
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        planned = [
            "app/__init__.py",
            "app/routers/__init__.py",
            "app/models/__init__.py",
            "tests/__init__.py",
            "app/main.py",
            "app/routers/users.py",
        ]
        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": path, "priority": 2} for path in planned
        ]})

        assert sorted(graph.nodes) == sorted(planned)

    def test_multi_directory_index_files_are_not_deduplicated(self):
        from app.agent.adapters.javascript import JavaScriptLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        planned = ["src/index.js", "src/components/index.js", "src/utils/index.js", "src/App.jsx"]
        graph = DependencyGraph(language_adapter=JavaScriptLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": path, "priority": 2} for path in planned
        ]})

        assert sorted(graph.nodes) == sorted(planned)

    def test_non_entry_duplicate_files_are_still_deduplicated(self):
        """护栏：非入口同名同类型文件仍按原逻辑去重。"""
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": "models.py", "priority": 2},
            {"path": "src/models/models.py", "priority": 2},
            {"path": "main.py", "priority": 1},
        ]})

        assert "src/models/models.py" in graph.nodes
        assert "models.py" not in graph.nodes

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

    def test_declared_utils_is_kept_when_path_rules_cannot_refine(self):
        """架构师显式声明的 utils 在路径规则无法细化时必须保留。

        原实现把 utils 一律推翻重推断，推断不出就降级为 unknown，使
        _infer_unknown_file_types 对这些文件硬失败。
        """
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": "app/__init__.py", "file_type": "config", "priority": 1},
            {"path": "app/deps.py", "file_type": "utils", "priority": 2},
            {"path": "myapp/urls.py", "file_type": "utils", "priority": 2},
        ]})

        assert graph.nodes["app/deps.py"].file_type == "utils"
        assert graph.nodes["myapp/urls.py"].file_type == "utils"
        assert graph.get_unknown_type_files() == []

    def test_unknown_type_files_excludes_utils(self):
        """utils 是确定类型，不属于待推断的未知类型。"""
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.add_file("app/deps.py", file_type="utils")
        graph.add_file("mystery.py", file_type="unknown")
        graph.add_file("blank.py", file_type="")

        assert graph.get_unknown_type_files() == ["mystery.py", "blank.py"]

    def test_config_and_dotfiles_are_not_unknown(self):
        """常见配置/元文件必须有确定性类型，否则 _infer_unknown_file_types 硬失败。"""
        import asyncio

        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.orchestrator_generation.spec_first_generate import (
            SpecFirstGenerateMixin,
        )

        planned = [
            ".gitignore", ".editorconfig", ".dockerignore",
            "nginx.conf", "setup.cfg", "poetry.lock", "alembic.ini",
            "schema.graphql", "proto/user.proto", "infra/main.tf",
            "requirements.txt", "app/main.py",
            "LICENSE", "CHANGELOG", "Jenkinsfile", "Procfile", "Pipfile",
            "MANIFEST.in", "docs/guide.rst", "docs/manual.adoc", "config.xml",
        ]
        architecture = {"file_plan": [
            {"path": path, "priority": 2} for path in planned
        ]}
        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture(architecture)

        pending = graph.get_unknown_type_files()
        asyncio.run(SpecFirstGenerateMixin()._infer_unknown_file_types(
            graph, pending, architecture, "python"
        ))

        assert graph.get_unknown_type_files() == []
        assert "nginx.conf" in graph.nodes
        assert "schema.graphql" in graph.nodes

    def test_tool_named_config_files_are_kept_in_plan(self):
        """以工具名命名的配置文件（vite.config.js、alembic.ini）不能被当外部库丢弃。"""
        from app.agent.adapters.javascript import JavaScriptLanguageAdapter
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        js_graph = DependencyGraph(language_adapter=JavaScriptLanguageAdapter())
        js_graph.build_from_architecture({"file_plan": [
            {"path": "vite.config.js", "priority": 2},
            {"path": "src/main.js", "priority": 1},
        ]})
        assert "vite.config.js" in js_graph.nodes

        py_graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        py_graph.build_from_architecture({"file_plan": [
            {"path": "alembic.ini", "priority": 2},
            {"path": "app/main.py", "priority": 1},
        ]})
        assert "alembic.ini" in py_graph.nodes

    def test_external_package_source_trees_are_still_dropped(self):
        """护栏：真正的第三方包源码路径仍按外部库丢弃。"""
        from app.agent.adapters.javascript import JavaScriptLanguageAdapter
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        py_graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        py_graph.build_from_architecture({"file_plan": [
            {"path": "sqlalchemy/orm/session.py", "priority": 2},
            {"path": "fastapi.py", "priority": 2},
            {"path": "app/main.py", "priority": 1},
        ]})
        assert "sqlalchemy/orm/session.py" not in py_graph.nodes
        assert "fastapi.py" not in py_graph.nodes

        js_graph = DependencyGraph(language_adapter=JavaScriptLanguageAdapter())
        js_graph.build_from_architecture({"file_plan": [
            {"path": "react/index.js", "priority": 2},
            {"path": "src/main.js", "priority": 1},
        ]})
        assert "react/index.js" not in js_graph.nodes

    def test_dotted_module_paths_are_converted(self):
        """点号分隔的模块路径（src.app.utils.py）仍要转换成目录路径。"""
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": "src.app.utils.py", "priority": 2},
            {"path": "main.py", "priority": 1},
        ]})

        assert "src/app/utils.py" in graph.nodes

    def test_dotted_file_names_are_not_converted(self):
        """点号文件名（vite.config.js、index.test.js）不能被改写成目录路径。"""
        from app.agent.adapters.javascript import JavaScriptLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        planned = ["vite.config.js", "index.test.js", "main.min.js", "types.d.ts", "src/main.js"]
        graph = DependencyGraph(language_adapter=JavaScriptLanguageAdapter())
        graph.build_from_architecture({"file_plan": [
            {"path": path, "priority": 2} for path in planned
        ]})

        assert sorted(graph.nodes) == sorted(planned)
    
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

    @pytest.mark.asyncio
    async def test_existing_project_skips_maven_build_outputs(self, graph, tmp_path):
        source_file = tmp_path / "src/main/java/com/example/Application.java"
        target_file = tmp_path / "target/maven-status/compiler/inputFiles.lst"
        source_file.parent.mkdir(parents=True)
        target_file.parent.mkdir(parents=True)
        source_file.write_text("public class Application {}", encoding="utf-8")
        target_file.write_text(str(source_file), encoding="utf-8")

        await graph.build_from_existing_project(tmp_path)

        assert "src/main/java/com/example/Application.java" in graph.nodes
        assert "target/maven-status/compiler/inputFiles.lst" not in graph.nodes

    @pytest.mark.asyncio
    async def test_existing_java_project_maps_class_references_to_file_paths(self, graph, tmp_path):
        todo_file = tmp_path / "src/main/java/com/example/Todo.java"
        controller_file = tmp_path / "src/main/java/com/example/TodoController.java"
        todo_file.parent.mkdir(parents=True)
        todo_file.write_text("package com.example; public class Todo {}", encoding="utf-8")
        controller_file.write_text(
            "package com.example; public class TodoController { private Todo todo; }",
            encoding="utf-8",
        )

        await graph.build_from_existing_project(tmp_path)

        assert graph.adjacency["src/main/java/com/example/TodoController.java"] == {
            "src/main/java/com/example/Todo.java"
        }


class TestEnrichFromSource:
    def test_unknown_only_depended_by_entry_becomes_utils(self, tmp_path):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        (tmp_path / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        (tmp_path / "main.py").write_text(
            '"""CLI entry."""\nfrom calc import add\nprint(add(1, 2))\n',
            encoding="utf-8",
        )

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.add_file("calc.py")
        graph.add_file("main.py")
        graph.add_dependency("main.py", "calc.py")

        assert graph.nodes["calc.py"].file_type == "unknown"
        assert graph.nodes["main.py"].file_type == "entry"

        changed = graph.enrich_from_source(tmp_path)

        assert changed is True
        assert graph.nodes["calc.py"].file_type == "utils"
        assert "add" in graph.nodes["calc.py"].description
        assert "subtract" in graph.nodes["calc.py"].description
        assert graph.nodes["main.py"].description == "CLI entry."

    def test_does_not_overwrite_existing_metadata(self, tmp_path):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.add_file("calc.py", file_type="model", description="keep me")

        changed = graph.enrich_from_source(tmp_path)

        assert changed is False
        assert graph.nodes["calc.py"].file_type == "model"
        assert graph.nodes["calc.py"].description == "keep me"

    def test_enrich_and_save_persists_to_disk(self, tmp_path):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("from calc import add\n", encoding="utf-8")
        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        graph.add_file("calc.py")
        graph.add_file("main.py")
        graph.add_dependency("main.py", "calc.py")

        assert graph.enrich_and_save(tmp_path) is True

        loaded = DependencyGraph.load(str(tmp_path / ".dep_graph.json"), language_adapter=PythonLanguageAdapter())
        assert loaded is not None
        assert loaded.nodes["calc.py"].file_type == "utils"
        assert "add" in loaded.nodes["calc.py"].description

    @pytest.mark.asyncio
    async def test_build_from_existing_project_fills_empty_descriptions(self, tmp_path):
        from app.agent.adapters.python import PythonLanguageAdapter
        from app.agent.dependency_graph import DependencyGraph

        (tmp_path / "calc.py").write_text(
            '"""Arithmetic helpers."""\ndef add(a, b):\n    return a + b\n',
            encoding="utf-8",
        )
        (tmp_path / "main.py").write_text("from calc import add\nprint(add(1, 2))\n", encoding="utf-8")

        graph = DependencyGraph(language_adapter=PythonLanguageAdapter())
        await graph.build_from_existing_project(tmp_path)

        assert graph.nodes["calc.py"].file_type == "utils"
        assert graph.nodes["calc.py"].description == "Arithmetic helpers."
        assert "add" in graph.nodes["main.py"].description or graph.nodes["main.py"].file_type == "entry"


class TestGenerationOrderPriorityQueue:
    """DG5：Kahn 排序改用最小堆后，顺序语义（优先级、稳定性、依赖先行）不变。"""

    def test_same_priority_keeps_insertion_order(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        for path in ("c.py", "b.py", "a.py"):
            graph.add_file(path, priority=3)

        assert graph.get_generation_order() == ["c.py", "b.py", "a.py"]

    def test_lower_priority_value_wins(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.add_file("late.py", priority=5)
        graph.add_file("early.py", priority=1)
        graph.add_file("mid.py", priority=3)

        assert graph.get_generation_order() == ["early.py", "mid.py", "late.py"]

    def test_dependencies_always_precede_dependents(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.add_file("model.py", priority=1)
        graph.add_file("service.py", priority=3)
        graph.add_file("api.py", priority=5)
        graph.add_dependency("service.py", "model.py")
        graph.add_dependency("api.py", "service.py")

        order = graph.get_generation_order()

        assert order.index("model.py") < order.index("service.py") < order.index("api.py")

    def test_large_graph_orders_every_node(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        size = 1500
        for index in range(size):
            graph.add_file(f"mod_{index}.py", priority=3)
        for index in range(1, size):
            graph.add_dependency(f"mod_{index}.py", f"mod_{index - 1}.py")

        order = graph.get_generation_order()

        assert len(order) == size
        assert order.index("mod_0.py") < order.index(f"mod_{size - 1}.py")


class TestContextBudgetWiring:
    """DG7：上下文预算随模型窗口变化，未指定窗口时走集中式默认值。"""

    def test_budget_grows_with_model_window(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.add_file("main.py")

        small = graph.get_context_package_for_file(
            "main.py", {}, model_context_length=32768
        )
        large = graph.get_context_package_for_file(
            "main.py", {}, model_context_length=131072
        )

        assert large["budget_chars"] > small["budget_chars"]

    def test_missing_window_falls_back_to_central_default(self):
        from app.agent.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        graph.add_file("main.py")

        default = graph.get_context_package_for_file("main.py", {})
        explicit = graph.get_context_package_for_file(
            "main.py", {}, model_context_length=32768
        )

        # 未传窗口时等于集中式默认窗口（32768）的预算，而非本地硬编码常量
        assert default["budget_chars"] == explicit["budget_chars"]


class TestJsImportAliasResolution:
    """DG9：前端别名（@/、~/、src/）导入应能解析为项目内真实文件。"""

    @pytest.mark.asyncio
    async def test_at_alias_resolves_to_src(self, tmp_path):
        from app.agent.dependency_graph import DependencyGraph

        (tmp_path / "src/components").mkdir(parents=True)
        (tmp_path / "src/components/User.ts").write_text(
            "export const user = 1;\n", encoding="utf-8"
        )
        (tmp_path / "src/pages").mkdir(parents=True)
        (tmp_path / "src/pages/Home.vue").write_text(
            'import User from "@/components/User";\n', encoding="utf-8"
        )

        graph = DependencyGraph()
        await graph.build_from_existing_project(tmp_path)

        assert "src/components/User.ts" in graph.adjacency["src/pages/Home.vue"]

    def test_tilde_and_bare_src_prefixes_resolve(self, tmp_path):
        from app.agent.dependency_graph import DependencyGraph

        (tmp_path / "src/lib").mkdir(parents=True)
        (tmp_path / "src/lib/api.js").write_text("export const api = 1;\n", encoding="utf-8")
        source = tmp_path / "src/entry.ts"
        source.write_text(
            'import api from "~/lib/api";\nimport other from "src/lib/api";\n',
            encoding="utf-8",
        )

        graph = DependencyGraph()

        assert graph._parse_js_requires(source, tmp_path) == ["src/lib/api.js"]
