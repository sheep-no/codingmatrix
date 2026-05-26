"""
Multi-Language Dependency Parser 单元测试

测试覆盖：
- 14 种编程语言的 import 解析
- 语言检测
- 路径标准化
- 注释和字符串处理
- 边界情况
"""
import pytest
from pathlib import Path
from app.agent.multi_language_parser import (
    LanguageDependencyParser,
    parse_file_dependencies,
    detect_file_language,
    get_parser,
)


class TestLanguageDetection:
    """语言检测测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    @pytest.mark.parametrize("filepath,expected_lang", [
        # Python
        ("main.py", "python"),
        ("app/models/user.py", "python"),
        ("script.pyw", "python"),
        
        # JavaScript/TypeScript
        ("App.js", "javascript"),
        ("component.jsx", "javascript"),
        ("utils.ts", "javascript"),
        ("Component.tsx", "javascript"),
        ("module.mjs", "javascript"),
        ("config.cjs", "javascript"),
        
        # Java
        ("UserService.java", "java"),
        ("App.groovy", "java"),
        
        # Go
        ("main.go", "go"),
        
        # Rust
        ("lib.rs", "rust"),
        
        # C/C++
        ("main.c", "cpp"),
        ("app.cpp", "cpp"),
        ("header.h", "cpp"),
        ("impl.hpp", "cpp"),
        
        # Ruby
        ("app.rb", "ruby"),
        ("gem.gemspec", "ruby"),
        
        # PHP
        ("index.php", "php"),
        
        # Swift
        ("AppDelegate.swift", "swift"),
        
        # Kotlin
        ("Main.kt", "kotlin"),
        ("script.kts", "kotlin"),
        
        # C#
        ("Program.cs", "csharp"),
        
        # Scala
        ("App.scala", "scala"),
        
        # R
        ("analysis.R", "r"),
        ("script.r", "r"),
    ])
    def test_detect_language(self, filepath, expected_lang):
        """测试语言检测"""
        lang = self.parser.detect_language(filepath)
        assert lang == expected_lang, f"Expected {expected_lang}, got {lang}"
    
    def test_unsupported_language(self):
        """测试不支持的语言"""
        lang = self.parser.detect_language("file.unknown")
        assert lang is None
    
    def test_get_language_stats(self):
        """测试语言统计"""
        files = [
            "src/main.py",
            "src/App.tsx",
            "src/utils.js",
            "tests/test_main.py",
            "lib/helper.rb",
        ]
        stats = self.parser.get_language_stats(files)
        
        assert stats["python"] == 2
        assert stats["javascript"] == 2
        assert stats["ruby"] == 1


class TestPythonParser:
    """Python 解析测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_simple_import(self):
        """测试简单 import"""
        code = "import os"
        imports = self.parser.parse_imports("test.py", code)
        assert "os.py" in imports
    
    def test_from_import(self):
        """测试 from ... import"""
        code = "from pathlib import Path"
        imports = self.parser.parse_imports("test.py", code)
        assert "pathlib.py" in imports
    
    def test_multiple_imports(self):
        """测试多个导入"""
        code = """
import os
import sys
from pathlib import Path
from typing import List, Dict
import numpy as np
"""
        imports = self.parser.parse_imports("test.py", code)
        assert len(imports) == 5
        assert "os.py" in imports
        assert "sys.py" in imports
        assert "pathlib.py" in imports
        assert "typing.py" in imports
        assert "numpy.py" in imports
    
    def test_skip_comments(self):
        """测试跳过注释"""
        code = """
# import os
import sys  # This is a comment
"""
        imports = self.parser.parse_imports("test.py", code)
        assert "os.py" not in imports
        assert "sys.py" in imports
    
    def test_skip_strings(self):
        """测试跳过字符串"""
        code = '''
import sys
comment = "import os"
'''
        imports = self.parser.parse_imports("test.py", code)
        assert "os.py" not in imports
        assert "sys.py" in imports
    
    def test_multiline_strings(self):
        """测试多行字符串"""
        code = '''
import sys
doc = """
This is a docstring mentioning import os
"""
'''
        imports = self.parser.parse_imports("test.py", code)
        assert "sys.py" in imports
        # 字符串中的 import 不应被解析
        assert len(imports) == 1


