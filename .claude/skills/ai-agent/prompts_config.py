"""
AI Agent Prompts - Prompt 模板配置
"""

PROMPTS = {
    "task_planning": """将以下任务分解为可执行的步骤：

任务：{task}

上下文：
{context}

支持的步骤类型：
- file_operation: 文件操作 (read, write, delete, create)
- code_generation: 代码生成
- tool_call: 工具调用
- ai_call: AI调用 (使用指定模型)

请以JSON数组格式返回步骤：
[
  {{"type": "file_operation", "description": "读取文件", "params": {{"operation": "read", "path": "..."}}}},
  {{"type": "code_generation", "description": "生成代码", "params": {{"language": "python"}}}},
  ...
]""",

    "code_review": """审查以下代码，检查：
1. 安全性（SQL注入、XSS、命令注入等）
2. 正确性（逻辑错误、边界情况）
3. 性能问题
4. 代码质量

代码：
```{code}```

上下文：{context}

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "suggestions": ["改进建议"],
  "risk_level": "low/medium/high"
}}""",

    "plan_review": """审查以下执行计划，判断是否合理和安全：

计划：
{plan}

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "suggestions": ["改进建议"],
  "risk_level": "low/medium/high"
}}""",

    "file_operation_review": """审查以下文件操作：

操作类型：{operation}
文件路径：{file_path}
文件内容：{content}

检查项：
1. 路径是否安全（无路径遍历风险）
2. 扩展名是否允许
3. 内容是否包含危险模式
4. 操作是否合理

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "risk_level": "low/medium/high"
}}""",
}


DANGEROUS_PATTERNS = [
    (r"rm\s+-rf\s+/", "递归删除根目录"),
    (r"fork\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*:\s*&[^}]*\}", "Fork炸弹"),
    (r"exec\s*\(\s*['\"].*;.*['\"]\s*\)", "危险命令执行"),
    (r"__import__\s*\(\s*['\"](?:os|subprocess|pty|socket)", "动态导入危险模块"),
    (r"subprocess\.call\s*\(", "子进程调用"),
    (r"os\.system\s*\(", "系统命令执行"),
    (r"os\.popen\s*\(", "Popen执行"),
    (r"pty\.spawn\s*\(", "PTY spawn"),
]

PROTECTED_PATHS = {
    "/etc", "/root", "/proc", "/sys", "/boot", "/dev",
    "/var/log", "/var/cache", "/var/run", "/tmp"
}

PROTECTED_FILES = {
    ".env", ".git/config", "id_rsa", "id_ed25519",
    "known_hosts", "authorized_keys"
}

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css",
    ".md", ".json", ".yaml", ".yml", ".txt", ".sh", ".bash",
    ".toml", ".xml", ".sql", ".env", ".gitignore", ".dockerfile"
}
