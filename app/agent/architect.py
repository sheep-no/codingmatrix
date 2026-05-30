import re
import json
import logging
from typing import Optional, Dict

from app.utils import call_llm
from app.agent.complexity import ComplexityAnalysis
from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_architect_prompt
from app.agent.tracing import traced
from app.agent.language_detector import LanguageDetector
from app.agent.architect_json_parser import ArchitectJsonParser

logger = logging.getLogger(__name__)


class Architect(Specialist):
    """架构师 - 负责技术选型和整体架构设计"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.json_parser = ArchitectJsonParser()

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_architect_prompt()
        if prompt is None:
            logger.error("架构师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级首席软件架构师，精通几乎所有编程语言和技术栈。
你的职责：分析需求、设计架构、定义 API 和数据库 Schema。
输出格式要求：必须只输出 JSON 格式，不要包含任何解释文字。"""

    @traced("architect.design", attributes={"component": "specialist", "role": "architect"})
    async def design_architecture(self, requirement: str, complexity: ComplexityAnalysis) -> Dict:
        """设计项目架构"""
        # 检测目标语言
        lang_detection = LanguageDetector.detect(requirement)
        target_language = lang_detection.language
        lang_rules = LanguageDetector.get_language_specific_rules(target_language)

        logger.info(f"检测到目标语言: {target_language} (置信度: {lang_detection.confidence:.2f})")
        logger.info(f"检测依据: {lang_detection.evidence}")

        # 构建语言规则部分（如果语言未知，让 LLM 推断）
        if lang_detection.needs_clarification or lang_rules.get('needs_clarification'):
            lang_rules_text = f"""目标语言：{target_language}
注意：该语言不在已知列表中，请根据语言名称推断正确的文件扩展名、入口文件、语法约定等。
例如：Zig → .zig，Nim → .nim，Crystal → .cr 等。"""
        else:
            lang_rules_text = f"""目标语言：{target_language}
语言规则：
- 文件扩展名：{lang_rules['file_extension']}
- 包入口文件：{lang_rules['package_init']}
- 导入语法：{lang_rules['import_syntax']}
- 入口文件：{lang_rules['entry_point']}
- 测试框架：{lang_rules['test_framework']}
- 包管理器：{lang_rules['package_manager']}
- 配置文件：{', '.join(lang_rules['config_files']) if lang_rules['config_files'] else '无'}
- 推荐结构：{chr(10).join('- ' + s for s in lang_rules['common_structure'])}"""

        prompt = f"""请为以下需求设计项目架构：

需求：{requirement}

复杂度分析：
- 等级：{complexity.level.value}
- 预估文件数：{complexity.estimated_files}
- 有前端：{complexity.has_frontend}
- 有后端：{complexity.has_backend}
- 有数据库：{complexity.has_database}
- 技术栈：{', '.join(complexity.key_technologies)}
- 风险因素：{', '.join(complexity.risk_factors)}

{lang_rules_text}

请输出完整的架构设计，必须包含 api_spec（后端接口定义）和 db_schema（数据库表结构）。

输出格式要求：
- 只输出 JSON 格式
- 不要包含任何解释文字
- 必须包含以下字段：project_type, frontend_structure, backend_structure, api_spec, db_schema, file_plan
- 所有文件必须使用 {target_language} 的文件扩展名和语法

file_plan 格式要求（每个文件必须包含 imports 字段）：
```json
{{{{
  "file_plan": [
    {{"path": "<入口文件>", "description": "主程序入口", "priority": 1, "imports": [...]}},
    ...
  ]
}}}}
```

重要规则：
1. 每个被其他文件 import 的模块都必须在 file_plan 中有对应的文件
2. imports 字段列出该文件需要导入的其他项目内模块（不包括第三方库）
3. 确保所有 import 路径都能在 file_plan 中找到对应文件
4. 使用 {target_language} 的标准语法和约定
5. 如果语言不在已知列表中，请根据语言名称推断正确的文件扩展名和语法约定"""

        response = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        # 解析 JSON
        try:
            if not response or not response.strip():
                logger.warning("架构师输出为空，返回默认架构")
                return self._get_default_architecture(complexity, target_language)

            architecture = self._safe_parse_json(response)
        except ValueError:
            logger.warning(f"架构师输出解析失败，尝试 LLM 辅助提取")
            architecture = await self._extract_json_with_llm(response, complexity)
            if not architecture:
                logger.warning("LLM 辅助提取失败，返回默认架构")
                return self._get_default_architecture(complexity, target_language)

        if architecture:
            # 验证并增强 api_spec
            if complexity.has_backend:
                architecture = self._validate_and_enhance_api_spec(architecture, complexity)

            # 验证并增强 db_schema
            if complexity.has_database:
                architecture = self._validate_and_enhance_db_schema(architecture, complexity)

            # 确保 file_plan 存在
            if not architecture.get("file_plan"):
                logger.warning("架构师未返回 file_plan，使用默认架构")
                architecture = self._get_default_architecture(complexity, target_language)

            # 补充完整性：确保所有被引用的模块都在 file_plan 中
            architecture = self._ensure_file_plan_completeness(architecture)

            return architecture
        else:
            return self._get_default_architecture(complexity, target_language)
    
    async def _extract_json_with_llm(self, raw_text: str, complexity: ComplexityAnalysis) -> Optional[Dict]:
        """使用 LLM 从非标准输出中提取 JSON"""
        extract_prompt = f"""请将以下文本转换为标准 JSON 格式：

原始文本：
{raw_text[:3000]}

要求：
1. 只输出 JSON，不要包含其他内容
2. 确保 JSON 格式正确
3. 必须包含：project_type, frontend_structure, backend_structure, api_spec, db_schema, file_plan
4. 修复以下常见问题：
   - 值中错误的反斜杠引号："INTEGER\\" 应为 "INTEGER"
   - dependencies 中的数组格式应为对象或数组
   - 文件路径中的空格应为斜杠：src store/ 应为 src/store/"""

        try:
            response = await call_llm(
                model=self.model_name,
                prompt=f"【USER】\n{extract_prompt}",
                stream=False,
                max_tokens=4096,
                temperature=0.3
            )
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._safe_parse_json(content)
        except Exception as e:
            logger.error(f"LLM 辅助提取 JSON 失败: {e}")
            return None

    def _validate_and_enhance_api_spec(self, architecture: Dict, complexity: ComplexityAnalysis) -> Dict:
        """验证并增强 API 规范"""
        api_spec = architecture.get("api_spec", {})

        # 如果没有 api_spec，生成基本的
        if not api_spec or "paths" not in api_spec:
            logger.warning("架构师未输出 api_spec，生成基本规范")
            api_spec = {
                "paths": {
                    "/api/v1/health": {
                        "get": {"summary": "健康检查", "responses": {"200": {"description": "OK"}}}
                    }
                }
            }

        # 验证路径格式
        paths = api_spec.get("paths", {})
        for path, methods in paths.items():
            if not path.startswith("/"):
                paths[f"/{path}"] = methods
                del paths[path]

        architecture["api_spec"] = api_spec
        return architecture

    def _validate_and_enhance_db_schema(self, architecture: Dict, complexity: ComplexityAnalysis) -> Dict:
        """验证并增强数据库 Schema"""
        db_schema = architecture.get("db_schema", {})

        # 如果没有 db_schema，生成基本的
        if not db_schema:
            logger.warning("架构师未输出 db_schema，生成基本规范")
            db_schema = {
                "users": {
                    "columns": {
                        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    }
                }
            }

        # 确保每个表都有 id 和 created_at
        for table, schema in db_schema.items():
            columns = schema.get("columns", {})
            if "id" not in columns:
                columns["id"] = "INTEGER PRIMARY KEY AUTOINCREMENT"
            if "created_at" not in columns:
                columns["created_at"] = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"

        architecture["db_schema"] = db_schema
        return architecture

    def _safe_parse_json(self, text: str) -> Dict:
        """安全解析 JSON，处理各种格式问题"""
        return self.json_parser.safe_parse_json(text)

    def _get_default_architecture(self, complexity: ComplexityAnalysis, language: str = "python") -> Dict:
        """返回默认架构（根据语言生成）"""
        from app.agent.language_detector import LanguageDetector
        lang_rules = LanguageDetector.get_language_specific_rules(language)

        # 根据语言生成不同的默认文件结构
        if language == "python":
            entry_point = "main.py"
            db_file = "app/database.py"
            model_file = "app/models.py"
            router_file = "app/routers.py"
            init_file = "app/__init__.py"
            dep_file = "requirements.txt"
        elif language == "javascript":
            entry_point = "src/index.ts"
            db_file = "src/database.ts"
            model_file = "src/models/user.ts"
            router_file = "src/routes/index.ts"
            init_file = None  # JS 没有 __init__.py
            dep_file = "package.json"
        elif language == "go":
            entry_point = "main.go"
            db_file = "internal/database/database.go"
            model_file = "internal/models/user.go"
            router_file = "internal/handlers/user.go"
            init_file = None  # Go 没有 __init__.py
            dep_file = "go.mod"
        elif language == "java":
            entry_point = "src/main/java/com/example/Application.java"
            db_file = "src/main/java/com/example/config/DatabaseConfig.java"
            model_file = "src/main/java/com/example/model/User.java"
            router_file = "src/main/java/com/example/controller/UserController.java"
            init_file = None  # Java 没有 __init__.py
            dep_file = "pom.xml"
        elif language == "rust":
            entry_point = "src/main.rs"
            db_file = "src/database.rs"
            model_file = "src/models/user.rs"
            router_file = "src/handlers/user.rs"
            init_file = None  # Rust 没有 __init__.py
            dep_file = "Cargo.toml"
        else:
            # 通用结构
            ext = lang_rules.get('file_extension')
            if ext:
                ext_name = ext.lstrip('.')
            else:
                ext_name = language  # 未知语言使用语言名作为扩展名
            entry_point = f"main.{ext_name}"
            db_file = f"database.{ext_name}"
            model_file = f"models/user.{ext_name}"
            router_file = f"routes/user.{ext_name}"
            init_file = None
            dep_file = "README.md"

        file_plan = [
            {"path": entry_point, "description": "主程序入口", "priority": 1, "imports": []},
            {"path": dep_file, "description": "依赖配置", "priority": 2, "imports": []},
            {"path": "README.md", "description": "项目文档", "priority": 3, "imports": []}
        ]

        if complexity.has_frontend:
            file_plan.extend([
                {"path": "index.html", "description": "前端页面", "priority": 4, "imports": []},
                {"path": "static/style.css", "description": "样式表", "priority": 5, "imports": []},
                {"path": "static/app.js", "description": "前端脚本", "priority": 5, "imports": []}
            ])

        if complexity.has_backend:
            backend_files = [
                {"path": db_file, "description": "数据库连接配置", "priority": 1, "imports": []},
                {"path": model_file, "description": "数据模型", "priority": 2, "imports": [db_file]},
                {"path": router_file, "description": "API 路由", "priority": 3, "imports": [model_file, db_file]},
            ]
            # 如果有包入口文件，添加它
            if init_file:
                backend_files.insert(0, {"path": init_file, "description": "包初始化文件", "priority": 1, "imports": []})
            file_plan.extend(backend_files)

        return {
            "project_type": "fullstack" if complexity.has_frontend and complexity.has_backend else ("frontend" if complexity.has_frontend else "backend"),
            "tech_stack": complexity.key_technologies,
            "language": language,
            "file_plan": file_plan,
            "dependencies": {},
            "risks": complexity.risk_factors
        }

    def _ensure_file_plan_completeness(self, architecture: Dict) -> Dict:
        """确保 file_plan 完整性：补充缺失的基础文件和被引用的模块"""
        file_plan = architecture.get("file_plan", [])
        if not file_plan:
            return architecture

        # 检测语言（从 file_plan 中推断）
        from app.agent.adapters import LanguageAdapterRegistry
        files_for_detection = {f["path"]: "" for f in file_plan}
        detected_lang = LanguageAdapterRegistry.detect_language(files_for_detection)
        adapter = LanguageAdapterRegistry.get_adapter(detected_lang)

        logger.info(f"_ensure_file_plan_completeness: 检测到语言={detected_lang}, 适配器={adapter.language}")

        # 提取所有已规划的文件路径
        planned_paths = {f["path"] for f in file_plan}
        # 提取所有被引用的模块
        all_imports = set()
        for f in file_plan:
            imports = f.get("imports", [])
            if isinstance(imports, list):
                all_imports.update(imports)

        # 需要补充的文件
        missing_files = []

        # 1. 检查包入口文件（使用 LanguageAdapter）
        packages = set()
        for f in file_plan:
            path = f["path"]
            # 检测是否是包内的文件
            if "/" in path:
                # 获取文件扩展名
                ext = path.rsplit(".", 1)[-1] if "." in path else ""
                # 排除入口文件本身
                init_file = adapter.get_package_init_file("")
                init_ext = init_file.rsplit(".", 1)[-1] if "." in init_file else ""
                
                if ext == init_ext or not init_ext:
                    # 检查是否是包内的文件（不是入口文件）
                    pkg = path.rsplit("/", 1)[0]
                    if pkg and not path.endswith(init_file.split("/")[-1]):
                        packages.add(pkg)

        for pkg in packages:
            # 使用 LanguageAdapter 获取包入口文件
            init_path = adapter.get_package_init_file(pkg)
            if init_path and init_path not in planned_paths:
                missing_files.append({
                    "path": init_path,
                    "description": f"{pkg} 包初始化文件",
                    "priority": 1,
                    "imports": []
                })
                logger.info(f"自动补充缺失文件: {init_path}")

        # 2. 检查被引用的模块是否存在
        for imp in all_imports:
            # 使用 LanguageAdapter 解析导入路径
            from app.agent.adapters import ImportInfo
            import_info = ImportInfo(module=imp, symbols=[], is_relative=False)
            candidates = adapter.resolve_import_to_file(import_info, "")

            # 检查是否有任何候选路径已规划
            exists = any(c in planned_paths for c in candidates)

            if not exists and candidates:
                # 补充第一个候选路径
                file_path = candidates[0]
                missing_files.append({
                    "path": file_path,
                    "description": f"自动补充的模块文件",
                    "priority": 2,
                    "imports": []
                })
                logger.info(f"自动补充缺失模块: {file_path}")

        # 3. 补充缺失文件到 file_plan
        if missing_files:
            file_plan.extend(missing_files)
            architecture["file_plan"] = file_plan
            logger.info(f"共补充 {len(missing_files)} 个缺失文件")

        return architecture