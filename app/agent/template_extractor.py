import json
import logging
from typing import List, Dict, Optional

from app.agent.orchestrator_requirements import DOMAIN_TEMPLATES_DIR

logger = logging.getLogger(__name__)

TEMPLATE_REVIEW_MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
TEMPLATE_EXTRACT_MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"


class TemplateExtractor:

    async def extract_template(
        self, domain: str, projects: List[Dict]
    ) -> Optional[Dict]:
        feature_lists = []
        for p in projects:
            fl = p.get("feature_list", [])
            if fl:
                feature_lists.append(fl)

        if len(feature_lists) < 5:
            logger.info(f"有效功能清单数 {len(feature_lists)} < 5, 跳过萃取")
            return None

        all_features = []
        for fl in feature_lists:
            all_features.extend(fl)

        prompt = f"""基于以下 {len(feature_lists)} 个 {domain} 领域项目的功能清单，萃取出该领域的通用模板。

项目功能清单汇总：
{json.dumps(all_features[:200], ensure_ascii=False)}

请严格按照以下 JSON 格式输出领域模板，不要输出任何其他内容：
{
  "domain": "{domain}",
  "version": "auto_extracted",
  "description": "基于历史项目自动萃取的{domain}领域模板",
  "applicable_project_types": ["medium", "large"],
  "core_modules": [
    {"name": "模块名", "category": "core/optional", "impact": "影响说明", "options": ["选项A", "选项B"], "default": "默认选项"}
  ],
  "non_functional_requirements": [
    {"category": "security/performance/compliance", "item": "需求描述", "priority": "high/medium"}
  ],
  "common_pitfalls": ["陷阱1", "陷阱2"],
  "key_decisions": [
    {"question": "决策问题", "impact": "architecture/data_model/storage", "options": ["选项A", "选项B"]}
  ]
}

萃取要求：
1. core_modules 只提取出现频率 >=40% 的功能模块
2. non_functional_requirements 提取该领域最常见的非功能需求
3. common_pitfalls 提取该领域最容易犯的错误
4. key_decisions 提取架构层面的关键决策点
5. 每个 core_modules 的 category 标记：出现频率 >=70% 为 core, 40-70% 为 optional"""

        try:
            from app.utils import call_llm
            response = await call_llm(
                model=TEMPLATE_EXTRACT_MODEL,
                prompt=prompt,
            )
        except Exception as e:
            logger.warning(f"模板萃取主模型失败: {e}")
            return None

        template = self._parse_template_response(response, domain)
        if not template:
            return None

        review_result = await self._review_template(template)
        if not review_result.get("approved"):
            logger.warning(
                f"模板萃取审核未通过: {review_result.get('reason', 'unknown')}"
            )
            return None

        self._save_template(template, domain)
        logger.info(f"领域模板 {domain} 自动萃取并审核通过")
        return template

    def _parse_template_response(
        self, response: str, domain: str
    ) -> Optional[Dict]:
        import re
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                template = json.loads(json_match.group())
                template["domain"] = domain
                template["version"] = "auto_extracted"
                if not template.get("core_modules"):
                    return None
                return template
        except json.JSONDecodeError:
            pass

        logger.warning(f"模板萃取输出非 JSON: {response[:100]}")
        return None

    async def _review_template(self, template: Dict) -> Dict:
        prompt = f"""你是领域模板审核员。请审核以下自动萃取的领域模板，判断是否可以入库使用。

模板内容：
{json.dumps(template, ensure_ascii=False, indent=2)}

审核标准：
1. core_modules 是否覆盖该领域核心功能（>=5 个模块）
2. non_functional_requirements 是否合理（至少包含 security 类）
3. common_pitfalls 是否有实际价值（>=3 个）
4. key_decisions 是否是真正的架构级决策（>=2 个）
5. 无明显错误或荒谬内容

请严格按照以下 JSON 格式输出审核结果：
{
  "approved": true/false,
  "reason": "审核理由",
  "suggestions": ["改进建议1", "改进建议2"]
}"""

        try:
            from app.utils import call_llm
            response = await call_llm(
                model=TEMPLATE_REVIEW_MODEL,
                prompt=prompt,
            )
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"模板审核失败: {e}")

        return {"approved": False, "reason": "审核过程异常"}

    def _save_template(self, template: Dict, domain: str):
        existing_path = DOMAIN_TEMPLATES_DIR / f"{domain}.json"
        if existing_path.exists():
            backup_path = DOMAIN_TEMPLATES_DIR / f"{domain}_manual.json"
            with open(existing_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            logger.info(f"原手工模板已备份为 {backup_path}")

        with open(existing_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