class TestJavaScriptParser:
    """JavaScript/TypeScript 解析测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_es6_import(self):
        """测试 ES6 import"""
        code = "import React from 'react'"
        imports = self.parser.parse_imports("test.js", code)
        assert "react.js" in imports
    
    def test_destructuring_import(self):
        """测试解构导入"""
        code = "import { useState, useEffect } from 'react'"
        imports = self.parser.parse_imports("test.js", code)
        assert "react.js" in imports
    
    def test_require(self):
        """测试 require"""
        code = "const lodash = require('lodash')"
        imports = self.parser.parse_imports("test.js", code)
        assert "lodash.js" in imports
    
    def test_dynamic_import(self):
        """测试动态导入"""
        code = "import('./lazy-module')"
        imports = self.parser.parse_imports("test.js", code)
        assert "lazy-module.js" in imports
    
    def test_side_effect_import(self):
        """测试副作用导入"""
        code = "import 'polyfill'"
        imports = self.parser.parse_imports("test.js", code)
        assert "polyfill.js" in imports
    
    def test_typescript(self):
        """测试 TypeScript"""
        code = """
import React from 'react'
import { useState } from 'react'
import type { User } from './types'
"""
        imports = self.parser.parse_imports("App.tsx", code)
        assert "react.js" in imports
        assert "types.js" in imports


class TestJavaParser:
    """Java 解析测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_simple_import(self):
        """测试简单 import"""
        code = "import java.util.List;"
        imports = self.parser.parse_imports("Test.java", code)
        assert "java/util/List.java" in imports
    
    def test_static_import(self):
        """测试 static import"""
        code = "import static java.lang.Math.PI;"
        imports = self.parser.parse_imports("Test.java", code)
        # static import 会被解析
        assert len(imports) >= 1
    
    def test_wildcard_import(self):
        """测试通配符导入"""
        code = "import java.util.*;"
        imports = self.parser.parse_imports("Test.java", code)
        assert "java/util/.java" in imports
    
    def test_multiple_imports(self):
        """测试多个导入"""
        code = """
import org.springframework.stereotype.Service;
import java.util.List;
import java.util.ArrayList;
import com.example.model.User;
"""
        imports = self.parser.parse_imports("UserService.java", code)
        assert len(imports) >= 3


class TestGoParser:
    """Go 解析测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_single_import(self):
        """测试单行 import"""
        code = 'import "fmt"'
        imports = self.parser.parse_imports("main.go", code)
        assert "fmt" in imports
    
    def test_multi_import(self):
        """测试多行 import"""
        code = '''
import (
    "fmt"
    "os"
    "github.com/gin-gonic/gin"
)
'''
        imports = self.parser.parse_imports("main.go", code)
        assert "fmt" in imports
        assert "os" in imports
        assert "github/com/gin-gonic/gin" in imports


class TestRustParser:
    """Rust 解析测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_use_statement(self):
        """测试 use 语句"""
        code = "use std::io::Read;"
        imports = self.parser.parse_imports("lib.rs", code)
        assert "std/io/Read.rs" in imports
    
    def test_extern_crate(self):
        """测试 extern crate"""
        code = "extern crate serde;"
        imports = self.parser.parse_imports("lib.rs", code)
        assert "serde.rs" in imports
    
    def test_mod_statement(self):
        """测试 mod 语句"""
        code = "mod models;"
        imports = self.parser.parse_imports("lib.rs", code)
        assert "models.rs" in imports


