import json
import logging
from typing import Dict

from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_backend_engineer_prompt
from app.agent.tracing import traced
from app.agent.language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class BackendEngineer(Specialist):
    """后端工程师 - 专注后端代码生成"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_backend_engineer_prompt()
        if prompt is None:
            logger.error("后端工程师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级后端工程师，精通所有主流后端编程语言和框架。
你的职责：创建后端文件、实现 API 端点、数据库模型、业务逻辑、错误处理。
规则：每次只创建一个文件，代码必须完整可运行，包含错误处理和类型注解。"""

    @traced("backend.generate_file", attributes={"component": "specialist", "role": "backend"})
    async def generate_file(self, file_path: str, description: str, project_context: Dict) -> str:
        # 从 project_context 中提取语言信息
        architecture = project_context.get("architecture", {})
        language = architecture.get("language", "python")
        lang_rules = LanguageDetector.get_language_specific_rules(language)

        prompt = f"""请创建以下后端文件：

文件路径：{file_path}
文件描述：{description}
目标语言：{language}
语言规则：
- 文件扩展名：{lang_rules['file_extension']}
- 导入语法：{lang_rules['import_syntax']}
- 入口文件：{lang_rules['entry_point']}

项目上下文：{json.dumps(project_context, ensure_ascii=False, indent=2)}

请返回完整的文件内容，使用 {language} 语法编写，不要省略任何部分。"""

        return await self.call_llm(prompt, self.SYSTEM_PROMPT)