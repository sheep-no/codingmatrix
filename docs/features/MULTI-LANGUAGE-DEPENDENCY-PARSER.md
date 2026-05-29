# 多语言依赖解析器使用指南

> v5.8.1 新增 | 支持 14 种主流编程语言

## 概述

`app/agent/multi_language_parser.py` 提供了全语言支持的依赖解析能力，能够在项目生成、增量修改、跨文件 Patch 等场景中自动识别并解析不同编程语言的 import/require 语句。

## 支持的语言

| 语言 | 扩展名 | Import 语法 | 示例 |
|------|--------|------------|------|
| **Python** | .py, .pyw | `import x`, `from x import y` | `import os`, `from pathlib import Path` |
| **JavaScript** | .js, .jsx, .mjs, .cjs | `import x from 'y'`, `require('y')` | `import React from 'react'` |
| **TypeScript** | .ts, .tsx | `import x from 'y'`, `require('y')` | `import { useState } from 'react'` |
| **Java** | .java, .groovy | `import package.Class` | `import java.util.List` |
| **Go** | .go | `import "package"` | `import "fmt"` |
| **Rust** | .rs | `use crate::module`, `mod x` | `use std::io::Read` |
| **C/C++** | .c, .cpp, .h, .hpp | `#include <x>`, `#include "x"` | `#include <iostream>` |
| **Ruby** | .rb, .gemspec | `require 'x'`, `include X` | `require 'rails'` |
| **PHP** | .php | `require 'x'`, `use X\Y` | `use Symfony\Component\HttpFoundation\Request` |
| **Swift** | .swift | `import Module` | `import UIKit` |
| **Kotlin** | .kt, .kts | `import package.Class` | `import android.app.Activity` |
| **C#** | .cs | `using Namespace` | `using System.Collections.Generic` |
| **Scala** | .scala | `import package._` | `import scala.collection._` |
| **R** | .R, .r | `library(x)`, `require(x)` | `library(ggplot2)` |

## 快速开始

### 基本使用

```python
from app.agent.multi_language_parser import (
    LanguageDependencyParser,
    parse_file_dependencies,
    detect_file_language
)

# 方式 1: 使用便捷函数
lang = detect_file_language("src/main.py")  # 返回："python"
imports = parse_file_dependencies("src/main.py")  # 返回：{"os.py", "sys.py", ...}

# 方式 2: 使用解析器实例
parser = LanguageDependencyParser()

# 检测语言
lang = parser.detect_language("app/models/user.py")
print(lang)  # 输出："python"

# 解析导入
imports = parser.parse_imports("app/models/user.py", """
import os
from pathlib import Path
from typing import List, Dict
import sqlalchemy as sa
""")
print(imports)  # 输出：{"os.py", "pathlib.py", "typing.py", "sqlalchemy.py"}
```

### 解析不同语言的代码

```python
parser = LanguageDependencyParser()

# Python
py_imports = parser.parse_imports("main.py", """
import numpy as np
from flask import Flask, request
import pandas as pd
""")
print(f"Python: {py_imports}")
# 输出：{'numpy.py', 'flask.py', 'pandas.py'}

# JavaScript/TypeScript
js_imports = parser.parse_imports("App.tsx", """
import React, { useState, useEffect } from 'react'
import { BrowserRouter } from 'react-router-dom'
const lodash = require('lodash')
import('./lazy-module')
""")
print(f"JavaScript: {js_imports}")
# 输出：{'react', 'react-router-dom', 'lodash'}

# Java
java_imports = parser.parse_imports("UserService.java", """
import org.springframework.stereotype.Service;
import java.util.List;
import java.util.Optional;
import com.example.model.User;
""")
print(f"Java: {java_imports}")
# 输出：{'org/springframework/stereotype/Service.java', 'java/util/List.java', ...}

# Go
go_imports = parser.parse_imports("main.go", """
import (
    "fmt"
    "os"
    "github.com/gin-gonic/gin"
)
""")
print(f"Go: {go_imports}")
# 输出：{'fmt', 'os', 'github.com/gin-gonic/gin'}

# Rust
rust_imports = parser.parse_imports("lib.rs", """
use std::io::Read;
use crate::utils::helper;
extern crate serde;
mod models;
""")
print(f"Rust: {rust_imports}")
# 输出：{'std/io/Read.rs', 'crate/utils/helper.rs', 'serde.rs', 'models.rs'}

# C/C++
cpp_imports = parser.parse_imports("main.cpp", """
#include <iostream>
#include <vector>
#include "my_header.h"
""")
print(f"C++: {cpp_imports}")
# 输出：{'iostream', 'vector', 'my_header.h'}
```

