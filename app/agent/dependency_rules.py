"""
依赖图规则定义

文件类型到依赖类型的映射（DEPENDENCY_RULES）和
文件路径到类型的映射（PATH_TYPE_RULES）。
"""

from typing import Dict, List, Tuple

# 文件类型到依赖类型的映射
DEPENDENCY_RULES: Dict[str, List[str]] = {
    # 基础设施层 - 最先生成
    "config": [],
    "env": [],
    "dockerfile": [],
    "service_config": ["env"],
    "docker_compose": ["env", "config"],

    # 数据库相关
    "database": ["config"],
    "model": ["database", "config"],
    "repository": ["database", "model", "schema", "types"],
    "migration": ["model", "database"],

    # 类型和工具
    "types": ["config"],
    "utils": ["config", "env"],
    "constants": ["config"],

    # 业务层
    "service": ["model", "repository", "types", "utils", "service_config", "env"],
    "schema": ["model", "types"],

    # API 层
    "api": ["service", "schema", "types"],
    "view": ["service", "schema", "types"],
    "controller": ["service", "schema", "types"],
    "router": ["service", "schema", "types"],
    "entry": ["api", "router", "controller", "service", "repository", "schema", "types", "model", "database"],

    # 前端
    "frontend_types": ["api"],
    "frontend_api": ["frontend_types"],
    "frontend_component": ["frontend_api", "frontend_types"],
    "frontend_page": ["frontend_component"],
    "frontend_style": [],

    # 测试
    "test": ["entry", "api", "router", "controller", "service", "repository", "schema", "types", "model", "database"],

    # 文档
    "readme": [],
    "docs": [],
}

# 文件路径到类型的映射规则
PATH_TYPE_RULES: List[Tuple[str, str]] = [
    # 配置
    ("requirements.txt", "config"),
    ("package.json", "config"),
    (".env", "env"),
    (".env.example", "env"),
    (".env.local", "env"),
    ("Dockerfile", "dockerfile"),
    ("docker-compose.yml", "docker_compose"),
    ("docker-compose.yaml", "docker_compose"),
    ("pyproject.toml", "config"),
    ("setup.py", "config"),
    ("Makefile", "config"),
    # 元文件/工具配置：这些名字与包名无法区分，但都是真实项目文件。
    # 缺少规则会让 file_type 推断返回 unknown 并中断生成。
    (".gitignore", "config"),
    (".gitattributes", "config"),
    (".dockerignore", "config"),
    (".npmignore", "config"),
    (".eslintignore", "config"),
    (".prettierignore", "config"),
    (".helmignore", "config"),
    (".editorconfig", "config"),
    (".babelrc", "config"),
    (".eslintrc", "config"),
    (".prettierrc", "config"),
    (".stylelintrc", "config"),
    (".npmrc", "config"),
    (".yarnrc", "config"),
    (".nvmrc", "config"),
    (".flake8", "config"),
    (".pylintrc", "config"),
    (".sqlfluff", "config"),

    # 服务连接配置
    ("redis_config.py", "service_config"),
    ("redis_connection.py", "service_config"),
    ("database_config.py", "service_config"),
    ("db_connection.py", "service_config"),
    ("mongodb_config.py", "service_config"),
    ("rabbitmq_config.py", "service_config"),
    ("elasticsearch_config.py", "service_config"),
    ("connections.py", "service_config"),
    ("connections/", "service_config"),
    ("connectors/", "service_config"),

    # Python 配置
    ("config.py", "config"),
    ("settings.py", "config"),
    ("config/", "config"),
    ("settings/", "config"),

    # 数据库
    ("database.py", "database"),
    ("database/", "database"),
    ("db.py", "database"),

    # 模型
    ("models.py", "model"),
    ("models/", "model"),
    ("model/", "model"),
    ("entities/", "model"),
    ("entity/", "model"),

    # Repository
    ("crud.py", "repository"),
    ("crud/", "repository"),
    ("repositories/", "repository"),
    ("repository/", "repository"),
    ("repos/", "repository"),
    ("dao/", "repository"),

    # 类型
    ("types.py", "types"),
    ("types/", "types"),
    ("schemas.py", "types"),
    ("schemas/", "schema"),
    ("dto/", "schema"),

    # 工具
    ("utils/", "utils"),
    ("utils.py", "utils"),
    ("helpers/", "utils"),
    ("helpers.py", "utils"),
    ("constants.py", "constants"),
    ("constants/", "constants"),

    # 服务
    ("services/", "service"),
    ("service/", "service"),
    ("business/", "service"),

    # API/View/Controller
    ("api/", "api"),
    ("apis/", "api"),
    ("views/", "view"),
    ("view/", "view"),
    ("controllers/", "controller"),
    ("controller/", "controller"),
    ("routers/", "router"),
    ("router/", "router"),
    ("routes/", "router"),

    # 前端
    ("src/types/", "frontend_types"),
    ("src/api/", "frontend_api"),
    ("src/apis/", "frontend_api"),
    ("src/components/", "frontend_component"),
    ("src/component/", "frontend_component"),
    ("src/pages/", "frontend_page"),
    ("src/page/", "frontend_page"),
    ("src/views/", "frontend_page"),
    ("src/styles/", "frontend_style"),
    ("src/assets/", "frontend_style"),

    # 迁移
    ("migrations/", "migration"),
    ("alembic/", "migration"),

    # 测试
    ("tests/", "test"),
    ("test/", "test"),
    ("test_", "test"),
    ("_test.py", "test"),
    ("__tests__/", "test"),

    # 文档
    ("README.md", "readme"),
    ("docs/", "docs"),
]

# 扩展名到文件类型的映射（兜底）
EXTENSION_TYPE_MAP = {
    '.js': 'frontend_component',
    '.ts': 'frontend_types',
    '.vue': 'frontend_component',
    '.jsx': 'frontend_component',
    '.tsx': 'frontend_component',
    '.html': 'frontend_page',
    '.css': 'frontend_style',
    '.scss': 'frontend_style',
    '.md': 'docs',
    '.rst': 'docs',
    '.adoc': 'docs',
    '.json': 'config',
    '.yaml': 'config',
    '.yml': 'config',
    '.toml': 'config',
    '.sql': 'migration',
    '.env': 'env',
    '.sh': 'config',
    '.dockerfile': 'dockerfile',
    '.txt': 'config',
    '.conf': 'config',
    '.cfg': 'config',
    '.ini': 'config',
    '.xml': 'config',
    '.in': 'config',
    '.tmpl': 'config',
    '.tpl': 'config',
    '.bat': 'config',
    '.cmd': 'config',
    '.ps1': 'config',
    '.properties': 'config',
    '.gradle': 'config',
    '.mk': 'config',
    '.cmake': 'config',
    '.lock': 'config',
    '.po': 'config',
    '.graphql': 'schema',
    '.gql': 'schema',
    '.proto': 'schema',
    '.tf': 'config',
    '.tfvars': 'config',
    '.less': 'frontend_style',
    '.sass': 'frontend_style',
    '.styl': 'frontend_style',
}
