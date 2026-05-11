"""
CodePatcher - 代码补丁生成器

解决缓存局限性问题：
1. 当基础架构命中缓存时，新需求只是局部修改
2. 直接调用 LLM 生成 diff patch 而非全量代码
3. 应用 patch 到原始文件，避免全量重新生成

使用场景：
- 增量生成：用户需求微调（如"加一个删除功能"）
- 缓存命中但需局部更新
- 错误修复：仅修改出错部分

工作原理：
1. 识别需要修改的文件
2. 生成 unified diff patch
3. 应用 patch 到原文件
4. 验证 patch 应用结果
"""

import re
import logging
import difflib
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PatchResult:
    """Patch 应用结果"""
    success: bool
    file_path: str
    original_content: str
    patched_content: str
    diff: str
    errors: List[str]
    warnings: List[str]


class CodePatcher:
    """
    代码补丁生成器

    支持两种模式：
    1. LLM 生成模式：调用 LLM 生成 patch
    2. 直接 diff 模式：基于原始内容和新内容生成 diff
    """

    # Patch 格式模式
    PATCH_HEADER = re.compile(r'^---\s+(\S+)')
    PATCH_HUNK_HEADER = re.compile(r'^@@\s+-(\d+),?(\d*)\s+\+(\d+),?(\d*)\s+@@')

    def __init__(self, llm_call_fn=None):
        """
        初始化 CodePatcher

        Args:
            llm_call_fn: 异步函数，用于调用 LLM 生成 patch
                        签名：async def llm_call(prompt: str, system_prompt: str) -> str
        """
        self.llm_call_fn = llm_call_fn

    async def generate_patch_from_requirement(
        self,
        file_path: str,
        original_content: str,
        change_request: str,
        project_context: Optional[Dict] = None
    ) -> Optional[str]:
        """
        基于需求变更生成 patch

        Args:
            file_path: 文件路径
            original_content: 原始文件内容
            change_request: 变更需求描述
            project_context: 项目上下文

        Returns:
            unified diff patch 字符串，或 None
        """
        if not self.llm_call_fn:
            logger.warning("未提供 LLM 调用函数，无法生成 patch")
            return None

        system_prompt = """你是一位代码补丁生成专家。

你的任务：
1. 分析原始代码和变更需求
2. 生成 unified diff 格式的 patch
3. 只修改必要的部分，保持其他代码不变

输出格式要求：
- 必须使用标准 unified diff 格式
- 以 ```diff 开头，``` 结尾
- 包含完整的 hunk 头（@@ -old_start,old_count +new_start,new_count @@）
- 不要省略上下文行

示例格式：
```diff
--- a/file.py
+++ b/file.py
@@ -10,7 +10,10 @@
     existing code line
     existing code line
-    old line to remove
+    new line to add
+    another new line
     existing code line
```"""

        context_info = ""
        if project_context:
            context_info = f"\n项目上下文：{project_context.get('requirement', '')}"

        prompt = f"""请为以下文件生成 patch：

文件路径：{file_path}

原始代码：
```
{original_content}
```

变更需求：{change_request}{context_info}

请生成 unified diff 格式的 patch："""

        try:
            response = await self.llm_call_fn(prompt, system_prompt)
            patch = self._extract_patch_from_response(response)
            return patch
        except Exception as e:
            logger.error(f"生成 patch 失败: {e}")
            return None

    def generate_diff_from_content(
        self,
        file_path: str,
        original_content: str,
        new_content: str
    ) -> str:
        """
        基于原始内容和新内容直接生成 diff

        Args:
            file_path: 文件路径
            original_content: 原始内容
            new_content: 新内容

        Returns:
            unified diff 字符串
        """
        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}"
        )

        return ''.join(diff)

    async def apply_patch(
        self,
        file_path: str,
        original_content: str,
        patch: str
    ) -> PatchResult:
        """
        应用 patch 到原始内容

        Args:
            file_path: 文件路径
            original_content: 原始内容
            patch: unified diff patch

        Returns:
            PatchResult 结果
        """
        result = PatchResult(
            success=False,
            file_path=file_path,
            original_content=original_content,
            patched_content="",
            diff=patch,
            errors=[],
            warnings=[]
        )

        try:
            # 解析 patch
            hunks = self._parse_patch(patch)

            if not hunks:
                result.errors.append("无法解析 patch 内容")
                return result

            # 应用 hunks
            patched_lines = self._apply_hunks(original_content.splitlines(), hunks)

            if patched_lines is None:
                result.errors.append("Patch 应用失败：行号不匹配")
                result.warnings.append("尝试使用模糊匹配...")

                # 尝试模糊匹配
                patched_lines = self._apply_hunks_fuzzy(original_content.splitlines(), hunks)

                if patched_lines is None:
                    result.errors.append("模糊匹配也失败，请检查 patch 是否适用于当前文件版本")
                    return result

            result.patched_content = '\n'.join(patched_lines)
            result.success = True

        except Exception as e:
            result.errors.append(f"应用 patch 异常: {str(e)}")

        return result

    async def apply_patch_to_file(
        self,
        file_path: Path,
        patch: str
    ) -> PatchResult:
        """
        应用 patch 到实际文件

        Args:
            file_path: 文件路径
            patch: unified diff patch

        Returns:
            PatchResult 结果
        """
        if not file_path.exists():
            return PatchResult(
                success=False,
                file_path=str(file_path),
                original_content="",
                patched_content="",
                diff=patch,
                errors=[f"文件不存在: {file_path}"],
                warnings=[]
            )

        original_content = file_path.read_text(encoding='utf-8')
        result = await self.apply_patch(str(file_path), original_content, patch)

        if result.success:
            # 备份原文件
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            backup_path.write_text(original_content, encoding='utf-8')

            # 写入 patch 后的内容
            file_path.write_text(result.patched_content, encoding='utf-8')

        return result

    def estimate_patch_impact(self, patch: str) -> Dict:
        """
        评估 patch 的影响范围

        Args:
            patch: unified diff patch

        Returns:
            影响评估字典
        """
        lines_added = 0
        lines_deleted = 0
        files_affected = set()

        for line in patch.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                lines_added += 1
            elif line.startswith('-') and not line.startswith('---'):
                lines_deleted += 1
            elif line.startswith('--- a/'):
                files_affected.add(line[6:])
            elif line.startswith('+++ b/'):
                files_affected.add(line[6:])

        return {
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "total_changes": lines_added + lines_deleted,
            "files_affected": list(files_affected),
            "is_small_patch": (lines_added + lines_deleted) < 20,
            "is_medium_patch": 20 <= (lines_added + lines_deleted) < 100,
            "is_large_patch": (lines_added + lines_deleted) >= 100
        }

    # ==================== 内部方法 ====================

    def _extract_patch_from_response(self, response: str) -> Optional[str]:
        """从 LLM 响应中提取 patch"""
        # 尝试提取 ```diff ... ``` 块
        match = re.search(r'```diff\s*\n(.*?)\n```', response, re.DOTALL)
        if match:
            return match.group(1)

        # 尝试提取 ``` ... ``` 块（无语言标记）
        match = re.search(r'```\s*\n(---.*?)\n```', response, re.DOTALL)
        if match:
            return match.group(1)

        # 尝试直接查找 --- 开头的内容
        lines = response.split('\n')
        start_idx = None
        for i, line in enumerate(lines):
            if line.startswith('--- a/') or line.startswith('--- '):
                start_idx = i
                break

        if start_idx is not None:
            return '\n'.join(lines[start_idx:])

        return None

    def _parse_patch(self, patch: str) -> List[Dict]:
        """解析 patch 为 hunks"""
        hunks = []
        lines = patch.split('\n')
        i = 0

        while i < len(lines):
            match = self.PATCH_HUNK_HEADER.match(lines[i])
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                hunk_lines = []
                i += 1
                while i < len(lines) and lines[i].startswith(('+', '-', ' ')):
                    hunk_lines.append(lines[i])
                    i += 1

                hunks.append({
                    'old_start': old_start,
                    'old_count': old_count,
                    'new_start': new_start,
                    'new_count': new_count,
                    'lines': hunk_lines
                })
            else:
                i += 1

        return hunks

    def _apply_hunks(self, original_lines: List[str], hunks: List[Dict]) -> Optional[List[str]]:
        """应用 hunks 到原始行（精确匹配）"""
        result = list(original_lines)

        for hunk in hunks:
            old_start = hunk['old_start'] - 1  # 转换为 0-based

            if old_start < 0 or old_start > len(result):
                return None

            # 验证上下文
            expected_context = [line[1:] for line in hunk['lines'] if line.startswith(' ')]
            actual_context = result[old_start:old_start + len(expected_context)]

            if expected_context != actual_context:
                return None

            # 应用变更
            new_lines = []
            for line in hunk['lines']:
                if line.startswith('-'):
                    continue  # 删除行
                elif line.startswith('+'):
                    new_lines.append(line[1:])  # 添加行
                else:
                    new_lines.append(line[1:])  # 上下文行

            # 替换
            result[old_start:old_start + len(expected_context)] = new_lines

        return result

    def _apply_hunks_fuzzy(self, original_lines: List[str], hunks: List[Dict], max_offset: int = 5) -> Optional[List[str]]:
        """应用 hunks 到原始行（模糊匹配，允许行号偏移）"""
        result = list(original_lines)

        for hunk in hunks:
            old_start = hunk['old_start'] - 1
            expected_context = [line[1:] for line in hunk['lines'] if line.startswith(' ')]

            # 尝试在偏移范围内匹配
            best_match = None
            for offset in range(-max_offset, max_offset + 1):
                test_start = old_start + offset
                if test_start < 0 or test_start + len(expected_context) > len(result):
                    continue

                actual_context = result[test_start:test_start + len(expected_context)]
                if expected_context == actual_context:
                    best_match = test_start
                    break

            if best_match is None:
                return None

            # 应用变更
            new_lines = []
            for line in hunk['lines']:
                if line.startswith('-'):
                    continue
                elif line.startswith('+'):
                    new_lines.append(line[1:])
                else:
                    new_lines.append(line[1:])

            result[best_match:best_match + len(expected_context)] = new_lines

        return result


# ==================== 便捷函数 ====================

async def apply_incremental_change(
    file_path: Path,
    change_request: str,
    llm_call_fn,
    project_context: Optional[Dict] = None
) -> PatchResult:
    """
    应用增量变更到文件

    Args:
        file_path: 文件路径
        change_request: 变更需求
        llm_call_fn: LLM 调用函数
        project_context: 项目上下文

    Returns:
        PatchResult 结果
    """
    patcher = CodePatcher(llm_call_fn=llm_call_fn)

    if not file_path.exists():
        return PatchResult(
            success=False,
            file_path=str(file_path),
            original_content="",
            patched_content="",
            diff="",
            errors=["文件不存在"],
            warnings=[]
        )

    original_content = file_path.read_text(encoding='utf-8')

    # 生成 patch
    patch = await patcher.generate_patch_from_requirement(
        file_path=str(file_path),
        original_content=original_content,
        change_request=change_request,
        project_context=project_context
    )

    if not patch:
        return PatchResult(
            success=False,
            file_path=str(file_path),
            original_content=original_content,
            patched_content="",
            diff="",
            errors=["生成 patch 失败"],
            warnings=[]
        )

    # 应用 patch
    return await patcher.apply_patch(str(file_path), original_content, patch)