## 高级功能

### 1. 批量解析文件

```python
from pathlib import Path

parser = LanguageDependencyParser()
project_root = Path("/path/to/project")

# 解析整个项目
all_imports = {}
for filepath in project_root.rglob("*.py"):
    imports = parser.parse_file(str(filepath))
    if imports:
        all_imports[str(filepath)] = imports

# 输出依赖关系
for file, imports in all_imports.items():
    print(f"{file}:")
    for imp in sorted(imports):
        print(f"  → {imp}")
```

### 2. 语言统计

```python
files = [
    "src/main.py",
    "src/App.tsx",
    "src/utils.js",
    "tests/test_main.py",
    "lib/helper.rb",
]

stats = parser.get_language_stats(files)
print(stats)
# 输出：{'python': 2, 'javascript': 2, 'ruby': 1}
```

### 3. 标准化导入路径

```python
parser = LanguageDependencyParser()

# Python: 点号转斜杠
py_path = parser._normalize_import("os.path.join", "python", "main.py")
print(py_path)  # 输出："os/path/join.py"

# JavaScript: 相对路径处理
js_path = parser._normalize_import("./components/Button", "javascript", "App.tsx")
print(js_path)  # 输出："components/Button.ts" (如果存在)

# Java: 包名转路径
java_path = parser._normalize_import("com.example.UserService", "java", "App.java")
print(java_path)  # 输出："com/example/UserService.java"
```

### 4. 与 DependencyGraph 集成

```python
from app.agent.dependency_graph import DependencyGraph
from app.agent.multi_language_parser import LanguageDependencyParser

# 创建解析器和依赖图
parser = LanguageDependencyParser()
dep_graph = DependencyGraph()

# 解析项目文件
project_files = [
    "src/main.py",
    "src/models/user.py",
    "src/services/user_service.py",
    "src/api/users.py",
]

for filepath in project_files:
    # 添加节点
    dep_graph.add_file(filepath)
    
    # 解析导入并添加依赖
    imports = parser.parse_file(filepath)
    for imp in imports:
        # 将导入映射到项目内文件
        imp_path = parser._normalize_import(imp, "python", filepath)
        dep_graph.add_dependency(filepath, imp_path)

# 获取生成顺序
order = dep_graph.get_generation_order()
print("生成顺序:")
for i, file in enumerate(order, 1):
    print(f"{i}. {file}")
```

### 5. 影响分析

```python
# 假设修改了 models/user.py
changed_file = "models/user.py"

# 找出所有受影响的文件
affected = dep_graph.get_affected_files([changed_file])
print(f"修改 {changed_file} 会影响:")
for file in affected.get(changed_file, []):
    print(f"  → {file}")
```

## 实际应用场景

### 场景 1: 全栈项目生成

项目包含多种语言（后端 Python + 前端 TypeScript）：

```python
parser = LanguageDependencyParser()

# 后端 Python 文件
backend_files = [
    "backend/models/user.py",
    "backend/services/auth.py",
    "backend/api/users.py",
]

# 前端 TypeScript 文件
frontend_files = [
    "frontend/src/types/user.ts",
    "frontend/src/api/users.ts",
    "frontend/src/components/UserList.tsx",
    "frontend/src/pages/UsersPage.tsx",
]

# 解析所有文件
all_imports = {}
for f in backend_files + frontend_files:
    imports = parser.parse_file(f)
    all_imports[f] = imports

# 统计语言分布
stats = parser.get_language_stats(backend_files + frontend_files)
print(stats)  # {'python': 3, 'javascript': 4}
```

### 场景 2: 微服务项目（多语言混合）

```
microservices/
├── user-service/      (Python)
│   ├── main.py
│   └── models.py
├── order-service/     (Go)
│   ├── main.go
│   └── handlers.go
├── notification-svc/  (Node.js)
│   ├── index.js
│   └── sender.js
└── frontend/          (TypeScript)
    └── App.tsx
```

解析器可以自动识别每个服务的语言并正确解析依赖。

### 场景 3: 大规模单体应用

```
monolith/
├── backend/           (Python FastAPI)
├── frontend/          (React + TypeScript)
├── shared/            (TypeScript 类型定义)
├── mobile/            (Kotlin for Android)
└── ios/               (Swift for iOS)
```

