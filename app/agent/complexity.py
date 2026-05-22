"""
项目复杂度分析器

负责分析用户需求的复杂度，评估项目规模、技术栈和风险因素。
"""

import re
import json
import logging
from enum import Enum
from typing import Optional, List, Dict
from dataclasses import dataclass

from app.utils import call_llm

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
    key_technologies: List[str] = None
    risk_factors: List[str] = None
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
    FRONTEND_KEYWORDS = ['前端', '页面', 'ui', '界面', 'vue', 'react', 'angular', 'html', 'css', '样式', '组件', '组件库']
    BACKEND_KEYWORDS = ['后端', 'api', '接口', '服务器', 'server', 'fastapi', 'django', 'flask', 'spring', 'express']
    DATABASE_KEYWORDS = ['数据库', 'database', 'mysql', 'postgres', 'sqlite', 'mongo', 'redis', '存储', '数据表']
    AUTH_KEYWORDS = ['登陆', '注册', '认证', 'auth', 'jwt', 'oauth', '权限', '角色', '用户管理']
    COMPLEX_KEYWORDS = ['微服务', '分布式', '缓存', '消息队列', 'kafka', 'rabbitmq', 'docker', 'k8s', '部署']

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
    async def analyze_with_llm(cls, requirement: str) -> Optional[ComplexityAnalysis]:
        """
        使用 LLM 辅助分析复杂度（适用于中大型需求）

        先用关键词快速扫描，再用 LLM 校准估算。
        LLM 只负责校准文件数和技术栈，避免额外 API 调用开销。
        """
        # 先用关键词快速分析
        keyword_result = cls.analyze(requirement)

        # 小项目不需要 LLM 校准
        if keyword_result.level in (ProjectComplexity.SIMPLE, ProjectComplexity.SMALL):
            return keyword_result

        # 中大型项目使用 LLM 校准
        try:
            system_prompt = (
                "你是一个资深软件架构师。根据用户需求评估项目复杂度。"
                "只返回 JSON，格式：{\"estimated_files\": 数字, \"tech_stack\": [\"技术1\", \"技术2\"], \"risk_factors\": [\"风险1\"]}"
                "estimated_files 范围：5-100。tech_stack 只列具体框架名。"
            )
            user_prompt = f"用户需求：\n{requirement}\n\n关键词初估：约 {keyword_result.estimated_files} 个文件，技术栈：{keyword_result.key_technologies}。请校准估算。"

            response = await call_llm(
                model="Qwen/Qwen3.5-4B",
                prompt=user_prompt,
                max_tokens=512,
                temperature=0.3,
                system_prompt=system_prompt
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 解析 JSON
            json_match = content.find('{')
            if json_match >= 0:
                llm_result = json.loads(content[json_match:])
                llm_files = llm_result.get("estimated_files", keyword_result.estimated_files)
                llm_techs = llm_result.get("tech_stack", keyword_result.key_technologies)
                llm_risks = llm_result.get("risk_factors", keyword_result.risk_factors)

                # 确定复杂度等级
                if llm_files <= 3:
                    level = ProjectComplexity.SIMPLE
                elif llm_files <= 8:
                    level = ProjectComplexity.SMALL
                elif llm_files <= 20:
                    level = ProjectComplexity.MEDIUM
                elif llm_files <= 50:
                    level = ProjectComplexity.LARGE
                else:
                    level = ProjectComplexity.ENTERPRISE

                estimated_tokens = cls._estimate_tokens(
                    level, llm_files,
                    keyword_result.has_frontend, keyword_result.has_backend,
                    keyword_result.has_database, keyword_result.has_auth
                )
                estimated_cost_usd = (estimated_tokens / 1000) * 0.001

                return ComplexityAnalysis(
                    level=level,
                    estimated_files=llm_files,
                    has_frontend=keyword_result.has_frontend,
                    has_backend=keyword_result.has_backend,
                    has_database=keyword_result.has_database,
                    key_technologies=llm_techs if llm_techs else keyword_result.key_technologies,
                    risk_factors=llm_risks if llm_risks else keyword_result.risk_factors,
                    estimated_tokens=estimated_tokens,
                    estimated_cost_usd=estimated_cost_usd
                )
        except Exception as e:
            logger.warning(f"LLM 复杂度校准失败，降级到关键词分析: {e}")

        # 降级到关键词分析
        return keyword_result
