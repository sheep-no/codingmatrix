"""
JavaScriptLanguageAdapter - JavaScript/TypeScript 语言适配器

处理 JS/TS 特有的：
- 导入语法 (require, import/export)
- 模块结构 (index.js, package.json)
- 文件类型推断
- 符号定义提取
"""

import re
from typing import Dict, List, Optional
from pathlib import Path

from .language_adapter import (
    LanguageAdapter, LanguageAdapterRegistry,
    ImportInfo, SymbolDefinition
)


class JavaScriptLanguageAdapter(LanguageAdapter):
    """JavaScript/TypeScript 语言适配器"""

    language = "javascript"
    extensions = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
    package_init_filename = "index.js"

    # Node.js 内置模块
    NODE_BUILTINS = {
        'fs', 'path', 'os', 'crypto', 'http', 'https', 'net', 'tls',
        'child_process', 'cluster', 'worker_threads', 'events', 'stream',
        'buffer', 'url', 'querystring', 'zlib', 'readline', 'util',
        'assert', 'console', 'process', 'timers', 'dns', 'dgram',
        'perf_hooks', 'async_hooks', 'vm', 'v8', 'inspector',
        'module', 'repl', 'string_decoder', 'punycode',
    }

    # 常见前端框架/库
    COMMON_THIRD_PARTY = {
        'react', 'react-dom', 'react-router', 'react-router-dom',
        'vue', 'vue-router', 'vuex', 'pinia', 'nuxt',
        'angular', '@angular/core', '@angular/common', '@angular/router',
        'svelte', 'sveltekit', 'next', 'next/router',
        'express', 'koa', 'fastify', 'hapi', 'nest', '@nestjs/core',
        'lodash', 'underscore', 'moment', 'dayjs', 'date-fns',
        'axios', 'node-fetch', 'got', 'superagent',
        'mongoose', 'sequelize', 'typeorm', 'prisma', 'knex',
        'jest', 'mocha', 'chai', 'vitest', 'cypress', 'playwright',
        'webpack', 'vite', 'rollup', 'parcel', 'esbuild',
        'tailwindcss', 'bootstrap', 'material-ui', 'antd', 'chakra-ui',
        'zustand', 'redux', 'mobx', 'recoil', 'jotai',
        'graphql', 'apollo', 'urql', 'swr', 'react-query',
        'socket.io', 'ws', 'jsonwebtoken', 'bcrypt',
        'dotenv', 'cors', 'helmet', 'morgan', 'body-parser',
        'typescript', 'babel', 'eslint', 'prettier',
    }

    # 文件路径到类型的映射规则
    PATH_TYPE_RULES = [
        # 配置
        ("package.json", "config"),
        ("tsconfig.json", "config"),
        (".eslintrc", "config"),
        (".prettierrc", "config"),
        ("vite.config", "config"),
        ("webpack.config", "config"),
        ("next.config", "config"),
        ("nuxt.config", "config"),
        (".env", "env"),
        (".env.local", "env"),
        (".env.development", "env"),

        # 入口文件
        ("index.ts", "entrypoint"),
        ("index.js", "entrypoint"),
        ("index.tsx", "entrypoint"),
        ("index.jsx", "entrypoint"),
        ("main.ts", "entrypoint"),
        ("main.js", "entrypoint"),
        ("app.ts", "config"),
        ("app.js", "config"),
        ("server.ts", "config"),
        ("server.js", "config"),

        # 数据库
        ("database", "database"),
        ("db", "database"),
        ("prisma", "database"),
        ("prisma/schema.prisma", "database"),

        # 模型/实体
        ("models", "model"),
        ("model", "model"),
        ("entities", "model"),
        ("entity", "model"),
        ("schemas", "schema"),
        ("schema", "schema"),
        ("types", "types"),
        ("interfaces", "types"),

        # API/Routes
        ("api", "api"),
        ("routes", "api"),
        ("router", "api"),
        ("controllers", "api"),
        ("controller", "api"),
        ("handlers", "api"),
        ("handler", "api"),
        ("endpoints", "api"),

        # 服务
        ("services", "service"),
        ("service", "service"),

        # 中间件
        ("middleware", "middleware"),
        ("middlewares", "middleware"),

        # 工具
        ("utils", "utils"),
        ("util", "utils"),
        ("helpers", "utils"),
        ("lib", "utils"),
        ("common", "utils"),

        # 组件（前端）
        ("components", "component"),
        ("component", "component"),
        ("pages", "page"),
        ("page", "page"),
        ("views", "page"),
        ("layouts", "layout"),
        ("layout", "layout"),

        # 静态资源
        ("public", "static"),
        ("static", "static"),
        ("assets", "assets"),

        # 测试
        ("__tests__", "test"),
        ("tests", "test"),
        ("test", "test"),
        ("spec", "test"),
        (".test.", "test"),
        (".spec.", "test"),

        # 文档
        ("README.md", "readme"),
        ("docs", "docs"),
    ]

    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        """解析 JavaScript/TypeScript 导入语句"""
        imports = []

        if not content:
            return imports

        for line in content.split('\n'):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue

            # ES6 import: import xxx from 'module'
            match = re.match(
                r"^import\s+(?:(\w+)|{([^}]+)}|\*\s+as\s+(\w+))\s+from\s+['\"]([^'\"]+)['\"]",
                stripped
            )
            if match:
                default_import = match.group(1)
                named_imports = match.group(2)
                namespace_import = match.group(3)
                module = match.group(4)

                symbols = []
                if default_import:
                    symbols.append(default_import)
                if named_imports:
                    symbols.extend([s.strip().split(' as ')[-1].strip() for s in named_imports.split(',')])
                if namespace_import:
                    symbols.append(namespace_import)

                is_relative = module.startswith('.')
                imports.append(ImportInfo(
                    module=module,
                    symbols=symbols,
                    is_relative=is_relative,
                    raw_line=stripped
                ))
                continue

            # import 'module' (side effect)
            match = re.match(r"^import\s+['\"]([^'\"]+)['\"]", stripped)
            if match:
                module = match.group(1)
                is_relative = module.startswith('.')
                imports.append(ImportInfo(
                    module=module,
                    symbols=[],
                    is_relative=is_relative,
                    raw_line=stripped
                ))
                continue

            # require: const xxx = require('module')
            match = re.match(r"^(?:const|let|var)\s+(?:{([^}]+)}|(\w+))\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", stripped)
            if match:
                named_imports = match.group(1)
                default_import = match.group(2)
                module = match.group(3)

                symbols = []
                if named_imports:
                    symbols.extend([s.strip().split(' as ')[-1].strip() for s in named_imports.split(',')])
                if default_import:
                    symbols.append(default_import)

                is_relative = module.startswith('.')
                imports.append(ImportInfo(
                    module=module,
                    symbols=symbols,
                    is_relative=is_relative,
                    raw_line=stripped
                ))
                continue

            # Dynamic import: import('module')
            match = re.match(r".*import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", stripped)
            if match:
                module = match.group(1)
                is_relative = module.startswith('.')
                imports.append(ImportInfo(
                    module=module,
                    symbols=[],
                    is_relative=is_relative,
                    raw_line=stripped
                ))
                continue

        return imports

    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        """将导入路径解析为文件路径"""
        candidates = []
        module = import_info.module

        if not module:
            return candidates

        # 相对导入
        if import_info.is_relative:
            current_dir = str(Path(current_file).parent)
            base_path = current_dir if current_dir != '.' else ''

            if base_path:
                base = f"{base_path}/{module}"
            else:
                base = module

            # 尝试多种扩展名
            for ext in ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs']:
                candidates.append(f"{base}{ext}")

            # index 文件
            for ext in ['.js', '.jsx', '.ts', '.tsx']:
                candidates.append(f"{base}/index{ext}")

            return candidates

        # 非相对导入（包或绝对路径）
        # 检查是否是项目内路径（如 @/xxx, src/xxx）
        if module.startswith('@/') or module.startswith('src/'):
            clean_module = module.lstrip('@/')
            for ext in ['.js', '.jsx', '.ts', '.tsx']:
                candidates.append(f"src/{clean_module}{ext}")
                candidates.append(f"src/{clean_module}/index{ext}")

        return candidates

    def infer_file_type(self, file_path: str) -> str:
        """根据文件路径推断文件类型"""
        # 检查路径规则
        for pattern, file_type in self.PATH_TYPE_RULES:
            if pattern.endswith('/'):
                if f"/{pattern}" in f"{file_path}/" or file_path.startswith(pattern):
                    return file_type
            elif pattern.startswith('.'):
                # 扩展名模式如 .test.
                if pattern in file_path:
                    return file_type
            else:
                if f"/{pattern}" in file_path or file_path.startswith(pattern):
                    return file_type

        # 基于目录名的推断
        parts = Path(file_path).parts
        for part in parts:
            part_lower = part.lower()
            if part_lower in ('models', 'model', 'entities', 'entity'):
                return "model"
            elif part_lower in ('api', 'routes', 'controllers', 'handlers'):
                return "api"
            elif part_lower in ('services', 'service'):
                return "service"
            elif part_lower in ('components', 'component'):
                return "component"
            elif part_lower in ('pages', 'views'):
                return "page"
            elif part_lower in ('utils', 'helpers', 'lib'):
                return "utils"
            elif part_lower in ('tests', 'test', '__tests__'):
                return "test"
            elif part_lower in ('hooks', 'composables'):
                return "hook"

        return "unknown"

    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        """提取 JavaScript/TypeScript 文件中的符号定义"""
        definitions = {}
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue

            # 函数定义: function xxx() / async function xxx()
            func_match = re.match(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)', stripped)
            if func_match:
                func_name = func_match.group(1)
                signature = func_match.group(2)
                definitions[func_name] = SymbolDefinition(
                    name=func_name,
                    symbol_type="function",
                    line_number=i,
                    signature=signature,
                    is_exported='export' in stripped
                )
                continue

            # 箭头函数: const xxx = () => / const xxx = async () =>
            arrow_match = re.match(
                r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>',
                stripped
            )
            if arrow_match:
                func_name = arrow_match.group(1)
                definitions[func_name] = SymbolDefinition(
                    name=func_name,
                    symbol_type="function",
                    line_number=i,
                    is_exported='export' in stripped
                )
                continue

            # 类定义: class xxx
            class_match = re.match(r'^(?:export\s+)?(?:default\s+)?class\s+(\w+)', stripped)
            if class_match:
                class_name = class_match.group(1)
                definitions[class_name] = SymbolDefinition(
                    name=class_name,
                    symbol_type="class",
                    line_number=i,
                    is_exported='export' in stripped
                )
                continue

            # 接口定义 (TypeScript): interface xxx
            interface_match = re.match(r'^(?:export\s+)?interface\s+(\w+)', stripped)
            if interface_match:
                interface_name = interface_match.group(1)
                definitions[interface_name] = SymbolDefinition(
                    name=interface_name,
                    symbol_type="interface",
                    line_number=i,
                    is_exported='export' in stripped
                )
                continue

            # 类型定义 (TypeScript): type xxx
            type_match = re.match(r'^(?:export\s+)?type\s+(\w+)', stripped)
            if type_match:
                type_name = type_match.group(1)
                definitions[type_name] = SymbolDefinition(
                    name=type_name,
                    symbol_type="type",
                    line_number=i,
                    is_exported='export' in stripped
                )
                continue

            # export default / export { xxx }
            export_match = re.match(r'^export\s+(?:default\s+)?{([^}]+)}', stripped)
            if export_match:
                symbols = [s.strip().split(' as ')[-1].strip() for s in export_match.group(1).split(',')]
                for symbol in symbols:
                    if symbol:
                        definitions[symbol] = SymbolDefinition(
                            name=symbol,
                            symbol_type="export",
                            line_number=i,
                            is_exported=True
                        )

            # 变量定义（模块级别）
            if not line.startswith(' ') and not line.startswith('\t'):
                var_match = re.match(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=', stripped)
                if var_match:
                    var_name = var_match.group(1)
                    # 跳过箭头函数（已处理）
                    if '=>' not in stripped:
                        definitions[var_name] = SymbolDefinition(
                            name=var_name,
                            symbol_type="variable",
                            line_number=i,
                            is_exported='export' in stripped
                        )

        return definitions

    def get_package_init_file(self, package_path: str) -> str:
        """获取 JS 包的入口文件"""
        # 优先 index.ts，然后 index.js
        return f"{package_path}/index.ts"

    def is_project_module(self, module_name: str) -> bool:
        """判断是否是项目内模块"""
        if not module_name:
            return False

        # 相对导入
        if module_name.startswith('.'):
            return True

        # 别名路径（@/xxx, src/xxx）
        if module_name.startswith('@/') or module_name.startswith('src/'):
            return True

        # Node.js 内置模块
        top_level = module_name.split('/')[0]
        if top_level.startswith('node:') or top_level in self.NODE_BUILTINS:
            return False

        # 第三方库
        if top_level in self.COMMON_THIRD_PARTY or top_level.startswith('@'):
            return False

        return False

    def validate_package_structure(self, package_path: str, files: Dict[str, str]) -> List[str]:
        """验证 JS 模块结构"""
        missing = []

        # 检查是否有入口文件
        index_ts = f"{package_path}/index.ts"
        index_js = f"{package_path}/index.js"

        if index_ts not in files and index_js not in files:
            missing.append(index_ts)  # 默认推荐 TypeScript

        return missing

    def get_required_package_files(self, package_path: str) -> List[str]:
        """获取 JS 包所需的文件"""
        return [
            f"{package_path}/index.ts",
            f"{package_path}/index.js",
        ]


# 注册适配器
LanguageAdapterRegistry.register(JavaScriptLanguageAdapter())