解析器支持整个单体应用的依赖分析。

## 高级依赖提取功能

### 1. 阴影依赖扫描 (Shadow Dependencies)

除标准 import/require 语句外，系统还能检测隐式依赖模式：

| 模式 | 描述 | 检测正则 |
|------|------|----------|
| `eval_exec` | eval/exec 动态代码执行 | `\beval\s*\(|\bexec\s*\(` |
| `dynamic_import` | 动态 import (importlib) | `importlib\.import_module` |
| `env_dependency` | 环境变量依赖 | `os\.environ\|os\.getenv` |
| `dynamic_require` | 动态 require (webpack) | `require\.context` |
| `getattr_dynamic` | 反射动态调用 | `getattr\s*\([^,]+,\s*["']` |

```python
from app.agent.dependency_graph import DependencyGraph

dep_graph = DependencyGraph()
shadow_deps = dep_graph.scan_shadow_dependencies(project_path)
# 返回: {'file.py': ['dynamic_import', 'env_dependency']}
```

### 2. 内容反推依赖 (增量场景)

从文件内容提取依赖（无需文件系统）：

```python
deps = dep_graph.extract_dependencies_from_content(
    file_path="src/main.py",
    content="import os\nfrom models import User"
)
```

### 3. 传递依赖分析

获取变更文件的下游影响：

```python
affected = dep_graph.get_affected_files(["models/user.py"])
# 返回: {'models/user.py': ['services/user.py', 'api/users.py']}
```

## 性能优化

### 1. 缓存解析结果

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_parse(filepath: str) -> set:
    return parser.parse_file(filepath)
```

### 2. 并行解析

```python
from concurrent.futures import ThreadPoolExecutor

def parse_all_files(files):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(parser.parse_file, files))
    return results
```

### 3. 增量更新

当文件变更时，只重新解析变更的文件：

```python
def update_dependencies(changed_files):
    for filepath in changed_files:
        new_imports = parser.parse_file(filepath)
        dep_graph.update_file_imports(filepath, new_imports)
```

## 最佳实践

1. **优先使用便捷函数**: 简单场景使用 `parse_file_dependencies()`
2. **批量解析使用实例**: 复杂场景创建 `LanguageDependencyParser` 实例
3. **语言检测先于解析**: 先调用 `detect_language()` 确认支持
4. **标准化路径**: 使用 `_normalize_import()` 转换导入为文件路径
5. **错误处理**: 解析失败时捕获异常，不影响整体流程

## 注意事项

### 1. 文件编码

解析器默认使用 UTF-8 读取文件：

```python
content = Path(filepath).read_text(encoding="utf-8", errors="ignore")
```

### 2. 动态导入

动态导入（如 `import()`）可能无法静态分析，需要运行时信息。

### 3. 条件导入

某些语言支持条件导入（如 `ifdef`），解析器可能无法完全识别。

### 4. 命名空间导入

某些语言的导入语法复杂（如 Python 的相对导入），可能需要额外处理。

## 故障排除

### 问题 1: 无法识别语言

检查文件扩展名是否在 `LANGUAGE_PATTERNS` 中定义：

```python
print(parser.LANGUAGE_PATTERNS.keys())  # 查看支持的语言
```

### 问题 2: 解析结果为空

- 检查文件是否真的包含 import 语句
- 确认注释和字符串已正确移除
- 使用调试模式查看详细日志

### 问题 3: 路径标准化错误

不同项目的目录结构不同，标准化逻辑可能需要调整：

```python
# 自定义标准化逻辑
def custom_normalize(import_path, lang, filepath):
    # 根据项目结构调整
    return custom_path
```

## 扩展新语言

如需添加新语言支持：

```python
new_lang = "newlang"
parser.LANGUAGE_PATTERNS[new_lang] = {
    "extensions": [".nl"],
    "patterns": [
        r'use\s+"([^"]+)"',  # use "module"
    ],
    "comment_regex": r'#.*$',
    "string_regex": r'"[^"]*"',
}
```

然后重新编译正则：

```python
parser._compile_patterns()
```

## 相关文件

- `app/agent/multi_language_parser.py` - 多语言解析器实现
- `app/agent/dependency_graph.py` - 依赖图构建
- `docs/architecture/MODULES.md` - 模块说明文档
- `docs/architecture/ARCHITECTURE.md` - 系统架构文档

---

最后更新：2026-05-23 | v5.8.1
