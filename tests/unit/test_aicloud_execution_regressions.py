"""aicloud 执行沙箱安全回归测试

覆盖已建档缺陷：
- CE2 文件系统逃逸：pathlib/io 等模块未纳入禁用清单
- CE3 JS 仅做 require 子串检查：process/fetch 等全局对象可绕过
- CE4 MAX_MEMORY_MB 死配置：子进程未施加任何内存/CPU 上限
- AE1 is_safe_code 子串检查可被空白与大小写绕过
"""

import pytest

from app.utils.aicloud.auto_executor import is_safe_code
from app.utils.aicloud.code_executor import CodeExecutor


@pytest.fixture
def executor(tmp_path):
    return CodeExecutor(workspace_path=str(tmp_path))


@pytest.mark.parametrize(
    "snippet",
    [
        "from pathlib import Path\nPath('a.txt').read_text()",
        "import io\nio.open('a.txt')",
        "import shutil\nshutil.copy('a', 'b')",
    ],
)
async def test_python_file_modules_are_rejected(executor, snippet):
    """CE2：文件系统相关模块必须在静态检查阶段被拒绝。"""
    result = await executor.execute(snippet, "python")
    assert result.success is False
    assert "禁止导入模块" in result.error


async def test_python_safe_code_still_runs(executor):
    """收紧检查后正常代码仍可执行。"""
    result = await executor.execute("print(2 + 2)", "python")
    assert result.success is True
    assert result.output.strip() == "4"


async def test_python_child_has_memory_and_cpu_limits(executor):
    """CE4：子进程需带上 MAX_MEMORY_MB 的地址空间上限与 CPU 上限。"""
    code = (
        "import resource\n"
        "print(resource.getrlimit(resource.RLIMIT_AS)[0])\n"
        "print(resource.getrlimit(resource.RLIMIT_CPU)[0])\n"
    )
    result = await executor.execute(code, "python", timeout=10)
    assert result.success is True, result.error

    memory_limit, cpu_limit = result.output.split()
    assert int(memory_limit) == CodeExecutor.MAX_MEMORY_MB * 1024 * 1024
    assert int(cpu_limit) == 10


@pytest.mark.parametrize(
    "snippet",
    [
        "fetch('http://example.com')",
        "console.log(process.env)",
        "const fs = require('fs')",
    ],
)
async def test_javascript_globals_are_rejected(executor, snippet):
    """CE3：process/fetch/require 等入口必须被静态拒绝。"""
    result = await executor.execute(snippet, "javascript")
    assert result.success is False


@pytest.mark.parametrize(
    "code",
    [
        "import  os",
        "IMPORT\tOS",
        "exec (1)",
        "open('a.txt')",
        "from pathlib import Path",
    ],
)
def test_is_safe_code_normalizes_whitespace_and_case(code):
    """AE1：空白与大小写变体不再绕过安全检查。"""
    assert is_safe_code(code)[0] is False


def test_is_safe_code_allows_normal_code():
    assert is_safe_code("print('hello')")[0] is True


@pytest.mark.parametrize(
    "snippet",
    [
        'package main\nimport "os"\nfunc main() { os.ReadFile("/etc/passwd") }',
        'package main\nimport (\n\t"fmt"\n\to "os"\n)\nfunc main() { fmt.Println(o.Args) }',
        'package main\nimport _ "net/http"\nfunc main() {}',
        'package main\nimport "os/exec"\nfunc main() {}',
        "package main\nimport\n\"io/ioutil\"\nfunc main() {}",
        "package main\nimport `os`\nfunc main() {}",
        'package main\nimport "C"\nfunc main() {}',
    ],
)
def test_go_dangerous_imports_are_detected(snippet):
    """CE2：Go 侧文件系统/进程/网络导入必须在静态检查阶段被识别。"""
    from app.utils.aicloud.code_executor import _find_banned_go_import

    assert _find_banned_go_import(snippet) is not None


@pytest.mark.parametrize(
    "snippet",
    [
        'package main\nimport "fmt"\nfunc main() { fmt.Println("os") }',
        'package main\nimport (\n\t"strings"\n\t"strconv"\n)\nfunc main() {}',
    ],
)
def test_go_safe_imports_pass(snippet):
    """收紧检查后正常导入与含同名文本的字符串字面量不受影响。"""
    from app.utils.aicloud.code_executor import _find_banned_go_import

    assert _find_banned_go_import(snippet) is None


async def test_go_banned_import_blocked_before_compilation(executor):
    """CE2：禁用导入在调用 go 工具链之前即返回失败，无需本机安装 Go。"""
    result = await executor.execute('package main\nimport "os"\nfunc main() {}', "go")
    assert result.success is False
    assert "禁止导入包" in result.error