class TestCppParser:
    """C/C++ 解析测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_system_include(self):
        """测试系统头文件"""
        code = "#include <iostream>"
        imports = self.parser.parse_imports("main.cpp", code)
        assert "iostream" in imports
    
    def test_local_include(self):
        """测试本地头文件"""
        code = '#include "my_header.h"'
        imports = self.parser.parse_imports("main.cpp", code)
        assert "my_header.h" in imports
    
    def test_multiple_includes(self):
        """测试多个 include"""
        code = """
#include <iostream>
#include <vector>
#include <memory>
#include "my_class.h"
"""
        imports = self.parser.parse_imports("main.cpp", code)
        assert len(imports) == 4


class TestOtherLanguages:
    """其他语言测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_ruby_require(self):
        """测试 Ruby require"""
        code = "require 'rails'"
        imports = self.parser.parse_imports("app.rb", code)
        assert "rails.rb" in imports
    
    def test_php_use(self):
        """测试 PHP use"""
        code = "use Symfony\\Component\\HttpFoundation\\Request;"
        imports = self.parser.parse_imports("Controller.php", code)
        assert "Symfony/Component/HttpFoundation/Request.php" in imports
    
    def test_swift_import(self):
        """测试 Swift import"""
        code = "import UIKit"
        imports = self.parser.parse_imports("AppDelegate.swift", code)
        assert "UIKit" in imports
    
    def test_kotlin_import(self):
        """测试 Kotlin import"""
        code = "import android.app.Activity"
        imports = self.parser.parse_imports("Main.kt", code)
        assert "android.app.Activity" in imports
    
    def test_csharp_using(self):
        """测试 C# using"""
        code = "using System;"
        imports = self.parser.parse_imports("Program.cs", code)
        assert "System" in imports
    
    def test_scala_import(self):
        """测试 Scala import"""
        code = "import scala.collection._"
        imports = self.parser.parse_imports("App.scala", code)
        assert "scala.collection._" in imports
    
    def test_r_library(self):
        """测试 R library"""
        code = "library(ggplot2)"
        imports = self.parser.parse_imports("analysis.R", code)
        assert "ggplot2" in imports


class TestPathNormalization:
    """路径标准化测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_python_normalization(self):
        """测试 Python 路径标准化"""
        result = self.parser._normalize_import("os.path.join", "python", "main.py")
        assert result == "os/path/join.py"
    
    def test_java_normalization(self):
        """测试 Java 路径标准化"""
        result = self.parser._normalize_import("com.example.UserService", "java", "App.java")
        assert result == "com/example/UserService.java"
    
    def test_rust_normalization(self):
        """测试 Rust 路径标准化"""
        result = self.parser._normalize_import("std::io::Read", "rust", "lib.rs")
        assert result == "std/io/Read.rs"
    
    def test_php_normalization(self):
        """测试 PHP 路径标准化"""
        result = self.parser._normalize_import("Symfony\\Component\\Request", "php", "Controller.php")
        assert result == "Symfony/Component/Request.php"
    
    def test_unknown_language(self):
        """测试未知语言"""
        result = self.parser._normalize_import("module", "unknown", "file.unknown")
        assert result == "module"


class TestGlobalParser:
    """全局解析器测试"""
    
    def test_get_parser_singleton(self):
        """测试解析器单例"""
        parser1 = get_parser()
        parser2 = get_parser()
        assert parser1 is parser2
    
    def test_parse_file_dependencies(self):
        """测试便捷函数"""
        # 创建一个临时文件
        test_file = Path("/tmp/test_parse.py")
        test_file.write_text("import os\nimport sys")
        
        try:
            imports = parse_file_dependencies(str(test_file))
            assert "os.py" in imports
            assert "sys.py" in imports
        finally:
            test_file.unlink(missing_ok=True)
    
    def test_detect_file_language(self):
        """测试便捷函数"""
        lang = detect_file_language("test.py")
        assert lang == "python"
    
    def test_parse_nonexistent_file(self):
        """测试不存在的文件"""
        imports = parse_file_dependencies("/nonexistent/file.py")
        assert len(imports) == 0


class TestEdgeCases:
    """边界情况测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_empty_code(self):
        """测试空代码"""
        imports = self.parser.parse_imports("test.py", "")
        assert len(imports) == 0
    
    def test_only_comments(self):
        """测试只有注释"""
        code = """
# This is a comment
# import os
"""
        imports = self.parser.parse_imports("test.py", code)
        assert len(imports) == 0
    
    def test_invalid_syntax(self):
        """测试无效语法"""
        code = "import"  # 不完整的 import
        imports = self.parser.parse_imports("test.py", code)
        # 应该不抛出异常，返回空集合
        assert isinstance(imports, set)
    
    def test_unicode_in_code(self):
        """测试 Unicode 字符"""
        code = """
import os
# 这是一个注释 émoji 🎉
variable = "你好"
"""
        imports = self.parser.parse_imports("test.py", code)
        assert "os.py" in imports
    
    def test_mixed_languages_content(self):
        """测试混合语言内容"""
        # Python 文件中包含其他语言代码
        code = """
import os
# JavaScript code in comment:
# import React from 'react'
js_code = "import React from 'react'"
"""
        imports = self.parser.parse_imports("test.py", code)
        assert "os.py" in imports
        # 不应解析注释和字符串中的导入
        assert "react" not in imports


