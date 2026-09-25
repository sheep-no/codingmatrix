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

import os
import re
import logging
import difflib
import tempfile
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _atomic_write_text(path: Path, text: str) -> None:
    """同目录写临时文件 + fsync + os.replace，避免中断留下半写文件（CP5）。"""
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


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
            raise RuntimeError("LLM call function is not configured for patch generation")

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
            if not patch:
                raise RuntimeError(f"LLM patch generation returned no patch for {file_path}")
            return patch
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"生成 patch 失败: {e}")
            raise RuntimeError(f"LLM patch generation failed: {e}") from e

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
            logger.error(f"应用 patch 异常: {e}", exc_info=True)

        return result

    async def apply_patch_to_file(
        self,
        file_path: Path,
        patch: str,
        output_dir: Optional[Path] = None,
    ) -> PatchResult:
        """
        应用 patch 到实际文件

        Args:
            file_path: 文件路径
            patch: unified diff patch
            output_dir: 安全边界目录，文件路径必须在此目录内

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

        # 路径穿越校验：确保文件在安全边界内
        if output_dir is not None:
            resolved_file = file_path.resolve()
            resolved_dir = output_dir.resolve()
            try:
                resolved_file.relative_to(resolved_dir)
            except ValueError:
                return PatchResult(
                    success=False,
                    file_path=str(file_path),
                    original_content="",
                    patched_content="",
                    diff=patch,
                    errors=[f"路径穿越: {file_path} 不在 {output_dir} 内"],
                    warnings=[]
                )

        original_content = file_path.read_text(encoding='utf-8')
        result = await self.apply_patch(str(file_path), original_content, patch)

        if result.success:
            # 备份原文件（原子写，避免备份与写入之间中断留下半写 .bak）
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            _atomic_write_text(backup_path, original_content)

            # 原子写入 patch 后的内容：进程中断不会留下半写文件
            _atomic_write_text(file_path, result.patched_content)

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
        # 用 splitlines 而非 split('\n')：后者对以换行结尾的 patch 会多出一个
        # 合成空串，在容忍裸空行后会被误当作空上下文行吞入 hunk（CP6）。
        lines = patch.splitlines()
        i = 0

        while i < len(lines):
            match = self.PATCH_HUNK_HEADER.match(lines[i])
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                # 收集 hunk body。标准上下文行为单个空格开头，但 LLM 生成 diff 时
                # 常把空上下文行的尾随空格一并去掉，形成裸空行（''）。此前裸空行会
                # 提前终止收集，使 hunk 被截断、后续行被当作非 hunk 行跳过，最终
                # 静默写出被截断的内容且 success=True（CP6）。这里把裸空行按空
                # 上下文行处理，并用 old_count/new_count 预算判定 body 收集完毕。
                hunk_lines = []
                i += 1
                ctx = deleted = added = 0
                while i < len(lines):
                    line = lines[i]
                    if line.startswith('+'):
                        added += 1
                    elif line.startswith('-'):
                        deleted += 1
                    elif line.startswith(' '):
                        ctx += 1
                    elif line == '':
                        ctx += 1
                        line = ' '  # 归一化为标准空上下文行
                    else:
                        break

                    hunk_lines.append(line)
                    i += 1

                    if (ctx + deleted == old_count
                            and ctx + added == new_count
                            and ctx + deleted + added > 0):
                        break

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
        """应用 hunks 到原始行（精确匹配）

        hunk 行号基于原始文件：多 hunk 时从后向前应用，避免前一个 hunk 改变
        行数后使后续 hunk 的行号漂移（CP12）。同时逐行校验上下文/删除行与
        原文是否一致，不一致返回 None 交由模糊匹配处理（CP1）。
        """
        result = list(original_lines)

        for hunk in sorted(hunks, key=lambda h: h['old_start'], reverse=True):
            old_start = hunk['old_start'] - 1  # 转换为 0-based
            old_count = hunk.get('old_count', 0)

            # 新文件创建 @@ -0,0 +1,N @@：old_start 0 → 插入到文件开头
            if old_start == -1 and old_count == 0:
                old_start = 0

            if old_start < 0 or old_start + old_count > len(result):
                return None

            expected = [line[1:] for line in hunk['lines'] if line[:1] in (' ', '-')]
            if len(expected) != old_count or expected != result[old_start:old_start + old_count]:
                return None

            # 应用变更：old_count 是原始文件中此 hunk 覆盖的行数（上下文 + 删除）
            new_lines = []
            for line in hunk['lines']:
                if line.startswith('-'):
                    continue  # 删除行
                elif line.startswith('+'):
                    new_lines.append(line[1:])  # 添加行
                else:
                    new_lines.append(line[1:])  # 上下文行

            # 替换：使用 old_count 作为替换范围（而非仅上下文行数）
            result[old_start:old_start + old_count] = new_lines

        return result

    def _apply_hunks_fuzzy(self, original_lines: List[str], hunks: List[Dict], max_offset: int = 5) -> Optional[List[str]]:
        """应用 hunks 到原始行（模糊匹配，允许行号偏移）"""
        result = list(original_lines)

        # 与精确路径一致：hunk 行号基于原始文件，从后向前应用避免漂移（CP12）
        for hunk in sorted(hunks, key=lambda h: h['old_start'], reverse=True):
            old_start = hunk['old_start'] - 1
            old_count = hunk.get('old_count', 0)
            if old_start == -1 and old_count == 0:
                old_start = 0
            expected_context = [line[1:] for line in hunk['lines'] if line.startswith(' ')]

            # 尝试在偏移范围内匹配上下文；优先偏移 0（声明位置），
            # 避免无上下文 hunk 被 -max_offset 处抢先匹配（CP3）
            best_match = None
            for offset in sorted(range(-max_offset, max_offset + 1), key=abs):
                test_start = old_start + offset
                if test_start < 0 or test_start + old_count > len(result):
                    continue

                # 在 old_count 范围内提取上下文行位置进行匹配
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

            # 替换：使用 old_count 作为替换范围
            result[best_match:best_match + old_count] = new_lines

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
        raise RuntimeError(f"incremental patch target does not exist: {file_path}")

    original_content = file_path.read_text(encoding='utf-8')

    # 生成 patch
    patch = await patcher.generate_patch_from_requirement(
        file_path=str(file_path),
        original_content=original_content,
        change_request=change_request,
        project_context=project_context
    )

    if not patch:
        raise RuntimeError(f"LLM patch generation returned no patch for {file_path}")

    # 应用 patch
    result = await patcher.apply_patch(str(file_path), original_content, patch)
    if not result.success:
        raise RuntimeError(
            f"incremental patch apply failed for {file_path}: "
            + "; ".join(result.errors)
        )
    return result


@dataclass
class CrossFilePatchResult:
    """跨文件 patch 应用结果"""
    primary_file: str
    primary_result: Optional[PatchResult] = None
    dependent_results: List[PatchResult] = field(default_factory=list)
    failed_patches: List[str] = field(default_factory=list)
    dependency_chain: Dict[str, List[str]] = field(default_factory=dict)


class CrossFilePatcher:
    """
    跨文件 patch 生成器

    v4.8.0 新增：
    - 给定变更文件和依赖链，自动为所有受影响文件生成 patch
    - 无法自动 patch 的文件标记为 "manual review required"
    """

    def __init__(self, code_patcher: CodePatcher):
        self.code_patcher = code_patcher

    async def generate_cross_file_patches(
        self,
        requirement: str,
        changed_files: List[str],
        affected_files: Dict[str, List[str]],
        project_path: Path,
        file_contents: Dict[str, str],
    ) -> CrossFilePatchResult:
        """
        为变更文件和所有受影响文件生成 patch

        Args:
            requirement: 变更需求描述
            changed_files: 直接变更的文件列表
            affected_files: {变更文件: [受影响的下游文件]}
            project_path: 项目根目录
            file_contents: {文件路径: 文件内容}

        Returns:
            CrossFilePatchResult
        """
        result = CrossFilePatchResult(
            primary_file=changed_files[0] if changed_files else "",
            dependency_chain=affected_files,
        )

        for changed_file in changed_files:
            content = file_contents.get(changed_file, "")
            if not content:
                try:
                    content = (project_path / changed_file).read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    raise RuntimeError(f"failed to read changed file {changed_file}: {e}") from e
            if not content:
                raise RuntimeError(f"changed file is empty or missing: {changed_file}")

            project_context = {
                "requirement": requirement,
                "affected_files": affected_files.get(changed_file, []),
            }

            patch = await self.code_patcher.generate_patch_from_requirement(
                changed_file, content, requirement, project_context
            )

            if patch:
                patch_result = await self.code_patcher.apply_patch(
                    changed_file, content, patch
                )
                if patch_result.success:
                    result.primary_result = patch_result
                else:
                    errors = "; ".join(patch_result.errors or ["apply_patch failed"])
                    raise RuntimeError(f"failed to apply patch to {changed_file}: {errors}")
            else:
                raise RuntimeError(f"LLM returned empty patch for {changed_file}")

        for source_file, dependents in affected_files.items():
            for dep_file in dependents:
                if dep_file in changed_files:
                    continue

                dep_content = file_contents.get(dep_file, "")
                if not dep_content:
                    try:
                        dep_content = (project_path / dep_file).read_text(encoding="utf-8", errors="ignore")
                    except Exception as e:
                        raise RuntimeError(f"failed to read dependent file {dep_file}: {e}") from e
                if not dep_content:
                    raise RuntimeError(f"dependent file is empty or missing: {dep_file}")

                dep_requirement = (
                    f"文件 {source_file} 已修改（需求：{requirement}），"
                    f"请调整 {dep_file} 以保持与 {source_file} 的依赖关系一致"
                )

                dep_project_context = {
                    "requirement": requirement,
                    "source_file": source_file,
                    "source_changes": f"文件 {source_file} 已根据需求变更",
                }

                dep_patch = await self.code_patcher.generate_patch_from_requirement(
                    dep_file, dep_content, dep_requirement, dep_project_context
                )

                if dep_patch:
                    dep_result = await self.code_patcher.apply_patch(
                        dep_file, dep_content, dep_patch
                    )
                    if dep_result.success:
                        result.dependent_results.append(dep_result)
                    else:
                        errors = "; ".join(dep_result.errors or ["apply_patch failed"])
                        raise RuntimeError(f"failed to apply patch to {dep_file}: {errors}")
                else:
                    raise RuntimeError(f"LLM returned empty patch for {dep_file}")

        logger.info(
            f"跨文件 patch 生成完成: "
            f"primary={result.primary_result is not None}, "
            f"dependents={len(result.dependent_results)}, "
            f"failed={len(result.failed_patches)}"
        )

        if result.failed_patches:
            raise RuntimeError(
                "cross-file patch failed for "
                f"{len(result.failed_patches)} file(s): "
                + ", ".join(result.failed_patches)
            )
        return result
