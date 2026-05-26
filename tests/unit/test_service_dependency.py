"""
测试第三方服务依赖处理 - v4.8.0
"""
import pytest
import tempfile
import shutil
import json
from pathlib import Path


class TestServiceConfigTemplates:
    """服务配置模板库测试"""

    def test_all_service_templates_exist(self):
        """测试 6 种服务模板都存在"""
        from app.agent.service_config_templates import SERVICE_TEMPLATES
        expected = ["redis", "postgresql", "mysql", "mongodb", "rabbitmq", "elasticsearch"]
        for name in expected:
            assert name in SERVICE_TEMPLATES

    def test_redis_template_has_required_fields(self):
        """测试 Redis 模板完整性"""
        from app.agent.service_config_templates import get_service_template
        t = get_service_template("redis")
        assert t.python_packages == ["redis"]
        assert "REDIS_URL" in t.env_vars
        assert t.docker_image == "redis:7-alpine"
        assert t.default_port == 6379
        assert "redis_client" in t.connection_code

    def test_postgresql_template(self):
        """测试 PostgreSQL 模板"""
        from app.agent.service_config_templates import get_service_template
        t = get_service_template("postgresql")
        assert "psycopg2-binary" in t.python_packages
        assert "DATABASE_URL" in t.env_vars
        assert t.default_port == 5432

    def test_detect_services_from_requirement(self):
        """测试从需求文本检测服务"""
        from app.agent.service_config_templates import detect_services_from_requirements
        assert "redis" in detect_services_from_requirements("Redis cache")
        assert "postgresql" in detect_services_from_requirements("PostgreSQL database")
        assert "mongodb" in detect_services_from_requirements("MongoDB nosql")
        assert "rabbitmq" in detect_services_from_requirements("RabbitMQ消息队列")
        assert "elasticsearch" in detect_services_from_requirements("Elasticsearch搜索")
        assert [] == detect_services_from_requirements("简单静态页面")

    def test_detect_multiple_services(self):
        """测试同时检测多个服务"""
        from app.agent.service_config_templates import detect_services_from_requirements
        result = detect_services_from_requirements("Redis + PostgreSQL 的 Web 项目")
        assert "redis" in result
        assert "postgresql" in result

    def test_generate_env_example(self):
        """测试生成 .env.example"""
        from app.agent.service_config_templates import generate_env_example
        env = generate_env_example(["redis", "postgresql"])
        assert "REDIS_URL" in env
        assert "DATABASE_URL" in env
        assert "SECRET_KEY" in env

    def test_generate_docker_compose(self):
        """测试生成 docker-compose.yml"""
        from app.agent.service_config_templates import generate_docker_compose
        compose = generate_docker_compose(["redis"])
        assert "redis" in compose
        assert "redis:7" in compose

    def test_get_python_packages(self):
        """测试获取 Python 包列表"""
        from app.agent.service_config_templates import get_python_packages_for_services
        packages = get_python_packages_for_services(["redis"])
        assert "redis" in packages
        assert "fastapi" in packages

    def test_get_connection_snippets(self):
        """测试获取连接代码片段"""
        from app.agent.service_config_templates import get_connection_snippets
        snippets = get_connection_snippets(["redis"])
        assert "redis_client" in snippets["redis"]


class TestDynamicPackageManager:
    """动态包管理器测试"""

    @pytest.fixture
    def pkg_mgr(self):
        from app.utils.dynamic_package_manager import DynamicPackageManager
        temp_dir = Path(tempfile.mkdtemp())
        mgr = DynamicPackageManager()
        mgr.WHITELIST_FILE = temp_dir / "whitelist.json"
        mgr.EVALUATION_LOG_FILE = temp_dir / "eval_log.json"
        yield mgr
        shutil.rmtree(temp_dir)

    def test_static_whitelist_size(self):
        """测试静态白名单规模"""
        from app.utils.dynamic_package_manager import STATIC_WHITELIST
        assert len(STATIC_WHITELIST) >= 80

    def test_blocked_packages(self):
        """测试黑名单"""
        from app.utils.dynamic_package_manager import BLOCKED_PACKAGES
        assert "requests2" in BLOCKED_PACKAGES
        assert "setup-tools" in BLOCKED_PACKAGES

    def test_is_in_whitelist(self, pkg_mgr):
        """测试白名单检查"""
        assert pkg_mgr.is_in_whitelist("redis") is True
        assert pkg_mgr.is_in_whitelist("unknown-package") is False

    def test_is_blocked(self, pkg_mgr):
        """测试黑名单检查"""
        assert pkg_mgr.is_blocked("requests2") is True
        assert pkg_mgr.is_blocked("redis") is False

    def test_heuristic_evaluate_known_dev_package(self, pkg_mgr):
        """测试启发式评估 - 开发关键词包"""
        result = pkg_mgr._heuristic_evaluate("redis-locks")
        assert result.is_safe is True

    def test_heuristic_evaluate_typosquat_package(self, pkg_mgr):
        """测试启发式评估 - 钓鱼包（名字与 urllib3 相似）"""
        result = pkg_mgr._heuristic_evaluate("urlllib3")
        assert result.is_safe is False

    def test_heuristic_evaluate_short_name(self, pkg_mgr):
        """测试启发式评估 - 过短包名"""
        result = pkg_mgr._heuristic_evaluate("xyz")
        assert result.is_safe is False
        assert result.risk_level == "medium_risk"

    def test_heuristic_evaluate_normal_package(self, pkg_mgr):
        """测试启发式评估 - 正常包"""
        result = pkg_mgr._heuristic_evaluate("some-new-library")
        assert result.is_safe is True
        assert result.risk_level in ("low_risk", "safe")

    def test_dynamic_whitelist_add_and_check(self, pkg_mgr):
        """测试动态白名单添加和检查"""
        pkg_mgr._dynamic_whitelist.add("test-new-package")
        assert pkg_mgr.is_in_whitelist("test-new-package") is True

    def test_dynamic_whitelist_persistence(self, pkg_mgr):
        """测试动态白名单持久化"""
        from app.utils.dynamic_package_manager import DynamicPackageManager
        pkg_mgr._dynamic_whitelist.add("persistent-package")
        pkg_mgr._save_dynamic_whitelist()
        assert pkg_mgr.WHITELIST_FILE.exists()

        mgr2 = DynamicPackageManager()
        mgr2.WHITELIST_FILE = pkg_mgr.WHITELIST_FILE
        mgr2.EVALUATION_LOG_FILE = pkg_mgr.EVALUATION_LOG_FILE
        mgr2._load_dynamic_whitelist()
        assert mgr2.is_in_whitelist("persistent-package") is True

    def test_filter_packages(self, pkg_mgr):
        """测试包列表过滤"""
        allowed, rejected = pkg_mgr.filter_packages(
        ["redis", "requests2", "fastapi"]
        )
        assert "redis" in allowed
        assert "fastapi" in allowed
        assert "requests2" in rejected

    def test_normalize_package_name(self):
        """测试包名规范化"""
        from app.utils.dynamic_package_manager import DynamicPackageManager
        assert DynamicPackageManager._normalize_package_name("Redis") == "redis"
        assert DynamicPackageManager._normalize_package_name("psycopg2-binary") == "psycopg2-binary"
        assert DynamicPackageManager._normalize_package_name("python_jose[cryptography]") == "python-jose"


