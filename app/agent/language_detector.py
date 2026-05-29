"""
LanguageDetector - 从需求文本自动推断目标编程语言

检测策略：
1. 显式语言关键词（如"用 Python 写"、"React 项目"）
2. 框架/技术栈推断（如"Spring Boot" → Java，"Express" → Node.js）
3. 文件扩展名提示（如".py 文件"、".go 文件"）
4. 默认 fallback（根据项目类型推断）
"""

import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class LanguageDetectionResult:
    """语言检测结果"""
    language: str                    # 检测到的语言
    confidence: float                # 置信度 0-1
    evidence: List[str]              # 检测依据
    adapter_name: str                # 对应的适配器名
    needs_clarification: bool = False  # 是否需要用户澄清（如未知语言的文件扩展名）


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

        # 策略 1: 显式语言关键词（全局按关键词长度降序匹配，避免短关键词误匹配）
        # 收集所有 (keyword, language) 对
        all_keywords = []
        for lang, keywords in cls.LANGUAGE_KEYWORDS.items():
            for keyword in keywords:
                all_keywords.append((keyword, lang))
        # 按关键词长度降序排列
        all_keywords.sort(key=lambda x: len(x[0]), reverse=True)
        # 遍历匹配
        for keyword, lang in all_keywords:
            # 使用词边界匹配，避免误匹配
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, requirement_lower):
                evidence.append(f"关键词匹配: '{keyword}' → {lang}")
                return LanguageDetectionResult(
                    language=lang,
                    confidence=0.95,
                    evidence=evidence,
                    adapter_name=cls._get_adapter_name(lang)
                )

        # 策略 2: 框架推断
        for framework, lang in cls.FRAMEWORK_LANGUAGE.items():
            pattern = r'\b' + re.escape(framework) + r'\b'
            if re.search(pattern, requirement_lower):
                evidence.append(f"框架推断: '{framework}' → {lang}")
                return LanguageDetectionResult(
                    language=lang,
                    confidence=0.90,
                    evidence=evidence,
                    adapter_name=cls._get_adapter_name(lang)
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
                    adapter_name=cls._get_adapter_name(lang)
                )

        # 策略 4: 项目类型默认值
        if project_type and project_type in cls.PROJECT_TYPE_DEFAULTS:
            lang = cls.PROJECT_TYPE_DEFAULTS[project_type]
            evidence.append(f"项目类型默认: '{project_type}' → {lang}")
            return LanguageDetectionResult(
                language=lang,
                confidence=0.60,
                evidence=evidence,
                adapter_name=cls._get_adapter_name(lang)
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
                        adapter_name=cls._get_adapter_name(potential_lang)
                    )
                # 不在列表中，但看起来像语言名（短且无特殊字符），低置信度
                # 如果在扩展名映射表中有记录，则不需要澄清
                if len(potential_lang) <= 15 and potential_lang.isalnum():
                    has_ext = potential_lang in cls.LANGUAGE_EXTENSION_MAP
                    evidence.append(f"中文模式推断（{'已知' if has_ext else '未知'}语言）: '{match.group(group_idx)}' → {potential_lang}")
                    return LanguageDetectionResult(
                        language=potential_lang,
                        confidence=0.70 if has_ext else 0.40,
                        evidence=evidence,
                        adapter_name="generic",
                        needs_clarification=not has_ext
                    )

        # 默认：Python（最通用）
        evidence.append("未检测到明确语言，使用默认: Python")
        return LanguageDetectionResult(
            language="python",
            confidence=0.30,
            evidence=evidence,
            adapter_name="python"
        )

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
                "test_framework": "根据语言约定",
                "package_manager": "根据语言约定",
                "config_files": [],
                "common_structure": ["请根据语言最佳实践组织代码结构"],
            }

        return rules.get(language, rules["python"])
