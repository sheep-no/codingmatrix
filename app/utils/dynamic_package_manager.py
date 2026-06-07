"""
DynamicPackageManager - 动态包管理器

v4.8.0 新增：
- 静态白名单 + 动态扩展
- 不在白名单中的包 → AI 评估安全性 → 通过则安装并加入白名单
- 白名单持久化到 JSON 文件
- 安全评估维度：恶意包检测、依赖冲突、许可证风险
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

STATIC_WHITELIST: Set[str] = {
    # FastAPI 生态
    'fastapi', 'starlette', 'uvicorn', 'gunicorn', 'hypercorn',
    # 数据库
    'sqlalchemy', 'alembic', 'aiosqlite', 'aiomysql', 'pymysql',
    'psycopg2', 'psycopg2-binary', 'pymongo', 'redis', 'asyncpg',
    'hiredis', 'cachetools',
    # Pydantic
    'pydantic', 'pydantic-settings',
    # 认证安全
    'python-jose', 'cryptography', 'passlib', 'bcrypt',
    # HTTP
    'httpx', 'aiohttp', 'requests', 'urllib3', 'aiofiles', 'Pillow',
    'python-multipart',
    # AI
    'tiktoken', 'transformers', 'tokenizers', 'openai',
    # HTML
    'beautifulsoup4', 'bs4', 'lxml', 'html5lib',
    # 日志监控
    'structlog', 'python-json-logger', 'psutil', 'slowapi',
    # 任务调度
    'apscheduler', 'celery',
    # WebSocket
    'websockets',
    # 工具
    'python-dotenv', 'anyio', 'tenacity', 'click', 'typer', 'rich', 'tqdm',
    # 数据
    'pandas', 'numpy', 'scipy', 'matplotlib', 'seaborn', 'plotly',
    # Office
    'python-pptx', 'python-docx', 'openpyxl', 'xlrd', 'xlwt', 'xlsxwriter',
    # 格式
    'pyyaml', 'toml', 'tomli', 'json5', 'orjson', 'ujson',
    # 加密
    'pycryptodome', 'pyopenssl',
    # 测试
    'pytest', 'pytest-asyncio', 'pytest-cov', 'pytest-mock', 'pytest-xdist',
    'allure-pytest',
    # 网络
    'flask', 'django', 'bottle', 'falcon', 'grpcio', 'grpcio-tools',
    # 日期
    'python-dateutil', 'pytz',
    # 消息队列
    'aio-pika', 'pika', 'kombu',
    # 搜索
    'elasticsearch',
    # ORM 扩展
    'sqlalchemy-utils',
    # 其他
    'email-validator', 'itsdangerous', 'jinja2', 'markupsafe',
    'sqlparse', 'typing-extensions', 'greenlet',
    'fastapi-utils', 'backoff',
    # ORM 异步驱动
    'asyncpg', 'aiomysql',
    # 环境配置
    'dynaconf',
    # 序列化
    'marshmallow',
    # GraphQL
    'graphene', 'strawberry',
}

BLOCKED_PACKAGES: Set[str] = {
    # 已知恶意/高风险包
    'python3-daemon', 'pypi-publisher',
    'setup-tools', 'requests2',
    'pip-download', 'python-stdlib',
    'xkcd-password-generator',
    # 钓鱼包（名字与知名包相似）
    'urlllib', 'urlllib3', 'urlllib2',
    'requestss', 'requestsss',
    'urllib3-fake', 'requests-fake',
}

@dataclass
class PackageEvaluation:
    """包安全评估结果"""
    package_name: str
    is_safe: bool
    risk_level: str  # 'safe', 'low_risk', 'medium_risk', 'high_risk', 'blocked'
    reason: str
    category: str  # 'web', 'database', 'ai', 'security', 'utility', 'unknown'
    added_to_whitelist: bool = False


class DynamicPackageManager:
    """
    动态包管理器

    流程：
    1. 检查包是否在静态白名单 → 直接允许
    2. 检查包是否在黑名单 → 直接拒绝
    3. 不在两个名单中 → AI 评估安全性
    4. 评估通过 → 安装 + 加入动态白名单 + 持久化
    5. 评估不通过 → 拒绝 + 记录原因
    """

    WHITELIST_FILE = Path("configs/dynamic_whitelist.json")
    EVALUATION_LOG_FILE = Path("configs/package_evaluations.json")

    def __init__(self, llm_eval_fn=None):
        self.llm_eval_fn = llm_eval_fn
        self._dynamic_whitelist: Set[str] = set()
        self._evaluations: Dict[str, PackageEvaluation] = {}
        self._load_dynamic_whitelist()

    def _load_dynamic_whitelist(self):
        """加载持久化的动态白名单"""
        if self.WHITELIST_FILE.exists():
            try:
                data = json.loads(self.WHITELIST_FILE.read_text())
                self._dynamic_whitelist = set(data.get("packages", []))
                logger.info(f"动态白名单加载: {len(self._dynamic_whitelist)} 个包")
            except Exception as e:
                logger.warning(f"动态白名单加载失败: {e}")

        if self.EVALUATION_LOG_FILE.exists():
            try:
                data = json.loads(self.EVALUATION_LOG_FILE.read_text())
                for pkg_name, eval_data in data.items():
                    self._evaluations[pkg_name] = PackageEvaluation(
                        package_name=eval_data["package_name"],
                        is_safe=eval_data["is_safe"],
                        risk_level=eval_data["risk_level"],
                        reason=eval_data["reason"],
                        category=eval_data["category"],
                    )
            except Exception as e:
                logger.warning(f"评估日志加载失败: {e}")

    def _save_dynamic_whitelist(self):
        """持久化动态白名单"""
        from datetime import datetime
        data = {
            "packages": sorted(self._dynamic_whitelist),
            "last_updated": datetime.now().isoformat(),
        }
        try:
            self.WHITELIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.WHITELIST_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"动态白名单保存失败: {e}")

    def _save_evaluation_log(self):
        """持久化评估日志"""
        data = {}
        for pkg_name, evaluation in self._evaluations.items():
            data[pkg_name] = {
                "package_name": evaluation.package_name,
                "is_safe": evaluation.is_safe,
                "risk_level": evaluation.risk_level,
                "reason": evaluation.reason,
                "category": evaluation.category,
                "added_to_whitelist": evaluation.added_to_whitelist,
            }
        try:
            self.EVALUATION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.EVALUATION_LOG_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"评估日志保存失败: {e}")

    def is_in_whitelist(self, package_name: str) -> bool:
        """检查包是否在白名单（静态+动态）"""
        normalized = self._normalize_package_name(package_name)
        return normalized in STATIC_WHITELIST or normalized in self._dynamic_whitelist

    def is_blocked(self, package_name: str) -> bool:
        """检查包是否在黑名单"""
        # 先检查原始包名（因为黑名单包含钓鱼包名如 requests2）
        if package_name.lower().strip() in BLOCKED_PACKAGES:
            return True
        
        # 再检查规范化后的包名
        normalized = self._normalize_package_name(package_name)
        return normalized in BLOCKED_PACKAGES

    def get_full_whitelist(self) -> Set[str]:
        """获取完整白名单（静态+动态）"""
        return STATIC_WHITELIST | self._dynamic_whitelist

    async def evaluate_and_install(self, package_name: str) -> PackageEvaluation:
        """
        评估并安装包

        流程：
        1. 白名单中 → 直接通过
        2. 黑名单中 → 直接拒绝
        3. 已评估过 → 使用缓存结果
        4. 新包 → AI 评估 → 通过则加入白名单

        Args:
            package_name: 包名

        Returns:
            PackageEvaluation 评估结果
        """
        normalized = self._normalize_package_name(package_name)

        if self.is_in_whitelist(normalized):
            return PackageEvaluation(
                package_name=normalized,
                is_safe=True,
                risk_level="safe",
                reason="已在白名单中",
                category="whitelist",
            )

        if self.is_blocked(normalized):
            return PackageEvaluation(
                package_name=normalized,
                is_safe=False,
                risk_level="blocked",
                reason="在黑名单中，已知恶意包",
                category="blocked",
            )

        cached = self._evaluations.get(normalized)
        if cached:
            return cached

        evaluation = await self._ai_evaluate_package(normalized)
        self._evaluations[normalized] = evaluation

        if evaluation.is_safe:
            self._dynamic_whitelist.add(normalized)
            evaluation.added_to_whitelist = True
            self._save_dynamic_whitelist()
            logger.info(f"包 {normalized} 评估通过，已加入动态白名单")

        self._save_evaluation_log()
        return evaluation

    async def _ai_evaluate_package(self, package_name: str) -> PackageEvaluation:
        """
        AI 评估包安全性

        评估维度：
        1. 意图判断：是否是合理的开发依赖？
        2. 安全风险：是否已知恶意包？
        3. 依赖冲突：是否与现有依赖冲突？
        4. 许可证：是否使用限制性许可证？

        Args:
            package_name: 包名

        Returns:
            PackageEvaluation
        """
        if not self.llm_eval_fn:
            return self._heuristic_evaluate(package_name)

        prompt = f"""请评估以下 Python 包是否可以安全安装到开发环境中：