class TestServiceContainerManager:
    """服务容器管理器测试"""

    def test_service_container_configs(self):
        """测试容器配置完整性"""
        from app.utils.service_container_manager import SERVICE_CONTAINER_CONFIGS
        expected = ["redis", "postgresql", "mysql", "mongodb", "rabbitmq", "elasticsearch"]
        for svc in expected:
            assert svc in SERVICE_CONTAINER_CONFIGS
        config = SERVICE_CONTAINER_CONFIGS[svc]
        assert "image" in config
        assert "ports" in config
        assert "health_cmd" in config
        assert "startup_timeout" in config

    def test_detect_project_services_from_requirements(self):
        """测试从 requirements.txt 检测服务"""
        from app.utils.service_container_manager import detect_project_services
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "requirements.txt").write_text("redis\npsycopg2-binary\nflask\n")
        services = detect_project_services(temp_dir)
        assert "redis" in services
        assert "postgresql" in services
        shutil.rmtree(temp_dir)

    def test_detect_project_services_from_env(self):
        """测试从 .env.example 检测服务"""
        from app.utils.service_container_manager import detect_project_services
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / ".env.example").write_text("REDIS_URL=redis://localhost\nDATABASE_URL=postgresql://localhost\n")
        services = detect_project_services(temp_dir)
        assert "redis" in services
        assert "postgresql" in services
        shutil.rmtree(temp_dir)

    def test_detect_project_services_from_docker_compose(self):
        """测试从 docker-compose.yml 检测服务"""
        from app.utils.service_container_manager import detect_project_services
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "docker-compose.yml").write_text("services:\n redis:\n image: redis:7\n")
        services = detect_project_services(temp_dir)
        assert "redis" in services
        shutil.rmtree(temp_dir)

    def test_detect_no_services(self):
        """测试无服务依赖的项目"""
        from app.utils.service_container_manager import detect_project_services
        temp_dir = Path(tempfile.mkdtemp())
        services = detect_project_services(temp_dir)
        assert services == []
        shutil.rmtree(temp_dir)

    def test_container_manager_init(self):
        """测试容器管理器初始化"""
        from app.utils.service_container_manager import ServiceContainerManager
        mgr = ServiceContainerManager()
        assert len(mgr.get_running_services()) == 0


class TestDependencyGraphServiceRelations:
    """依赖图服务关系测试"""

    def test_service_depends_on_env_and_service_config(self):
        """测试 service 类型依赖 env 和 service_config"""
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        assert "env" in dg.DEPENDENCY_RULES["service"]
        assert "service_config" in dg.DEPENDENCY_RULES["service"]

    def test_service_config_depends_on_env(self):
        """测试 service_config 依赖 env"""
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        assert "env" in dg.DEPENDENCY_RULES["service_config"]

    def test_docker_compose_depends_on_env_and_config(self):
        """测试 docker_compose 依赖 env 和 config"""
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        assert "env" in dg.DEPENDENCY_RULES["docker_compose"]
        assert "config" in dg.DEPENDENCY_RULES["docker_compose"]

    def test_docker_compose_path_type(self):
        """测试 docker-compose.yml 被识别为 docker_compose 类型"""
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        matched_type = None
        for pattern, type_name in dg.PATH_TYPE_RULES:
            if pattern == "docker-compose.yml":
                matched_type = type_name
                break
        assert matched_type == "docker_compose"

    def test_service_config_path_rules(self):
        """测试 service_config 路径规则"""
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        found = False
        for pattern, type_name in dg.PATH_TYPE_RULES:
            if type_name == "service_config":
                found = True
                break
        assert found is True