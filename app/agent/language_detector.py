"""
LanguageDetector - 从需求文本自动推断目标编程语言

检测策略：
1. 显式语言关键词（如"用 Python 写"、"React 项目"）
2. 框架/技术栈推断（如"Spring Boot" → Java，"Express" → Node.js）
3. 文件扩展名提示（如".py 文件"、".go 文件"）
4. 默认 fallback（根据项目类型推断）
5. LLM 辅助检测（当检测结果可能存在冲突时，使用 LLM 进行上下文感知的语言检测）
"""

import re
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LanguageDetectionResult:
    """语言检测结果"""
    language: str                    # 检测到的语言（主要语言，通常是后端）
    confidence: float                # 置信度 0-1
    evidence: List[str]              # 检测依据
    adapter_name: str                # 对应的适配器名
    needs_clarification: bool = False  # 是否需要用户澄清（如未知语言的文件扩展名）
    frontend_language: Optional[str] = None  # 前端语言（如果检测到）
    backend_language: Optional[str] = None   # 后端语言（如果检测到）
    all_languages: Optional[List[str]] = None  # 项目中所有检测到的语言
    detection_method: str = "rule"   # 检测方法：rule（规则）或 llm（LLM 辅助）


class LanguageDetector:
    """语言检测器"""

    # 语言关键词映射
    LANGUAGE_KEYWORDS: Dict[str, List[str]] = {
        "python": [
            "python", "py", "django", "flask", "fastapi", "uvicorn",
            "sqlalchemy", "pydantic", "pandas", "numpy", "scrapy",
            "celery", "pytest", "pip", "conda", "anaconda",
            "python 3", "python3", "py3",
        ],
        "javascript": [
            "javascript", "js", "node", "nodejs", "node.js",
            "express", "koa", "fastify", "nestjs", "nest.js",
            "react", "vue", "angular", "svelte", "next", "nuxt",
            "webpack", "vite", "rollup", "esbuild",
            "npm", "yarn", "pnpm", "bun",
            "typescript", "ts", "tsx", "jsx",
        ],
        "java": [
            "java", "spring", "springboot", "spring boot",
            "maven", "gradle", "tomcat", "jetty",
            "hibernate", "mybatis", "jpa",
            "jvm", "jdk", "jre",
        ],
        "go": [
            "go", "golang", "gin", "echo", "fiber", "beego",
            "gorilla", "mux", "chi",
            "go mod", "go module",
        ],
        "rust": [
            "rust", "cargo", "crates", "actix", "rocket", "axum",
            "tokio", "serde", "warp",
            "rustc", "rustup",
        ],
        "csharp": [
            "c#", "csharp", "c sharp", ".net", "dotnet",
            "asp.net", "aspnet", "blazor", "maui",
            "visual studio", "nuget",
            "entity framework", "ef core",
        ],
        "php": [
            "php", "laravel", "symfony", "codeigniter", "yii",
            "composer", "wordpress", "drupal", "magento",
        ],
        "ruby": [
            "ruby", "rails", "ruby on rails", "sinatra",
            "gem", "bundler", "rake",
        ],
        "swift": [
            "swift", "ios", "xcode", "cocoapods", "swiftui",
            "uikit", "foundation",
        ],
        "kotlin": [
            "kotlin", "android", "jetpack", "compose",
            "ktor", "exposed",
        ],
        "dart": [
            "dart", "flutter", "pub",
        ],
        "elixir": [
            "elixir", "phoenix", "mix",
        ],
        "haskell": [
            "haskell", "ghc", "cabal", "stack",
        ],
        "scala": [
            "scala", "akka", "play framework", "sbt",
        ],
        "r": [
            " r ", "r语言", "r语言", "rstudio", "shiny", "ggplot",
        ],
        "lua": [
            "lua", "luajit", "openresty", "nginx lua",
        ],
        "perl": [
            "perl", "cpan",
        ],
            "易语言": [
            "易语言", "e语言", "ec", "易程序",
        ],
        "renpy": [
            "ren'py", "renpy", "galgame", "视觉小说", "visual novel",
            ".rpy", "rpy文件",
        ],
    }

    # 通用语言扩展名映射（不常见但已知的语言）
    LANGUAGE_EXTENSION_MAP: Dict[str, str] = {
        "renpy": ".rpy",
        "lua": ".lua",
        "perl": ".pl",
        "elixir": ".ex",
        "haskell": ".hs",
        "scala": ".scala",
        "dart": ".dart",
        "swift": ".swift",
        "kotlin": ".kt",
        "rust": ".rs",
        "go": ".go",
        "ruby": ".rb",
        "php": ".php",
        "r": ".r",
        "zig": ".zig",
        "nim": ".nim",
        "crystal": ".cr",
        "odin": ".odin",
        "jai": ".jai",
        "v": ".v",
        "vale": ".vale",
        "gleam": ".gleam",
        "roc": ".roc",
    }

    # 框架 → 语言的强映射
    FRAMEWORK_LANGUAGE: Dict[str, str] = {
        "django": "python",
        "flask": "python",
        "fastapi": "python",
        "express": "javascript",
        "koa": "javascript",
        "react": "javascript",
        "vue": "javascript",
        "angular": "javascript",
        "next": "javascript",
        "nuxt": "javascript",
        "spring": "java",
        "springboot": "java",
        "hibernate": "java",
        "gin": "go",
        "echo": "go",
        "actix": "rust",
        "rocket": "rust",
        "laravel": "php",
        "symfony": "php",
        "rails": "ruby",
        "phoenix": "elixir",
        "flutter": "dart",
    }

    # 项目类型 → 默认语言
    PROJECT_TYPE_DEFAULTS: Dict[str, str] = {
        "web_frontend": "javascript",
        "web_backend": "python",
        "api": "python",
        "cli": "python",
        "mobile": "kotlin",
        "desktop": "javascript",
        "data_science": "python",
        "machine_learning": "python",
        "game": "csharp",
        "embedded": "rust",
        "system": "rust",
    }

    # 前端专用关键词（用于区分前端和后端技术栈）
    FRONTEND_KEYWORDS: List[str] = [
        "react", "vue", "angular", "svelte", "next", "nuxt",
        "webpack", "vite", "rollup", "esbuild",
        "html", "css", "dom", "browser",
        "前端", "frontend", "front-end",
        "原生 javascript", "vanilla javascript",
    ]

    # 后端专用关键词（用于区分前端和后端技术栈）
    BACKEND_KEYWORDS: List[str] = [
        "django", "flask", "fastapi", "uvicorn",
        "express", "koa", "fastify", "nestjs",
        "spring", "springboot", "hibernate",
        "gin", "echo", "fiber",
        "后端", "backend", "back-end",
        "api", "rest", "graphql",
        "数据库", "database", "sql", "mysql", "postgresql", "sqlite",
    ]

    @classmethod
    def detect(cls, requirement: str, project_type: Optional[str] = None) -> LanguageDetectionResult:
        """
        从需求文本检测目标语言

        Args:
            requirement: 需求描述文本
            project_type: 项目类型（可选，用于 fallback）

        Returns:
            LanguageDetectionResult
        """
        requirement_lower = requirement.lower()
        evidence = []

        # 策略 0: 检查是否是全栈项目（前端 + 后端不同语言）
        is_fullstack, frontend_lang, backend_lang = cls._detect_fullstack_languages(requirement_lower)
        if is_fullstack:
            evidence.append(f"全栈项目检测: 前端={frontend_lang}, 后端={backend_lang}")

        # 检测所有出现的语言（用于多语言项目，如 Python + Rust）
        all_detected_langs = cls._detect_all_languages(requirement_lower)
        if len(all_detected_langs) > 1:
            evidence.append(f"多语言检测: {all_detected_langs}")

        # 策略 1: 框架推断（优先于通用语言关键词，因为框架更明确）
        for framework, lang in cls.FRAMEWORK_LANGUAGE.items():
            pattern = r'\b' + re.escape(framework) + r'\b'
            if re.search(pattern, requirement_lower):
                evidence.append(f"框架推断: '{framework}' → {lang}")
                result = LanguageDetectionResult(
                    language=lang,
                    confidence=0.95,
                    evidence=evidence,
                    adapter_name=cls._get_adapter_name(lang),
                    frontend_language=frontend_lang,
                    backend_language=backend_lang or lang,
                    all_languages=all_detected_langs if all_detected_langs else [lang],
                )
                return result

        # 策略 2: 显式语言关键词（全局按关键词长度降序匹配，避免短关键词误匹配）
        # 收集所有 (keyword, language) 对
        all_keywords = []
        for lang, keywords in cls.LANGUAGE_KEYWORDS.items():
            for keyword in keywords:
                all_keywords.append((keyword, lang))
        # 按关键词长度降序排列
        all_keywords.sort(key=lambda x: len(x[0]), reverse=True)
        # 遍历匹配
        for keyword, lang in all_keywords:
            # 处理以点开头的关键词（如 .rpy）
            if keyword.startswith('.'):
                # 对于以点开头的关键词，使用特殊模式：前面是空格或字符串开头
                pattern = r'(?:^|\s)' + re.escape(keyword) + r'(?:\s|$|，|。|,|\.)'
            else:
                # 使用词边界匹配，避免误匹配
                pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, requirement_lower):
                evidence.append(f"关键词匹配: '{keyword}' → {lang}")
                # 检查是否有冲突（需求中同时提到了其他语言的框架）
                # 仅用于日志记录，不改变检测结果
                conflict = cls._check_language_conflict(requirement_lower, lang)
                if conflict:
                    evidence.append(f"检测到冲突（已忽略）: {conflict}")
                return LanguageDetectionResult(
                    language=lang,
                    confidence=0.95,
                    evidence=evidence,
                    adapter_name=cls._get_adapter_name(lang),
                    frontend_language=frontend_lang,
                    backend_language=backend_lang or lang,
                    all_languages=all_detected_langs if all_detected_langs else [lang],
                )

        # 策略 3: 文件扩展名
        ext_matches = re.findall(r'\.(\w+)(?:\s|，|。|,|\.|$)', requirement)
        ext_language_map = {
            'py': 'python', 'pyw': 'python',
            'js': 'javascript', 'jsx': 'javascript',
            'ts': 'javascript', 'tsx': 'javascript',
            'java': 'java',
            'go': 'go',
            'rs': 'rust',
            'cs': 'csharp',
            'php': 'php',
            'rb': 'ruby',
            'swift': 'swift',
            'kt': 'kotlin',
            'dart': 'dart',
            'ex': 'elixir',
            'hs': 'haskell',
            'scala': 'scala',
            'r': 'r',
            'lua': 'lua',
            'pl': 'perl',
        }
        for ext in ext_matches:
            if ext in ext_language_map:
                lang = ext_language_map[ext]
                evidence.append(f"扩展名推断: '.{ext}' → {lang}")
                return LanguageDetectionResult(
                    language=lang,
                    confidence=0.85,
                    evidence=evidence,
                    adapter_name=cls._get_adapter_name(lang),
                    frontend_language=frontend_lang,
                    backend_language=backend_lang or lang,
                    all_languages=all_detected_langs if all_detected_langs else [lang],
                )

        # 策略 4: 项目类型默认值
        if project_type and project_type in cls.PROJECT_TYPE_DEFAULTS:
            lang = cls.PROJECT_TYPE_DEFAULTS[project_type]
            evidence.append(f"项目类型默认: '{project_type}' → {lang}")
            return LanguageDetectionResult(
                language=lang,
                confidence=0.60,
                evidence=evidence,
                adapter_name=cls._get_adapter_name(lang),
                frontend_language=frontend_lang,
                backend_language=backend_lang or lang,
                all_languages=all_detected_langs if all_detected_langs else [lang],
            )

        # 策略 5: 中文需求的常见模式
        chinese_patterns = [
            (r'用\s*([\w]+)\s*写', 1),
            (r'用\s*([\w]+)\s*开发', 1),
            (r'使用\s*([\w]+)\s*开发', 1),
            (r'基于\s*([\w]+)\s*的', 1),
            (r'([\w]+)\s*项目', 1),
            (r'([\w]+)\s*应用', 1),
            (r'([\w]+)\s*程序', 1),
        ]
        for pattern, group_idx in chinese_patterns:
            match = re.search(pattern, requirement)
            if match:
                potential_lang = match.group(group_idx).lower()
                # 在已知语言列表中，高置信度
                if potential_lang in cls.LANGUAGE_KEYWORDS:
                    evidence.append(f"中文模式推断: '{match.group(group_idx)}' → {potential_lang}")
                    return LanguageDetectionResult(
                        language=potential_lang,
                        confidence=0.70,
                        evidence=evidence,
                        adapter_name=cls._get_adapter_name(potential_lang),
                        frontend_language=frontend_lang,
                        backend_language=backend_lang or potential_lang,
                        all_languages=all_detected_langs if all_detected_langs else [potential_lang],
                    )
                # 不在列表中，但看起来像语言名（短且仅含 ASCII 字母数字），低置信度
                # 如果在扩展名映射表中有记录，则不需要澄清
                # 注意：必须检查是否为 ASCII，因为中文字符的 isalnum() 也返回 True
                if len(potential_lang) <= 15 and potential_lang.isascii() and potential_lang.isalnum():
                    has_ext = potential_lang in cls.LANGUAGE_EXTENSION_MAP
                    evidence.append(f"中文模式推断（{'已知' if has_ext else '未知'}语言）: '{match.group(group_idx)}' → {potential_lang}")
                    return LanguageDetectionResult(
                        language=potential_lang,
                        confidence=0.70 if has_ext else 0.40,
                        evidence=evidence,
                        adapter_name="generic",
                        needs_clarification=not has_ext,
                        frontend_language=frontend_lang,
                        backend_language=backend_lang or potential_lang,
                        all_languages=all_detected_langs if all_detected_langs else [potential_lang],
                    )

        # 默认：Python（最通用）
        evidence.append("未检测到明确语言，使用默认: Python")
        return LanguageDetectionResult(
            language="python",
            confidence=0.30,
            evidence=evidence,
            adapter_name="python",
            frontend_language=frontend_lang,
            backend_language=backend_lang,
            all_languages=all_detected_langs if all_detected_langs else ["python"],
        )

    @classmethod
    def _detect_fullstack_languages(cls, requirement_lower: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        检测是否是全栈项目（前端 + 后端使用不同语言）

        Returns:
            (is_fullstack, frontend_lang, backend_lang)
        """
        frontend_lang = None
        backend_lang = None

        # 检测前端语言
        for keyword in cls.FRONTEND_KEYWORDS:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, requirement_lower):
                # 根据关键词推断前端语言
                if keyword in ["react", "vue", "angular", "svelte", "next", "nuxt"]:
                    frontend_lang = "javascript"
                    break
                elif keyword in ["html", "css", "dom", "browser", "原生 javascript", "vanilla javascript"]:
                    frontend_lang = "javascript"
                    break

        # 检测后端语言
        for keyword in cls.BACKEND_KEYWORDS:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, requirement_lower):
                # 根据关键词推断后端语言
                if keyword in ["django", "flask", "fastapi", "uvicorn"]:
                    backend_lang = "python"
                    break
                elif keyword in ["express", "koa", "fastify", "nestjs"]:
                    backend_lang = "javascript"
                    break
                elif keyword in ["spring", "springboot", "hibernate"]:
                    backend_lang = "java"
                    break
                elif keyword in ["gin", "echo", "fiber"]:
                    backend_lang = "go"
                    break

        # 如果前端和后端语言不同，认为是全栈项目
        if frontend_lang and backend_lang and frontend_lang != backend_lang:
            return True, frontend_lang, backend_lang

        return False, frontend_lang, backend_lang

    @classmethod
    def _detect_all_languages(cls, requirement_lower: str) -> List[str]:
        """
        检测需求中提到的所有编程语言（用于多语言项目）

        例如："Python 后端 + Rust 性能模块" → ["python", "rust"]

        Returns:
            检测到的语言列表（去重，保持顺序）
        """
        detected = []

        # 通过框架推断
        for framework, lang in cls.FRAMEWORK_LANGUAGE.items():
            pattern = r'\b' + re.escape(framework) + r'\b'
            if re.search(pattern, requirement_lower) and lang not in detected:
                detected.append(lang)

        # 通过语言关键词推断
        all_keywords = []
        for lang, keywords in cls.LANGUAGE_KEYWORDS.items():
            for keyword in keywords:
                all_keywords.append((keyword, lang))
        all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

        for keyword, lang in all_keywords:
            if keyword.startswith('.'):
                pattern = r'(?:^|\s)' + re.escape(keyword) + r'(?:\s|$|，|。|,|\.)'
            else:
                pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, requirement_lower) and lang not in detected:
                detected.append(lang)

        return detected

    @classmethod
    def _check_language_conflict(cls, requirement_lower: str, detected_lang: str) -> Optional[str]:
        """
        检查是否存在语言冲突（需求中提到了其他语言的框架）

        Returns:
            冲突描述，如果没有冲突则返回 None
        """
        # 检查是否有其他语言的框架被提及
        for framework, lang in cls.FRAMEWORK_LANGUAGE.items():
            if lang == detected_lang:
                continue
            pattern = r'\b' + re.escape(framework) + r'\b'
            if re.search(pattern, requirement_lower):
                return f"检测到 {detected_lang}，但需求中也提到了 {framework}（{lang}）"

        # 检查是否有其他语言的关键词被提及
        for lang, keywords in cls.LANGUAGE_KEYWORDS.items():
            if lang == detected_lang:
                continue
            for keyword in keywords:
                # 跳过太短的关键词，避免误匹配
                if len(keyword) <= 2:
                    continue
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, requirement_lower):
                    return f"检测到 {detected_lang}，但需求中也提到了 {keyword}（{lang}）"

        return None

    @classmethod
    def _detect_with_llm_sync(cls, requirement: str, evidence: List[str]) -> Optional[LanguageDetectionResult]:
        """
        使用 LLM 进行上下文感知的语言检测（同步版本）

        Args:
            requirement: 需求描述文本
            evidence: 已有的检测依据

        Returns:
            LanguageDetectionResult 或 None（如果 LLM 检测失败）
        """
        import asyncio
        try:
            # 尝试获取事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在异步上下文中，创建一个任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        cls._detect_with_llm(requirement, evidence)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(cls._detect_with_llm(requirement, evidence))
        except Exception as e:
            logger.warning(f"LLM 辅助语言检测失败: {e}")
            return None

    @classmethod
    async def _detect_with_llm(cls, requirement: str, evidence: List[str]) -> Optional[LanguageDetectionResult]:
        """
        使用 LLM 进行上下文感知的语言检测

        Args:
            requirement: 需求描述文本
            evidence: 已有的检测依据

        Returns:
            LanguageDetectionResult 或 None（如果 LLM 检测失败）
        """
        try:
            from app.utils import call_llm

            prompt = f"""请分析以下需求文本，确定项目应该使用的主要编程语言和技术栈。

需求文本：
{requirement}

请按照以下格式回答（只回答 JSON，不要有其他文字）：

{{
  "primary_language": "主要编程语言（用于生成代码文件）",
  "frontend_language": "前端语言（如果有前端）或 null",
  "backend_language": "后端语言（如果有后端）或 null",
  "reasoning": "选择该语言的原因"
}}

注意：
1. 如果需求明确指定了技术栈（如 "Python Flask"、"JavaScript Express"），请优先遵循需求指定的技术栈
2. 区分前端和后端技术栈，前端可能使用 JavaScript/TypeScript，后端可能使用 Python/Go/Java 等
3. primary_language 应该是需要生成代码的主要语言（通常是后端语言）
4. 如果需求没有明确指定，默认使用 Python"""

            response = await call_llm(prompt, "你是一个编程语言检测专家，擅长从需求文本中识别应该使用的技术栈。")

            if not response or not response.strip():
                return None

            # 解析 JSON 响应
            import json
            try:
                # 尝试提取 JSON
                json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(response)
            except json.JSONDecodeError:
                logger.warning(f"LLM 响应不是有效的 JSON: {response[:200]}")
                return None

            primary_lang = result.get("primary_language", "").lower()
            frontend_lang = result.get("frontend_language")
            backend_lang = result.get("backend_language")
            reasoning = result.get("reasoning", "")

            # 验证语言是否有效
            valid_languages = list(cls.LANGUAGE_KEYWORDS.keys())
            if primary_lang not in valid_languages:
                # 尝试映射常见的别名
                lang_aliases = {
                    "py": "python",
                    "js": "javascript",
                    "ts": "typescript",
                    "node": "javascript",
                    "nodejs": "javascript",
                }
                primary_lang = lang_aliases.get(primary_lang, primary_lang)

            if primary_lang not in valid_languages:
                logger.warning(f"LLM 返回的语言不在已知列表中: {primary_lang}")
                return None

            evidence.append(f"LLM 检测: {primary_lang} (原因: {reasoning})")

            return LanguageDetectionResult(
                language=primary_lang,
                confidence=0.90,
                evidence=evidence,
                adapter_name=cls._get_adapter_name(primary_lang),
                frontend_language=frontend_lang,
                backend_language=backend_lang or primary_lang,
                detection_method="llm"
            )

        except Exception as e:
            logger.warning(f"LLM 辅助语言检测异常: {e}")
            return None

    @classmethod
    def _get_adapter_name(cls, language: str) -> str:
        """获取语言对应的适配器名"""
        adapter_map = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "javascript",  # TypeScript 使用 JS 适配器
            "java": "generic",
            "go": "generic",
            "rust": "generic",
            "csharp": "generic",
            "php": "generic",
            "ruby": "generic",
            "swift": "generic",
            "kotlin": "generic",
            "dart": "generic",
            "elixir": "generic",
            "haskell": "generic",
            "scala": "generic",
            "r": "generic",
            "lua": "generic",
            "perl": "generic",
            "易语言": "generic",
            "renpy": "generic",
        }
        return adapter_map.get(language, "generic")

    @classmethod
    def get_language_specific_rules(cls, language: str) -> Dict:
        """获取语言特定的规则（用于 Architect prompt）"""
        rules = {
            "python": {
                "file_extension": ".py",
                "package_init": "__init__.py",
                "import_syntax": "from xxx import yyy / import xxx",
                "entry_point": "main.py 或 app.py",
                "default_framework": "FastAPI",
                "test_framework": "pytest",
                "package_manager": "pip",
                "config_files": ["requirements.txt", "pyproject.toml", "setup.py"],
                "common_structure": [
                    "app/ 或 src/ - 源代码目录",
                    "tests/ - 测试目录",
                    "models.py - 数据模型",
                    "database.py - 数据库配置",
                    "routers.py 或 views.py - API 路由",
                ],
            },
            "javascript": {
                "file_extension": ".ts / .js",
                "package_init": "index.ts / index.js",
                "import_syntax": "import xxx from 'yyy' / const xxx = require('yyy')",
                "entry_point": "src/index.ts 或 src/main.ts",
                "default_framework": "Express.js",
                "test_framework": "jest / vitest",
                "package_manager": "npm / yarn / pnpm",
                "config_files": ["package.json", "tsconfig.json", "vite.config.ts"],
                "common_structure": [
                    "src/ - 源代码目录",
                    "src/models/ - 数据模型",
                    "src/controllers/ - 控制器",
                    "src/routes/ - 路由",
                    "src/services/ - 服务",
                    "src/utils/ - 工具函数",
                    "tests/ - 测试目录",
                ],
            },
            "go": {
                "file_extension": ".go",
                "package_init": "同目录下任意 .go 文件（package 声明）",
                "import_syntax": "import \"xxx\"",
                "entry_point": "main.go",
                "default_framework": "Gin",
                "test_framework": "testing (标准库)",
                "package_manager": "go mod",
                "config_files": ["go.mod", "go.sum"],
                "common_structure": [
                    "cmd/ - 入口程序",
                    "internal/ - 内部包",
                    "pkg/ - 可导出的包",
                    "api/ - API 定义",
                    "models/ - 数据模型",
                    "handlers/ - 请求处理",
                ],
            },
            "java": {
                "file_extension": ".java",
                "package_init": "同目录下任意 .java 文件（package 声明）",
                "import_syntax": "import xxx.yyy;",
                "entry_point": "Main.java 或 Application.java",
                "default_framework": "Spring Boot",
                "test_framework": "JUnit",
                "package_manager": "Maven / Gradle",
                "config_files": ["pom.xml", "build.gradle", "settings.gradle"],
                "common_structure": [
                    "src/main/java/ - 源代码",
                    "src/test/java/ - 测试",
                    "com.example.project - 包结构",
                    "model/ - 数据模型",
                    "service/ - 服务层",
                    "controller/ - 控制器",
                    "repository/ - 数据访问",
                ],
            },
            "rust": {
                "file_extension": ".rs",
                "package_init": "mod.rs 或同目录文件",
                "import_syntax": "use xxx::yyy;",
                "entry_point": "src/main.rs",
                "default_framework": "Actix-web",
                "test_framework": "cargo test (内置)",
                "package_manager": "cargo",
                "config_files": ["Cargo.toml", "Cargo.lock"],
                "common_structure": [
                    "src/ - 源代码",
                    "src/main.rs - 入口",
                    "src/lib.rs - 库入口",
                    "src/models/ - 数据模型",
                    "src/handlers/ - 请求处理",
                    "tests/ - 集成测试",
                ],
            },
        }

        # 对于没有专门适配器的语言，使用通用规则
        if language not in rules:
            ext = cls.LANGUAGE_EXTENSION_MAP.get(language)
            # 如果扩展名不在映射表中，返回需要澄清的标志
            if ext is None:
                return {
                    "file_extension": None,  # 需要用户指定
                    "package_init": "",
                    "import_syntax": "根据语言约定",
                    "entry_point": None,
                    "test_framework": "根据语言约定",
                    "package_manager": "根据语言约定",
                    "config_files": [],
                    "common_structure": ["请根据语言最佳实践组织代码结构"],
                    "needs_clarification": True,
                }
            return {
                "file_extension": ext,
                "package_init": "",
                "import_syntax": "根据语言约定",
                "entry_point": f"main{ext}",
                "default_framework": None,
                "test_framework": "根据语言约定",
                "package_manager": "根据语言约定",
                "config_files": [],
                "common_structure": ["请根据语言最佳实践组织代码结构"],
            }

        return rules.get(language, rules["python"])
