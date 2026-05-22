import json
import logging
from typing import Dict

from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_frontend_engineer_prompt
from app.agent.tracing import traced

logger = logging.getLogger(__name__)


class FrontendEngineer(Specialist):
    """前端工程师 - 专注前端代码生成"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_frontend_engineer_prompt()
        if prompt is None:
            logger.error("前端工程师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级前端工程师，精通所有主流前端技术和跨平台开发框架。
你的职责：创建前端文件、编写高质量可维护的代码、实现响应式 UI 和状态管理。
规则：每次只创建一个文件，代码必须完整可运行。"""

    @traced("frontend.generate_file", attributes={"component": "specialist", "role": "frontend"})
    async def generate_file(self, file_path: str, description: str, project_context: Dict) -> str:
        prompt = f"""请创建以下前端文件：

文件路径：{file_path}
文件描述：{description}
项目上下文：{json.dumps(project_context, ensure_ascii=False, indent=2)}

请返回完整的文件内容，不要省略任何部分。"""

        return await self.call_llm(prompt, self.SYSTEM_PROMPT)