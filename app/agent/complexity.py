"""
项目复杂度分析器

负责分析用户需求的复杂度，评估项目规模、技术栈和风险因素。
"""

import logging
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ProjectComplexity(str, Enum):
    """项目复杂度等级"""
    SIMPLE = "simple"          # 单文件脚本，<50行
    SMALL = "small"           # 2-5个文件，简单逻辑
    MEDIUM = "medium"         # 5-15个文件，有前后端
    LARGE = "large"           # 15-50个文件，完整全栈
    ENTERPRISE = "enterprise" # 50+ 文件，企业级


@dataclass
class ComplexityAnalysis:
    """复杂度分析结果"""
    level: ProjectComplexity
    estimated_files: int
    has_frontend: bool
    has_backend: bool
    has_database: bool
    has_auth: bool = False
    key_technologies: Optional[List[str]] = None
    risk_factors: Optional[List[str]] = None
    estimated_tokens: int = 0  # 预估 Token 消耗
    estimated_cost_usd: float = 0.0  # 预估成本（美元）

    def __post_init__(self):
        if self.key_technologies is None:
            self.key_technologies = []
        if self.risk_factors is None:
            self.risk_factors = []


class ComplexityAnalyzer:
    """项目复杂度分析器"""

    # 关键词映射
    FRONTEND_KEYWORDS = ['前端', '页面', 'ui', '界面', 'vue', 'react', 'angular', 'html', 'css', '样式', '组件', '组件库', '小程序', 'h5', '移动端']
    BACKEND_KEYWORDS = ['后端', 'api', '接口', '服务器', 'server', 'fastapi', 'django', 'flask', 'spring', 'express', 'graphql', 'grpc', 'websocket', 'rpc']
    DATABASE_KEYWORDS = ['数据库', 'database', 'mysql', 'postgres', 'sqlite', 'mongo', 'redis', '存储', '数据表', 'elasticsearch', 'cassandra', 'clickhouse', 'tidb']
    AUTH_KEYWORDS = ['登录', '注册', '认证', 'auth', 'jwt', 'oauth', '权限', '角色', '用户管理', 'rbac', '访问控制', '单点登录', 'sso']
    COMPLEX_KEYWORDS = ['微服务', '分布式', '缓存', '消息队列', 'kafka', 'rabbitmq', 'docker', 'k8s', '部署',
                        '支付', '电商', '集成', '第三方', '网关', '调度', '任务队列', '定时任务', 'cron',
                        '通知', '推送', '短信', '邮件', '上传', '下载', '文件系统', 'cdn', 'oss',
                        '监控', '日志', '链路追踪', '熔断', '限流', '负载均衡', '集群', '高可用']

    @classmethod
    def analyze(cls, requirement: str) -> ComplexityAnalysis:
        """分析需求，返回复杂度评估"""
        req_lower = requirement.lower()

        has_frontend = any(kw in req_lower for kw in cls.FRONTEND_KEYWORDS)
        has_backend = any(kw in req_lower for kw in cls.BACKEND_KEYWORDS)
        has_database = any(kw in req_lower for kw in cls.DATABASE_KEYWORDS)
        has_auth = any(kw in req_lower for kw in cls.AUTH_KEYWORDS)
        has_complex = any(kw in req_lower for kw in cls.COMPLEX_KEYWORDS)

        # 估算文件数
        estimated_files = 3  # 基础：main.py + requirements.txt + README.md
        if has_frontend: estimated_files += 5
        if has_backend: estimated_files += 3
        if has_database: estimated_files += 2
        if has_auth: estimated_files += 3
        if has_complex: estimated_files += 10

        # 识别技术栈
        techs = []
        if 'vue' in req_lower: techs.append('Vue')
        if 'react' in req_lower: techs.append('React')
        if 'fastapi' in req_lower: techs.append('FastAPI')
        if 'django' in req_lower: techs.append('Django')
        if 'flask' in req_lower: techs.append('Flask')
        if 'mysql' in req_lower: techs.append('MySQL')
        if 'postgres' in req_lower or 'postgresql' in req_lower: techs.append('PostgreSQL')
        if 'redis' in req_lower: techs.append('Redis')
        if not techs:
            techs = ['Python']

        # 风险因素
        risks = []
        if has_auth: risks.append('需要用户认证系统')
        if has_database: risks.append('需要数据库设计和迁移')
        if has_complex: risks.append('架构复杂度高')
        if estimated_files > 20: risks.append('文件数量多，上下文管理困难')

        # 确定复杂度等级
        if estimated_files <= 3 and not has_complex:
            level = ProjectComplexity.SIMPLE
        elif estimated_files <= 8:
            level = ProjectComplexity.SMALL
        elif estimated_files <= 20:
            level = ProjectComplexity.MEDIUM
        elif estimated_files <= 50:
            level = ProjectComplexity.LARGE
        else:
            level = ProjectComplexity.ENTERPRISE

        # 估算 Token 消耗
        estimated_tokens = cls._estimate_tokens(level, estimated_files, has_frontend, has_backend, has_database, has_auth)

        # 估算成本（基于平均模型价格：约 $0.001/1K tokens）
        estimated_cost_usd = (estimated_tokens / 1000) * 0.001

        return ComplexityAnalysis(
            level=level,
            estimated_files=estimated_files,
            has_frontend=has_frontend,
            has_backend=has_backend,
            has_database=has_database,
            has_auth=has_auth,
            key_technologies=techs,
            risk_factors=risks,
            estimated_tokens=estimated_tokens,
            estimated_cost_usd=estimated_cost_usd
        )

    @classmethod
    def _estimate_tokens(cls, level: ProjectComplexity, files: int, has_fe: bool, has_be: bool, has_db: bool, has_auth: bool) -> int:
        """估算 Token 消耗

        基于历史数据估算：
        - 架构设计：~2K tokens
        - 每个文件生成：~3K tokens（平均）
        - 审查：~1K tokens/文件
        - API 规范生成：~2K tokens
        - DB Schema 生成：~1K tokens
        """
        base_tokens = 2000  # 架构设计

        # 文件生成
        tokens_per_file = 3000
        file_tokens = files * tokens_per_file

        # 审查
        review_tokens = files * 1000

        # API 规范
        api_tokens = 2000 if has_be else 0

        # DB Schema
        db_tokens = 1000 if has_db else 0

        # 认证系统
        auth_tokens = 3000 if has_auth else 0

        total = base_tokens + file_tokens + review_tokens + api_tokens + db_tokens + auth_tokens

        # 复杂度系数
        level_multiplier = {
            ProjectComplexity.SIMPLE: 1.0,
            ProjectComplexity.SMALL: 1.2,
            ProjectComplexity.MEDIUM: 1.5,
            ProjectComplexity.LARGE: 1.8,
            ProjectComplexity.ENTERPRISE: 2.0
        }
        return int(total * level_multiplier.get(level, 1.0))

    @classmethod
    async def analyze_with_llm(cls, requirement: str, api_key_token: Optional[str] = None) -> Optional[ComplexityAnalysis]:
        """向后兼容：直接调用关键词分析（不再使用 LLM 校准）"""
        return cls.analyze(requirement)