class TestPerformance:
    """性能测试"""
    
    def setup_method(self):
        self.parser = LanguageDependencyParser()
    
    def test_parse_speed(self):
        """测试解析速度"""
        import time
        code = "\n".join([f"import module{i}" for i in range(100)])
        
        start = time.time()
        result = self.parser.parse_imports("test.py", code)
        elapsed = time.time() - start
        
        assert len(result) == 100
        assert elapsed < 1.0  # 应该小于 1 秒
    
    def test_detect_speed(self):
        """测试检测速度"""
        import time
        files = [f"file{i}.py" for i in range(100)]
        
        start = time.time()
        results = [self.parser.detect_language(f) for f in files]
        elapsed = time.time() - start
        
        assert all(r == "python" for r in results)
        assert elapsed < 0.1  # 应该很快


# 集成测试
class TestIntegration:
    """集成测试"""
    
    def test_full_project_analysis(self, tmp_path):
        """测试完整项目分析"""
        # 创建测试项目结构
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("""
import os
from pathlib import Path
from services.user import UserService
""")
        (tmp_path / "src" / "App.tsx").write_text("""
import React from 'react'
import { UserList } from './components'
""")
        (tmp_path / "src" / "components.tsx").write_text("""
import React from 'react'
export const UserList = () => <div>Users</div>
""")
        
        parser = LanguageDependencyParser()
        
        # 解析所有文件
        all_imports = {}
        for filepath in tmp_path.rglob("*"):
            if filepath.is_file() and filepath.suffix in [".py", ".tsx"]:
                imports = parser.parse_file(str(filepath))
                all_imports[str(filepath)] = imports
        
        # 验证结果
        assert len(all_imports) == 3
        main_py_imports = all_imports[str(tmp_path / "src" / "main.py")]
        assert any("os.py" in imp for imp in main_py_imports)
    
    def test_dependency_graph_integration(self, tmp_path):
        """测试与 DependencyGraph 集成"""
        from app.agent.dependency_graph import DependencyGraph
        
        # 创建测试文件
        (tmp_path / "models.py").write_text("import utils")
        (tmp_path / "services.py").write_text("from models import User")
        (tmp_path / "api.py").write_text("from services import UserService")
        
        parser = LanguageDependencyParser()
        dep_graph = DependencyGraph()
        
        # 构建依赖图
        for filepath in tmp_path.glob("*.py"):
            dep_graph.add_file(str(filepath.name))
            imports = parser.parse_file(str(filepath))
            for imp in imports:
                dep_graph.add_dependency(filepath.name, imp)
        
        # 获取生成顺序
        order = dep_graph.get_generation_order()
        assert len(order) > 0
