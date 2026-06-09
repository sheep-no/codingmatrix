"""
Agent 公共工具函数
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def clean_code_block(content: str) -> str:
    """从 LLM 输出中提取代码块

    支持 ```python ... ```、``` ... ``` 等格式。
    先剥离 <think>...</think>` 标签，再提取代码块。
    如果没有代码块标记，返回原始内容（strip 后）。
    """
    import asyncio
    if asyncio.iscoroutine(content):
        logger.warning("clean_code_block 收到协程对象，降级为 str")
        content = str(content)
    elif not isinstance(content, str):
        content = str(content)

    # 剥离 <think>...</think> 标签（DeepSeek-R1 等模型的思考过程）
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    # 剥离 <think>...</think>` 标签（部分模型变体）
    content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()

    pattern = r'```(?:\w+)?\s*(.*?)\s*```'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


def extract_engineer_content(
    content: Optional[str],
    engineer,
    output_dir: Path,
    file_path: str,
    fix_imports_fn=None,
    all_files=None
) -> Optional[str]:
    """从工程师输出中提取最终文件内容

    统一处理三种情况：
    1. 工程师通过工具直接编辑了文件（get_edited_files）
    2. 工程师返回了编辑标记（JSON）
    3. 工程师返回了完整文件内容

    Args:
        content: 工程师返回的原始内容
        engineer: 工程师实例（需提供 get_edited_files 方法）
        output_dir: 项目输出目录
        file_path: 文件相对路径
        fix_imports_fn: 可选的 import 修复函数 (content, file_path, all_files) -> fixed_content
        all_files: 所有文件列表（用于 import 修复）

    Returns:
        提取后的文件内容，失败返回 None
    """
    import asyncio
    if asyncio.iscoroutine(content):
        logger.warning(f"extract_engineer_content 收到协程对象，降级为 str: {file_path}")
        content = str(content)
    elif content is not None and not isinstance(content, str):
        content = str(content)

    edited_files = engineer.get_edited_files()

    if edited_files:
        full_path = output_dir / file_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            if fix_imports_fn and all_files:
                fixed = fix_imports_fn(content, file_path, all_files)
                if fixed != content:
                    full_path.write_text(fixed, encoding='utf-8')
                    content = fixed
            logger.info(f"工程师通过工具直接编辑了文件: {file_path}，跳过写入步骤")
            return content
        else:
            logger.error(f"工程师报告编辑了文件但文件不存在: {file_path}")
            return None

    if content and _is_edit_marker(content):
        full_path = output_dir / file_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            if fix_imports_fn and all_files:
                fixed = fix_imports_fn(content, file_path, all_files)
                if fixed != content:
                    full_path.write_text(fixed, encoding='utf-8')
                    content = fixed
            logger.info(f"工程师返回编辑标记: {file_path}，读取已修改文件")
            return content
        else:
            logger.error(f"工程师返回编辑标记但文件不存在: {file_path}")
            return None

    if content:
        content = clean_code_block(content)
        if fix_imports_fn and all_files:
            content = fix_imports_fn(content, file_path, all_files)
        return content

    return None


def _is_edit_marker(content: str) -> bool:
    """检查内容是否是编辑标记（JSON 格式）"""
    stripped = content.strip()
    if not stripped.startswith('{'):
        return False
    try:
        import json
        obj = json.loads(stripped)
        return isinstance(obj, dict) and ("action" in obj or "operation" in obj)
    except (json.JSONDecodeError, ValueError):
        return False


def write_file_atomic(output_dir: Path, file_path: str, content: str) -> bool:
    """原子写入文件：先写临时文件，完成后重命名

    Args:
        output_dir: 项目输出目录
        file_path: 文件相对路径
        content: 文件内容

    Returns:
        是否成功
    """
    import uuid
    full_path = output_dir / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用唯一后缀避免并发写入同一 tmp 文件
    tmp_path = full_path.with_suffix(full_path.suffix + f'.tmp.{uuid.uuid4().hex[:8]}')

    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        tmp_path.rename(full_path)
        return True
    except Exception as e:
        logger.error(f"原子写入失败: {file_path}, {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def validate_content_quality(file_path: str, content: str) -> str:
    """验证文件内容质量，检测 LLM 思考过程泄漏等非代码内容

    返回警告信息（空字符串表示通过）。
    """
    if not content or len(content.strip()) < 10:
        return ""

    ext = Path(file_path).suffix.lower()
    stripped = content.strip()

    # 检测 LLM 思考过程泄漏（中文描述性文本混入代码文件）
    # 特征：以中文标点或"最终答案"、"任务执行"等开头
    thinking_patterns = [
        r'^最终答案',
        r'^任务执行',
        r'^基于.*?执行过程',
        r'^已成功完成',
        r'^以下是.*?总结',
        r'^✅',
        r'^---\s*$',
        r'^###\s+✅',
    ]
    for pattern in thinking_patterns:
        if re.match(pattern, stripped, re.MULTILINE):
            return f"内容疑似 LLM 思考过程泄漏（匹配模式: {pattern[:30]}）"

    # CSS 文件内容校验
    if ext == '.css':
        # CSS 不应包含大段中文描述（排除注释）
        lines = [l.strip() for l in stripped.split('\n') if l.strip() and not l.strip().startswith('/*')]
        chinese_lines = sum(1 for l in lines if len(re.findall(r'[\u4e00-\u9fff]', l)) > 10)
        if chinese_lines > len(lines) * 0.3 and chinese_lines > 3:
            return f"CSS 文件包含大量中文文本（{chinese_lines}/{len(lines)} 行），疑似非代码内容"
        # CSS 至少应有一些选择器或属性
        if '{' in stripped and '}' in stripped:
            # 有花括号，基本合格
            pass
        elif len(stripped) > 50 and not any(c in stripped for c in '{:;}'):
            return "CSS 文件缺少基本语法结构（选择器、属性）"

    # JS 文件内容校验
    if ext in ('.js', '.jsx', '.mjs', '.cjs'):
        # JS 不应包含 Python 特征
        python_indicators = ['def ', 'import ', 'from ', 'class ', 'self.', 'print(']
        python_count = sum(1 for ind in python_indicators if ind in stripped)
        if python_count >= 3:
            return f"JavaScript 文件包含 Python 代码特征（匹配 {python_count} 个指标）"

    # Python 文件不应放在前端目录
    if ext == '.py':
        frontend_dirs = ['static/js', 'static/css', 'assets/js', 'assets/css', 'public/js', 'public/css']
        if any(d in file_path.replace('\\', '/') for d in frontend_dirs):
            return f"Python 文件不应出现在前端资源目录: {file_path}"

    return ""


def cleanup_temp_files(output_dir: Path, file_path: str):
    """清理未完成的临时文件"""
    import glob
    full_path = output_dir / file_path
    # 匹配所有 .tmp.* 后缀的临时文件
    pattern = str(full_path) + ".tmp.*"
    for tmp in glob.glob(pattern):
        tmp_path = Path(tmp)
        if tmp_path.exists():
            logger.warning(f"发现未完成的文件，删除: {tmp_path}")
            tmp_path.unlink()