包名：{package_name}

评估维度：
1. **意图**：这个包是否是合理的开发/项目依赖？还是可疑的/无关的包？
2. **安全**：这个包是否是已知的恶意包、钓鱼包或名字混淆包？
3. **依赖冲突**：这个包是否可能与常见开发依赖产生冲突？
4. **许可证**：这个包是否使用限制性许可证（如 AGPL）？

请返回 JSON 格式的评估结果：
```json
{
    "is_safe": true/false,
    "risk_level": "safe/low_risk/medium_risk/high_risk",
    "reason": "评估原因说明",
    "category": "web/database/ai/security/utility/messaging/search/unknown"
}
```

注意：
- 如果包名与知名包名非常相似但拼写略有不同（如 urllib vs urllib3），标记为 high_risk
- 如果包名看起来是合理的开发工具，标记为 safe 或 low_risk
- 如果不确定，标记为 medium_risk"""

        try:
            response = await self.llm_eval_fn(prompt)
            result = self._parse_evaluation_response(package_name, response)
            return result
        except Exception as e:
            logger.warning(f"AI 评估失败，回退到启发式评估: {e}")
            return self._heuristic_evaluate(package_name)

    def _heuristic_evaluate(self, package_name: str) -> PackageEvaluation:
        """启发式安全评估（无 LLM 时的回退）"""
        # 规则 1: 包名与知名包相似但不同 → 高风险
        KNOWN_PACKAGES = {
            'requests', 'urllib3', 'flask', 'django', 'pytest',
            'sqlalchemy', 'redis', 'pymongo', 'numpy', 'pandas',
            'pillow', 'beautifulsoup4', 'cryptography',
        }
        normalized = self._normalize_package_name(package_name)
        for known in KNOWN_PACKAGES:
            # 计算编辑距离，差异 ≤ 2 且长度相似 → 钓鱼包
            if normalized != known and len(normalized) >= len(known) - 1:
                if self._is_likely_typosquat(normalized, known):
                    return PackageEvaluation(
                        package_name=package_name,
                        is_safe=False,
                        risk_level="high_risk",
                        reason=f"包名与知名包 {known} 非常相似，可能是钓鱼包",
                        category="unknown",
                    )

        # 规则 2: 包名包含常见开发关键词 → 低风险
        DEV_KEYWORDS = [
            'fastapi', 'api', 'http', 'web', 'db', 'sql', 'redis',
            'mongo', 'queue', 'queue', 'async', 'io', 'test', 'util',
            'config', 'log', 'auth', 'security', 'crypto', 'ml', 'ai',
            'data', 'json', 'yaml', 'xml', 'html', 'csv', 'pdf',
            'image', 'video', 'audio', 'graph', 'geo', 'time',
            'email', 'sms', 'slack', 'discord', 'telegram',
            'aws', 'gcp', 'azure', 'docker', 'k8s',
        ]
        for keyword in DEV_KEYWORDS:
            if keyword in package_name.lower():
                return PackageEvaluation(
                    package_name=package_name,
                    is_safe=True,
                    risk_level="low_risk",
                    reason=f"包名包含开发关键词 '{keyword}'，看起来是合理的开发依赖",
                    category="utility",
                )

        # 规则 3: 包名很短且没有已知对应 → 中等风险
        if len(package_name) <= 3:
            return PackageEvaluation(
                package_name=package_name,
                is_safe=False,
                risk_level="medium_risk",
                reason="包名过短，无法确认用途",
                category="unknown",
            )

        # 规则 4: 默认 → 低风险（允许但需记录）
        return PackageEvaluation(
            package_name=package_name,
            is_safe=True,
            risk_level="low_risk",
            reason="未识别但包名格式正常，允许安装并加入观察列表",
            category="unknown",
        )

    @staticmethod
    def _is_likely_typosquat(candidate: str, known: str) -> bool:
        """判断 candidate 是否是 known 的 typosquat（钓鱼包名）

        使用简化的 Levenshtein 距离：
        - 编辑距离 ≤ 2 且长度差 ≤ 2 → 可能是钓鱼
        """
        if candidate == known:
            return False
        if abs(len(candidate) - len(known)) > 2:
            return False
        # 简化 Levenshtein 距离计算
        m, n = len(candidate), len(known)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if candidate[i - 1] == known[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n] <= 2

    def _parse_evaluation_response(
        self, package_name: str, response: str
    ) -> PackageEvaluation:
        """解析 AI 评估响应"""
        try:
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return PackageEvaluation(
                    package_name=package_name,
                    is_safe=data.get("is_safe", False),
                    risk_level=data.get("risk_level", "medium_risk"),
                    reason=data.get("reason", "AI 评估"),
                    category=data.get("category", "unknown"),
                )
        except json.JSONDecodeError:
            pass

        # JSON 解析失败 → 从文本中提取
        is_safe = "true" in response.lower() or "safe" in response.lower()
        risk_level = "safe" if is_safe else "medium_risk"

        return PackageEvaluation(
            package_name=package_name,
            is_safe=is_safe,
            risk_level=risk_level,
            reason="AI 评估（文本解析）",
            category="unknown",
        )

    @staticmethod
    def _normalize_package_name(name: str) -> str:
        """规范化包名"""
        normalized = name.lower().strip()
        normalized = re.sub(r'[-_]+', '-', normalized)
        normalized = re.sub(r'\[.*\]', '', normalized)
        return normalized

    def filter_packages(self, packages: List[str]) -> Tuple[List[str], List[str]]:
        """
        过滤包列表，返回允许的和拒绝的

        Args:
            packages: 原始包列表

        Returns:
            (allowed_packages, rejected_packages)
        """
        allowed = []
        rejected = []

        for pkg in packages:
            # 先检查黑名单（包括原始包名和规范化后的包名）
            if self.is_blocked(pkg):
                rejected.append(pkg)
                continue
            
            normalized = self._normalize_package_name(pkg)
            if self.is_in_whitelist(normalized):
                allowed.append(pkg)
            else:
                # 不在白名单也不在黑名单 → 需要评估（异步）
                allowed.append(pkg)  # 先放入待评估列表

        return allowed, rejected