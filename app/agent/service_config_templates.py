"""
ServiceConfigTemplates - 第三方服务标准配置模板库

v4.8.0 新增：
- 6 种常见基础设施服务的标准配置模板
- 每种服务包含：Python 包、env 变量、docker-compose 服务定义、连接代码模板
- 用于架构师生成和一致性验证
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ServiceTemplate:
    """单个服务的配置模板"""
    name: str
    category: str  # 'cache', 'database', 'queue', 'search', 'storage'
    python_packages: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    docker_service: Dict[str, Any] = field(default_factory=dict)
    connection_code: str = ""
    health_check_command: str = ""
    default_port: int = 0
    docker_image: str = ""


SERVICE_TEMPLATES: Dict[str, ServiceTemplate] = {
    "redis": ServiceTemplate(
        name="Redis",
        category="cache",
        python_packages=["redis"],
        env_vars={
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "",
            "REDIS_URL": "redis://localhost:6379/0",
        },
        docker_service={
            "redis": {
                "image": "redis:7-alpine",
                "ports": ["6379:6379"],
                "command": "redis-server --appendonly yes",
                "volumes": ["redis_data:/data"],
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 5,
                },
            },
        },
        connection_code="""import redis
from urllib.parse import urlparse

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

def get_redis() -> redis.Redis:
    return redis_client""",
        health_check_command="redis-cli ping",
        default_port=6379,
        docker_image="redis:7-alpine",
    ),
    "postgresql": ServiceTemplate(
        name="PostgreSQL",
        category="database",
        python_packages=["psycopg2-binary", "sqlalchemy[asyncio]", "aiosqlite"],
        env_vars={
            "DATABASE_URL": "postgresql+asyncpg://appuser:apppass@localhost:5432/appdb",
            "DATABASE_HOST": "localhost",
            "DATABASE_PORT": "5432",
            "DATABASE_NAME": "appdb",
            "DATABASE_USER": "appuser",
            "DATABASE_PASSWORD": "apppass",
        },
        docker_service={
            "postgres": {
                "image": "postgres:16-alpine",
                "ports": ["5432:5432"],
                "environment": {
                    "POSTGRES_DB": "appdb",
                    "POSTGRES_USER": "appuser",
                    "POSTGRES_PASSWORD": "apppass",
                },
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U appuser -d appdb"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 5,
                },
            },
        },
        connection_code="""from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://appuser:apppass@localhost:5432/appdb")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session""",
        health_check_command="pg_isready -U appuser",
        default_port=5432,
        docker_image="postgres:16-alpine",
    ),
    "mysql": ServiceTemplate(
        name="MySQL",
        category="database",
        python_packages=["pymysql", "sqlalchemy", "cryptography"],
        env_vars={
            "DATABASE_URL": "mysql+pymysql://appuser:apppass@localhost:3306/appdb",
            "MYSQL_HOST": "localhost",
            "MYSQL_PORT": "3306",
            "MYSQL_DATABASE": "appdb",
            "MYSQL_USER": "appuser",
            "MYSQL_PASSWORD": "apppass",
        },
        docker_service={
            "mysql": {
                "image": "mysql:8.0",
                "ports": ["3306:3306"],
                "environment": {
                    "MYSQL_DATABASE": "appdb",
                    "MYSQL_USER": "appuser",
                    "MYSQL_PASSWORD": "apppass",
                    "MYSQL_ROOT_PASSWORD": "rootpass",
                },
                "volumes": ["mysql_data:/var/lib/mysql"],
                "healthcheck": {
                    "test": ["CMD", "mysqladmin", "ping", "-h", "localhost"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 5,
                },
            },
        },
        connection_code="""from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://appuser:apppass@localhost:3306/appdb")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()""",
        health_check_command="mysqladmin ping -h localhost",
        default_port=3306,
        docker_image="mysql:8.0",
    ),
    "mongodb": ServiceTemplate(
        name="MongoDB",
        category="database",
        python_packages=["pymongo"],
        env_vars={
            "MONGODB_URL": "mongodb://localhost:27017",
            "MONGODB_HOST": "localhost",
            "MONGODB_PORT": "27017",
            "MONGODB_DATABASE": "appdb",
        },
        docker_service={
            "mongodb": {
                "image": "mongo:7",
                "ports": ["27017:27017"],
                "environment": {
                    "MONGO_INITDB_DATABASE": "appdb",
                },
                "volumes": ["mongo_data:/data/db"],
                "healthcheck": {
                    "test": ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 5,
                },
            },
        },
        connection_code="""from pymongo import MongoClient

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")

mongo_client = MongoClient(MONGODB_URL)
mongo_db = mongo_client[os.getenv("MONGODB_DATABASE", "appdb")]

def get_mongo_db():
    return mongo_db""",
        health_check_command="mongosh --eval 'db.adminCommand(\"ping\")'",
        default_port=27017,
        docker_image="mongo:7",
    ),
    "rabbitmq": ServiceTemplate(
        name="RabbitMQ",
        category="queue",
        python_packages=["aio-pika"],
        env_vars={
            "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
            "RABBITMQ_HOST": "localhost",
            "RABBITMQ_PORT": "5672",
            "RABBITMQ_USER": "guest",
            "RABBITMQ_PASSWORD": "guest",
            "RABBITMQ_VHOST": "/",
        },
        docker_service={
            "rabbitmq": {
                "image": "rabbitmq:3-management-alpine",
                "ports": ["5672:5672", "15672:15672"],
                "environment": {
                    "RABBITMQ_DEFAULT_USER": "guest",
                    "RABBITMQ_DEFAULT_PASS": "guest",
                },
                "volumes": ["rabbitmq_data:/var/lib/rabbitmq"],
                "healthcheck": {
                    "test": ["CMD", "rabbitmq-diagnostics", "check_running"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 5,
                },
            },
        },
        connection_code="""import aio_pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

async def get_rabbitmq_connection():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    return connection""",
        health_check_command="rabbitmq-diagnostics check_running",
        default_port=5672,
        docker_image="rabbitmq:3-management-alpine",
    ),
    "elasticsearch": ServiceTemplate(
        name="Elasticsearch",
        category="search",
        python_packages=["elasticsearch"],
        env_vars={
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_HOST": "localhost",
            "ELASTICSEARCH_PORT": "9200",
        },
        docker_service={
            "elasticsearch": {
                "image": "elasticsearch:8.12.0",
                "ports": ["9200:9200"],
                "environment": {
                    "discovery.type": "single-node",
                    "xpack.security.enabled": "false",
                    "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
                },
                "volumes": ["es_data:/usr/share/elasticsearch/data"],
                "healthcheck": {
                    "test": ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 5,
                },
            },
        },
        connection_code="""from elasticsearch import AsyncElasticsearch

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

es_client = AsyncElasticsearch(ES_URL)

async def get_es() -> AsyncElasticsearch:
    return es_client""",
        health_check_command="curl -f http://localhost:9200/_cluster/health",
        default_port=9200,
        docker_image="elasticsearch:8.12.0",
    ),
}


def get_service_template(service_name: str) -> Optional[ServiceTemplate]:
    """获取服务配置模板"""
    return SERVICE_TEMPLATES.get(service_name.lower())


def get_all_service_names() -> List[str]:
    """获取所有支持的服务名称"""
    return list(SERVICE_TEMPLATES.keys())


def detect_services_from_requirements(requirement: str) -> List[str]:
    """
    从需求文本中检测需要哪些第三方服务

    Args:
        requirement: 用户需求描述

    Returns:
        匹配的服务名称列表
    """
    DETECTION_KEYWORDS: Dict[str, List[str]] = {
        "redis": ["redis", "缓存", "cache", "session store"],
        "postgresql": ["postgresql", "postgres", "pg", "关系数据库"],
        "mysql": ["mysql", "关系型数据库"],
        "mongodb": ["mongodb", "mongo", "文档数据库", "nosql"],
        "rabbitmq": ["rabbitmq", "消息队列", "queue", "mq", "amqp"],
        "elasticsearch": ["elasticsearch", "es", "搜索", "search engine", "全文检索"],
    }

    requirement_lower = requirement.lower()
    detected = []

    for service, keywords in DETECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in requirement_lower:
                if service not in detected:
                    detected.append(service)
                break

    return detected


def generate_env_example(services: List[str], custom_vars: Dict[str, str] = None) -> str:
    """
    生成 .env.example 文件内容

    Args:
        services: 需要的服务列表
        custom_vars: 自定义环境变量

    Returns:
        .env.example 文件内容
    """
    lines = [
        "# Application",
        "APP_NAME=myapp",
        "APP_ENV=development",
        "APP_PORT=8000",
        "",
        "# Security",
        "SECRET_KEY=change-me-in-production",
        "",
    ]

    for service_name in services:
        template = get_service_template(service_name)
        if template:
            lines.append(f"# {template.name}")
            for var, default in template.env_vars.items():
                lines.append(f"{var}={default}")
            lines.append("")

    if custom_vars:
        lines.append("# Custom")
        for var, val in custom_vars.items():
            lines.append(f"{var}={val}")
        lines.append("")

    return "\n".join(lines)


def generate_docker_compose(services: List[str], app_name: str = "myapp") -> str:
    """
    生成 docker-compose.yml 文件内容

    Args:
        services: 需要的服务列表
        app_name: 应用名称

    Returns:
        docker-compose.yml 文件内容
    """
    service_defs = {}
    volume_defs = {}

    for service_name in services:
        template = get_service_template(service_name)
        if template:
            for svc_name, svc_config in template.docker_service.items():
                service_defs[svc_name] = svc_config
                if "volumes" in svc_config:
                    for vol in svc_config["volumes"]:
                        vol_name = vol.split(":")[0]
                        volume_defs[vol_name] = {}

    app_service = {
        "build": {"context": ".", "dockerfile": "Dockerfile"},
        "ports": ["8000:8000"],
        "environment": [],
        "depends_on": [],
        "volumes": [".:/app"],
    }

    for service_name in services:
        template = get_service_template(service_name)
        if template:
            for svc_name in template.docker_service:
                app_service["depends_on"].append({
                    svc_name: {"condition": "service_healthy"}
                })

    env_content = generate_env_example(services)
    for line in env_content.split("\n"):
        line = line.strip()
        if "=" in line and not line.startswith("#") and line:
            key, val = line.split("=", 1)
            app_service["environment"].append(f"{key.strip()}={val.strip()}")

    service_defs["app"] = app_service

    lines = ["version: '3.8'", "", "services:"]
    for svc_name, svc_config in service_defs.items():
        lines.append(f"  {svc_name}:")
        for key, val in svc_config.items():
            if isinstance(val, dict):
                lines.append(f"    {key}:")
                for k2, v2 in val.items():
                    lines.append(f"      {k2}: {v2}")
            elif isinstance(val, list):
                lines.append(f"    {key}:")
                for item in val:
                    if isinstance(item, dict):
                        lines.append(f"      -")
                        for k3, v3 in item.items():
                            lines.append(f"        {k3}: {v3}")
                    else:
                        lines.append(f"      - {item}")
            elif isinstance(val, str):
                lines.append(f"    {key}: {val}")
        lines.append("")

    if volume_defs:
        lines.append("volumes:")
        for vol_name in volume_defs:
            lines.append(f"  {vol_name}:")
        lines.append("")

    return "\n".join(lines)


def get_python_packages_for_services(services: List[str]) -> List[str]:
    """获取指定服务所需的所有 Python 包"""
    packages = ["fastapi", "uvicorn", "pydantic", "pydantic-settings"]
    for service_name in services:
        template = get_service_template(service_name)
        if template:
            packages.extend(template.python_packages)
    return packages


def get_connection_snippets(services: List[str]) -> Dict[str, str]:
    """获取指定服务的连接代码片段"""
    snippets = {}
    for service_name in services:
        template = get_service_template(service_name)
        if template:
            snippets[service_name] = template.connection_code
    return snippets