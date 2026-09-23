import json
import time
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Optional

from app.agent.vector_index import METADATA_PATH
from app.agent.models import DEFAULT_REASONING_MODEL, DEFAULT_CODE_MODEL

logger = logging.getLogger(__name__)

FEATURE_EXTRACTION_MODEL = DEFAULT_REASONING_MODEL
FEATURE_EXTRACTION_FALLBACK = DEFAULT_CODE_MODEL


class ProjectMetadataManager:

    def __init__(self):
        METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._projects: List[Dict] = []
        self._load()

    def _load(self):
        if METADATA_PATH.exists():
            try:
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    self._projects = json.load(f)
            except Exception as e:
                logger.warning(f"project_metadata.json 加载失败: {e}")
                self._projects = []
        else:
            self._projects = []

    def _save(self):
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(self._projects, f, ensure_ascii=False, indent=2)

    def total_count(self) -> int:
        return len(self._projects)

    def count_with_features(self) -> int:
        # file_fallback 是文件名生成的伪功能，供历史匹配使用前需与真实提取区分
        return sum(
            1 for p in self._projects
            if p.get("feature_source") != "file_fallback"
            and p.get("feature_list") and len(p.get("feature_list")) > 0
        )

    def get_projects_by_domain(self, domain: str) -> List[Dict]:
        return [
            p for p in self._projects
            if p.get("domain") == domain
        ]

    def get_all_projects(self) -> List[Dict]:
        return self._projects

    async def extract_and_save(
        self, requirement: str,
        generated_files: Dict[str, str],
        domain: str = "",
        project_id: Optional[str] = None,
    ) -> Dict:
        feature_list, feature_source = await self._extract_feature_list(
            requirement, generated_files
        )

        project_meta = {
            "project_id": project_id or str(uuid.uuid4()),
            "requirement": requirement,
            "domain": domain,
            "feature_list": feature_list,
            "feature_source": feature_source,
            "file_count": len(generated_files),
            "created_at": time.time(),
        }

        self._projects.append(project_meta)
        self._save()

        try:
            from app.agent.vector_index import VectorIndexManager
            vi = VectorIndexManager()
            vi.load_or_create()
            await vi.add_project(project_meta)
        except Exception as e:
            logger.warning(f"向量索引追加失败: {e}")

        logger.info(
            f"功能清单提取完成: {len(feature_list)} 项, "
            f"总计 {len(self._projects)} 项目"
        )
        return project_meta

    async def _extract_feature_list(
        self, requirement: str,
        generated_files: Dict[str, str]
    ) -> "tuple[List[str], str]":
        file_summary = self._summarize_files(generated_files)

        # JSON 示例的字面花括号必须转义，否则会被 f-string 当作格式说明符求值并抛
        # ValueError（此前该函数每次调用即失败，功能清单从未落库）。
        prompt = f"""分析以下项目需求描述和生成的代码文件列表，提取该项目实现的结构化功能清单。

项目需求：
{requirement}

生成的文件列表及功能摘要：
{file_summary}

请严格按照以下 JSON 格式输出功能清单，不要输出任何其他内容：
{{
  "features": [
    "用户登录与认证",
    "商品浏览与搜索",
    "订单创建与管理"
  ]
}}

功能清单要求：
1. 每个功能点用一句话描述，从用户或系统视角
2. 只包含实际实现的功能，不包含计划中但未实现的功能
3. 优先关注核心业务功能，其次是非功能特性（安全/性能/日志等）
4. 最多 30 个功能点"""

        try:
            from app.utils import call_llm
            response = await call_llm(
                model=FEATURE_EXTRACTION_MODEL,
                prompt=prompt,
            )
        except Exception as e:
            logger.warning(f"功能清单提取主模型失败: {e}")
            try:
                from app.utils import call_llm
                response = await call_llm(
                    model=FEATURE_EXTRACTION_FALLBACK,
                    prompt=prompt,
                )
            except Exception as e2:
                logger.warning(f"功能清单提取降级模型也失败: {e2}")
                return (
                    self._fallback_feature_list(requirement, generated_files),
                    "file_fallback",
                )

        return self._parse_features_with_source(response)

    def _summarize_files(self, generated_files: Dict[str, str]) -> str:
        total = len(generated_files)
        lines = []
        for filepath, content in list(generated_files.items())[:50]:
            content_preview = content[:200].replace("\n", " ").strip()
            truncated = "（内容已截断）" if len(content) > 200 else ""
            lines.append(f"  {filepath}: {content_preview}{truncated}")
        if total > 50:
            lines.append(f"  ...（共 {total} 个文件，仅展示前 50 个）")
        return "\n".join(lines)

    def _parse_feature_response(self, response: str) -> List[str]:
        features, _ = self._parse_features_with_source(response)
        return features

    def _parse_features_with_source(self, response: str) -> "tuple[List[str], str]":
        # 逐「{」尝试解析首个 JSON 对象；贪婪 \{[\s\S]*\} 在多 JSON 块时会跨块匹配
        # 导致 json.loads 失败，进而把整段 JSON 原文当成功能项。
        from app.agent.json_parser import extract_first_json_object

        parsed = extract_first_json_object(response)
        if parsed is not None:
            features = self._coerce_feature_list(parsed)
            if features is not None:
                return features, "llm"
            logger.warning("功能清单响应 features 非字符串列表，回退文本解析")
        return self._parse_text_features(response), "llm_text"

    @staticmethod
    def _coerce_feature_list(parsed: Dict) -> Optional[List[str]]:
        # features 缺失/为 null/dict 时显式判非法，避免 TypeError 逃逸或静默空
        features = parsed.get("features")
        if not isinstance(features, list):
            return None
        return [f for f in features if isinstance(f, str) and len(f) > 3][:30]

    @staticmethod
    def _parse_text_features(response: str) -> List[str]:
        features = []
        for line in response.strip().split("\n"):
            line = line.strip().lstrip("- ").lstrip("0123456789. ")
            if not line or len(line) <= 3 or line.startswith("#"):
                continue
            # 跳过 JSON 片段，避免把 {"features": [...]} 原文当功能项
            if any(ch in line for ch in "{}[]") or '"features"' in line:
                continue
            features.append(line)
        return features[:30]

    def _fallback_feature_list(
        self, requirement: str,
        generated_files: Dict[str, str]
    ) -> List[str]:
        features = []
        for filepath in generated_files.keys():
            filename = Path(filepath).stem
            if filename in ["app", "main", "index", "config", "utils", "models"]:
                continue
            features.append(f"{filename} 模块")
        return features[:20]

    async def trigger_template_extraction(
        self, domain: str, min_projects: int = 15
    ) -> Optional[Dict]:
        domain_projects = self.get_projects_by_domain(domain)
        if len(domain_projects) < min_projects:
            logger.info(
                f"领域 {domain} 项目数 {len(domain_projects)} < {min_projects}, "
                f"不触发模板萃取"
            )
            return None

        from app.agent.template_extractor import TemplateExtractor
        extractor = TemplateExtractor()
        result = await extractor.extract_template(domain, domain_projects)
        return result
