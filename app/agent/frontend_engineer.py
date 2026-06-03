import json
import logging
from typing import Dict, Optional, Any

from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_frontend_engineer_prompt
from app.agent.tracing import traced
from app.agent.language_detector import LanguageDetector

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
    async def generate_file(
        self,
        file_path: str,
        description: str,
        project_context: Dict,
        spec_context: str = "",
        dep_context: str = "",
        project_path: Optional[str] = None,
        callback: Optional[Any] = None,
        is_existing_file: bool = False,
    ) -> str:
        # 从 project_context 中提取语言信息
        architecture = project_context.get("architecture", {})
        language = architecture.get("language", "javascript")
        lang_rules = LanguageDetector.get_language_specific_rules(language)

        prompt = f"""请创建以下前端文件：

文件路径：{file_path}
文件描述：{description}
目标语言：{language}
语言规则：
- 文件扩展名：{lang_rules['file_extension']}
- 导入语法：{lang_rules['import_syntax']}

项目上下文：{json.dumps(project_context, ensure_ascii=False, indent=2)}
"""

        if spec_context:
            prompt += f"""
## 相关规范（必须严格遵守）
{spec_context}
"""

        if dep_context:
            prompt += f"""
## 已生成依赖文件（请基于以下已存在的代码保持接口/类型一致）
{dep_context}
"""

        if is_existing_file:
            prompt += f"""
这是一个已有文件的增量修改任务。

你可以使用以下工具进行精准编辑：
- partial_update: 替换指定函数或代码块（推荐，按函数名精准替换）
- insert_content: 在指定位置插入内容（按行号或锚点文本）
- regex_replace: 批量正则替换
- execute_code: 验证修改后的代码是否正确

编辑规则：
1. 先用 read_file 读取文件现有内容，理解结构
2. 用 partial_update 或 insert_content 做精准编辑，不要重写整个文件
3. 编辑完成后，返回 JSON：{{"action": "edited", "files": ["{file_path}"], "summary": "修改摘要"}}
4. 如果改动太大无法局部修改，用 write_file 重写整个文件，返回完整内容
"""
        elif '__init__' in file_path:
            prompt += """
这是一个包入口文件（__init__.py）。

重要：你必须先读取同包目录下的其他文件，了解它们实际导出了哪些函数、类和变量，然后基于实际导出内容编写 __init__.py。

步骤：
1. 用 list_files 列出同包目录下的所有文件
2. 用 read_file 读取每个文件，提取它们的导出（export、default export）
3. 基于实际导出内容编写 __init__.py 的 import 语句
4. 返回完整的 __init__.py 内容
"""
        else:
            prompt += f"""
请返回完整的文件内容，使用 {language} 语法编写，不要省略任何部分。"""

        # 有项目路径时使用 ReAct 工具调用，否则退化为普通 call_llm
        if project_path:
            return await self.call_llm_with_tools(
                prompt, self.SYSTEM_PROMPT, project_path=project_path, callback=callback
            )
        return await self.call_llm(prompt, self.SYSTEM_PROMPT)
