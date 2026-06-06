import re
import json
import logging
from typing import Dict, List

from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_code_reviewer_prompt
from app.agent.tracing import traced

logger = logging.getLogger(__name__)


class CodeReviewer(Specialist):
    """代码审查员 - 负责代码质量和安全审查"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_code_reviewer_prompt()
        if prompt is None:
            logger.error("代码审查员提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级代码审查专家，精通所有主流编程语言的安全、性能和最佳实践。
审查维度：安全性、正确性、性能、可维护性、最佳实践、版本兼容性。
输出格式：JSON，包含 approved、risk_level、issues、suggestions、needs_fix、version_issues。"""

    # 常见库的版本兼容性规则
    VERSION_RULES = {
        "fastapi": {
            "0.100.0": {"removed": ["Middleware"], "changed": {"OAuth2PasswordBearer": "tokenUrl -> token_url"}},
            "0.90.0": {"added": ["APIRouter.include_router"]},
        },
        "sqlalchemy": {
            "2.0.0": {"removed": ["session.query()"], "changed": {"declarative_base": "DeclarativeBase"}},
        },
        "pydantic": {
            "2.0.0": {"removed": ["Field.regex"], "changed": {"BaseModel.dict": "model_dump"}},
        },
        "passlib": {
            "1.7.0": {"changed": {"import passlib.hash.bcrypt": "from passlib.hash import bcrypt"}},
        },
    }

    @traced("reviewer.review_code", attributes={"component": "specialist", "role": "reviewer"})
    async def review_code(self, code: str, file_path: str, context: str = "") -> Dict:
        """审查代码"""
        # 先进行版本兼容性检查
        version_issues = await self._check_version_compatibility(code)

        prompt = f"""请审查以下代码：

文件路径：{file_path}
上下文：{context}

代码：
```
{code}
```

请输出审查结果。"""

        response = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                result = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"CodeReviewer LLM 输出非合法 JSON，标记为需要人工审查: {response[:200]}")
            result = {
                "approved": False,
                "risk_level": "medium",
                "issues": ["LLM 审查结果解析失败，需人工审查"],
                "suggestions": [],
                "needs_fix": True
            }

        # 合并版本兼容性问题
        if version_issues:
            result["version_issues"] = version_issues
            if not result.get("issues"):
                result["issues"] = []
            result["issues"].extend(version_issues)
            if version_issues and result.get("risk_level") == "low":
                result["risk_level"] = "medium"
            result["needs_fix"] = True

        return result

    async def _check_version_compatibility(self, code: str) -> List[str]:
        """动态检查代码中使用的库版本兼容性"""
        issues = []

        # 尝试获取已安装包的版本
        try:
            import importlib.metadata as metadata
            installed_versions = {}
            for pkg_name in self.VERSION_RULES.keys():
                try:
                    version = metadata.version(pkg_name)
                    installed_versions[pkg_name] = version
                except metadata.PackageNotFoundError:
                    pass
        except ImportError:
            # Python < 3.8 回退
            try:
                import pkg_resources
                installed_versions = {}
                for pkg_name in self.VERSION_RULES.keys():
                    try:
                        version = pkg_resources.get_distribution(pkg_name).version
                        installed_versions[pkg_name] = version
                    except pkg_resources.DistributionNotFound:
                        pass
            except ImportError:
                return issues

        # 检查代码中的导入语句
        import_matches = re.findall(r'(?:from\s+(\w+)|import\s+(\w+))', code)

        for match in import_matches:
            pkg_name = match[0] or match[1]
            if pkg_name in self.VERSION_RULES and pkg_name in installed_versions:
                installed_version = installed_versions[pkg_name]
                rules = self.VERSION_RULES[pkg_name]

                # 检查是否有已知的兼容性问题
                for rule_version, rule_details in rules.items():
                    if self._version_gte(installed_version, rule_version):
                        if "removed" in rule_details:
                            for removed_api in rule_details["removed"]:
                                if removed_api in code:
                                    issues.append(
                                        f"[{pkg_name} v{installed_version}] API '{removed_api}' 在 v{rule_version}+ 中已移除"
                                    )
                        if "changed" in rule_details:
                            for old_api, new_api in rule_details["changed"].items():
                                if old_api in code:
                                    issues.append(
                                        f"[{pkg_name} v{installed_version}] 建议将 '{old_api}' 改为 '{new_api}'"
                                    )

        return issues

    def _version_gte(self, version: str, target: str) -> bool:
        """比较版本号是否大于等于目标版本"""
        try:
            from packaging.version import Version
            return Version(version) >= Version(target)
        except ImportError:
            # 简单字符串比较（仅适用于语义化版本）
            v1_parts = [int(x) for x in version.split(".")]
            v2_parts = [int(x) for x in target.split(".")]
            return v1_parts >= v2_parts
