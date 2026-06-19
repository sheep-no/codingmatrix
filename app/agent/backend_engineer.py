import json
import logging
from typing import Dict, Optional, Any

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

    @staticmethod
    def _infer_file_type_from_path(file_path: str) -> str:
        """从文件路径推断 file_type"""
        path_lower = file_path.lower()
        if 'model' in path_lower:
            return 'model'
        if 'api' in path_lower or 'router' in path_lower or 'handler' in path_lower or 'controller' in path_lower:
            return 'api'
        if 'service' in path_lower:
            return 'service'
        if 'repo' in path_lower or 'repository' in path_lower or 'dao' in path_lower:
            return 'repository'
        if 'database' in path_lower or 'db' in path_lower:
            return 'database'
        if 'config' in path_lower or 'settings' in path_lower:
            return 'config'
        if 'middleware' in path_lower:
            return 'middleware'
        if 'test' in path_lower:
            return 'test'
        if 'util' in path_lower or 'helper' in path_lower:
            return 'utils'
        if 'main' in path_lower or 'app' in path_lower or 'index' in path_lower:
            return 'entry'
        return 'unknown'

    @staticmethod
    def _build_spec_constraints(file_type: str, file_spec: Dict) -> str:
        """构建 project_spec 约束文本"""
        if not file_spec:
            return ""

        lines = []
        storage = file_spec.get("storage", {})
        terminology = file_spec.get("terminology", {})
        framework = file_spec.get("framework")

        if framework:
            lines.append(f"【框架约束 - 必须遵守】")
            lines.append(f"- 本项目统一使用 {framework} 框架")
            lines.append(f"- 所有后端文件必须使用 {framework} 的 API 和导入方式")
            lines.append(f"- 禁止混用其他框架（如 Flask、Django、Tornado 等）")
            lines.append(f"- requirements.txt / go.mod 等依赖文件必须包含 {framework} 的依赖")
            lines.append("")

        if storage:
            storage_type = storage.get("type", "unknown")
            lines.append(f"【存储约束 - 必须遵守】")
            lines.append(f"- 存储方式: {storage_type}")
            if storage.get("filename"):
                lines.append(f"- 存储文件: {storage['filename']}")
            if storage_type == "localStorage":
                lines.append(f"- 注意：localStorage 是浏览器 API，后端文件禁止使用，请使用文件存储或数据库替代")
            lines.append("")

        if terminology:
            lines.append(f"【术语约束 - 必须遵守】")
            lines.append(f"- 项目统一使用以下术语（字段名、变量名、API 路径必须遵循）:")
            for en_term, actual_term in terminology.items():
                lines.append(f"  - {en_term} -> {actual_term}")
            lines.append("")

        return "\n".join(lines)

    @traced("backend.generate_file", attributes={"component": "specialist", "role": "backend"})
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
        heartbeat_tracker=None,
    ) -> str:
        # 从 project_context 中提取语言信息
        architecture = project_context.get("architecture", {})
        project_language = architecture.get("language", "python")

        # 根据文件路径动态决定此文件的实际语言（避免配置文件被错误标记）
        from app.agent.utils import get_expected_language_for_file
        file_actual_language = get_expected_language_for_file(file_path, project_language)
        if not file_actual_language:
            file_actual_language = project_language
        lang_rules = LanguageDetector.get_language_specific_rules(project_language)

        # 从 project_spec 中提取当前文件的约束
        project_spec = architecture.get("project_spec", {})
        file_type = self._infer_file_type_from_path(file_path)
        file_spec = project_spec.get(file_type, project_spec.get("default", {}))
        spec_constraints = self._build_spec_constraints(file_type, file_spec)

        prompt = f"""【严格约束】你必须严格按文件路径指定的语言编写代码，禁止自行添加或修改扩展名。

请创建以下文件：

文件路径：{file_path}
文件描述：{description}
此文件的语言：{file_actual_language}
项目主语言：{project_language}
文件类型：{file_type}

【任务约束 - 最高优先级】
- 你本次任务只创建 {file_path} 这一个文件
- 先用 read_file / list_files / search_files 等工具探索项目结构和已有代码，了解上下文
- 探索完成后，直接以纯文本形式返回 {file_path} 的完整内容
- 不要尝试创建或修改其他文件

{spec_constraints}

【语言约束 - 必须遵守】
- 文件路径中已经包含正确的扩展名（如 .py、.go、.java、.json、.toml、.md 等），你必须保留原始路径，不允许添加项目主语言的扩展名
- 例如：文件路径是 "requirements.txt"，你创建的文件路径必须是 "requirements.txt"，不能是 "requirements.txt.py"
- 例如：文件路径是 "package.json"，你必须返回的是 JSON 内容
- 文件内容必须与此文件路径的扩展名匹配
- 如果文件路径是 .py/.go/.java 等后端文件，使用 {project_language} 编写
- 如果文件路径是 .json/.toml/.md/.yml/.yaml 等配置文件或文档文件，使用对应格式编写
- 禁止在 javascript 文件中使用 Python 语法（如 def、class、import os、from xxx import）
- 禁止在 python 文件中使用 JavaScript 语法（如 const、let、require、module.exports）

【运行时约束 - 严格遵守】
- 你的 file_type 是 {file_type}，这是一个后端文件
- 禁止使用浏览器 API：window, document, localStorage, sessionStorage, navigator, fetch(浏览器版)
- 禁止使用 DOM 操作：getElementById, querySelector, addEventListener
- 只能使用 {project_language} 的标准库和后端框架 API

导入规则（重要）：
- 包内文件之间的导入必须使用相对导入（如 from .utils import greet）
- 不要使用绝对导入（如 from src.utils import greet）
- 只有第三方库才用绝对导入

【跨文件导入验证 - 必须执行】
在生成代码前，你必须验证所有跨文件导入的正确性：
1. 用 read_symbols 或 read_file 查看目标模块实际导出了哪些符号（函数、类、变量）
2. 用 search_files 搜索你要导入的符号名是否在目标文件中正确定义
   示例：search_files(pattern="def FastAPI|class FastAPI", file_pattern="*.py")
3. 如果目标文件中不存在该符号，你必须：
   a) 修正导入路径（找到真正定义该符号的文件），或
   b) 在目标文件中添加该符号的定义
4. 确认所有跨文件导入正确后再返回代码
不要凭猜测导入不存在的符号。每次导入项目内模块前，先验证再使用。

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
- execute_code: 验证修改后的代码是否正确（仅 Python）

编辑规则：
1. 先用 read_file 读取文件现有内容，理解结构
2. 用 partial_update 或 insert_content 做精准编辑，不要重写整个文件
3. 编辑完成后，返回 JSON：{{"action": "edited", "files": ["{file_path}"], "summary": "修改摘要"}}
4. 如果改动太大无法局部修改，用 write_file 重写整个文件，返回完整内容
"""
        elif '__init__' in file_path:
            prompt += """
这是一个包入口文件（__init__.py）。

重要：你必须先读取同包目录下的其他 Python 文件，了解它们实际导出了哪些函数、类和变量，然后基于实际导出内容编写 __init__.py。

步骤：
1. 用 list_files 列出同包目录下的所有文件
2. 用 read_file 读取每个 .py 文件，提取它们的导出（def、class、__all__）
3. 基于实际导出内容编写 __init__.py 的 import 语句
4. 返回完整的 __init__.py 内容

示例：如果 utils.py 导出了 greet 和 farewell 函数，__init__.py 应该是：
```python
from .utils import greet, farewell
```
"""
        else:
            prompt += f"""
【输出格式 - 严格遵守】
- 直接返回 {file_actual_language} 代码，不要包裹在 JSON 对象中
- 不要返回 status、message、file_path、file_size 等元数据字段
- 不要返回 "以下是代码" 等引导语
- 不要用 ```markdown 代码块标记包裹整个文件
- 第一行必须是实际代码（import、定义、注释等）

请返回完整的文件内容，使用 {file_actual_language} 语法编写，不要省略任何部分。"""

        # 有项目路径时使用 ReAct 工具调用，否则退化为普通 call_llm
        # 编码阶段限制 thinking：省 token 留给代码输出，同时保留少量思考给用户展示
        # 报错修复场景（error_recovery/_fix_sandbox_errors）走独立路径，保持默认 thinking
        logger.info(f"BackendEngineer.generate_file: project_path={project_path}, callback={callback is not None}")
        if heartbeat_tracker:
            heartbeat_tracker.touch()
        if project_path:
            # 只给只读工具：LLM 用它们探索项目上下文，然后直接返回文件内容
            # 禁止 write_file/create_file：避免 LLM 写入其他文件（如 requirements.txt）而非目标文件
            from app.agent.tools import SPECIALIST_TOOLS
            read_only_tools = {
                k: v for k, v in SPECIALIST_TOOLS.items()
                if k in ('read_file', 'list_files', 'read_symbols', 'read_imports',
                         'summarize_file', 'search_files')
            }
            result = await self.call_llm_with_tools(
                prompt, self.SYSTEM_PROMPT, tools=read_only_tools,
                project_path=project_path, callback=callback,
                heartbeat_tracker=heartbeat_tracker, enable_streaming_thinking=True,
                thinking_budget=50,
            )
        else:
            result = await self.call_llm(prompt, self.SYSTEM_PROMPT, thinking_budget=50)
        if heartbeat_tracker:
            heartbeat_tracker.touch()
        return result

    @traced("backend.analyze", attributes={"component": "specialist", "role": "backend"})
    async def analyze(
        self,
        question: str,
        project_path: str,
        project_context: Optional[Dict] = None,
        callback: Optional[Any] = None,
        heartbeat_tracker=None,
    ) -> str:
        """分析模式 — 只读代码，用自然语言回答用户问题

        Args:
            question: 用户的问题（如"有哪些改进空间？"）
            project_path: 项目路径
            project_context: 项目上下文（可选）
            callback: 进度回调
            heartbeat_tracker: 心跳跟踪器

        Returns:
            自然语言分析结果
        """
        context_info = ""
        if project_context:
            architecture = project_context.get("architecture", {})
            language = architecture.get("language", "未知")
            context_info = f"\n项目主语言: {language}"

        # 先用工具读取项目结构
        project_files = []
        if project_path:
            from app.agent.tools import SPECIALIST_TOOLS
            read_only_tools = {
                k: v for k, v in SPECIALIST_TOOLS.items()
                if k in ('read_file', 'list_files', 'read_symbols', 'read_imports',
                         'summarize_file', 'search_files')
            }

            # 用 list_files 获取项目结构
            list_files_tool = read_only_tools.get('list_files')
            if list_files_tool:
                try:
                    files_result = await list_files_tool['function'](
                        directory=project_path,
                        max_depth=3
                    )
                    if files_result:
                        project_files = files_result.get('files', [])[:20]  # 限制文件数量
                except Exception as e:
                    logger.warning(f"获取文件列表失败: {e}")

        # 构建分析 prompt
        files_info = ""
        if project_files:
            files_info = f"\n项目文件结构:\n{json.dumps(project_files, ensure_ascii=False, indent=2)}"

        prompt = f"""你是一位资深代码分析师和架构师。用户向你提问，请分析项目并用自然语言回答。

用户问题：{question}
{context_info}
{files_info}

【分析流程】
1. 根据项目文件结构，分析项目的整体架构
2. 识别潜在的问题和改进空间
3. 给出具体的改进建议

【输出要求】
- 用自然语言回答，不要生成代码文件
- 如果是"改进空间"类问题，从以下维度分析：
  - 代码质量（命名、结构、可读性）
  - 架构设计（分层、耦合、扩展性）
  - 安全性（输入验证、错误处理、敏感信息）
  - 性能（潜在瓶颈、优化空间）
  - 最佳实践（框架约定、设计模式）
- 给出具体的改进建议，指出问题所在文件和行号
- 使用中文回答
"""

        logger.info(f"BackendEngineer.analyze: project_path={project_path}")
        if heartbeat_tracker:
            heartbeat_tracker.touch()

        # 直接调用 LLM，不使用 ReAct 引擎
        result = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        if heartbeat_tracker:
            heartbeat_tracker.touch()
        return result
