import re
import json
import asyncio
import logging
import subprocess as sp
from typing import Optional, Dict, List
from pathlib import Path

from app.agent.project_profiler import ProjectProfiler, ProjectProfile

logger = logging.getLogger(__name__)


class UtilsMixin:

    def _is_anti_pattern(self, requirement: str) -> bool:
        if not self.feedback_learner:
            return False
        for pattern in self.feedback_learner._fix_patterns.values():
            if pattern.is_anti_pattern() and pattern.error_pattern:
                if re.search(pattern.error_pattern, requirement, re.IGNORECASE):
                    logger.warning(f"反模式拦截: {pattern.error_type} - {pattern.failure_reason}")
                    return True
        return False

    async def _cache_review_gate(self, cached) -> bool:
        if self._is_anti_pattern(cached.requirement or ""):
            return False

        if not self.reviewer:
            return True

        try:
            architecture_summary = json.dumps(cached.architecture, ensure_ascii=False)[:800]
            review = await self.reviewer.review_code(
                architecture_summary,
                "cached_architecture",
                context="审查缓存架构是否与当前需求兼容"
            )
            risk_level = review.get("risk_level", "low")
            if risk_level == "high":
                logger.warning(f"缓存架构语义审查风险等级: {risk_level}")
                return False
        except Exception as e:
            logger.warning(f"缓存审查闸门异常（放行）: {e}")

        return True

    async def _select_dynamic_model(self, candidate_models: List[str], task_type: str) -> str:
        from app.agent.dynamic_model_router import get_dynamic_router

        router = await get_dynamic_router()
        return await router.get_best_model(candidate_models, task_type)

    def _validate_file_plan(self, file_plan: List[Dict]) -> List[Dict]:
        valid_files = []
        for file_info in file_plan:
            path = file_info.get("path", "")
            if not path:
                continue

            if re.search(r'[^a-zA-Z0-9_\-./]', path):
                self.warnings.append(f"跳过非法路径: {path}")
                continue

            depth = path.count('/') + path.count('\\')
            if depth > 5:
                self.warnings.append(f"跳过过深路径: {path}")
                continue

            if path.startswith('/') or path.startswith('\\'):
                path = path.lstrip('/\\')
                file_info["path"] = path

            ext = Path(path).suffix.lower()
            valid_extensions = {
                '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.css', '.scss', '.sass',
                '.less', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.env', '.sql',
                '.sh', '.bat', '.ps1', '.dockerfile', '.gitignore', '.editorconfig',
                '.graphql', '.proto', '.xml', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico',
                '',
            }
            if ext not in valid_extensions:
                self.warnings.append(f"跳过不支持的文件类型: {path}")
                continue

            if any(f.get("path") == path for f in valid_files):
                self.warnings.append(f"跳过重复路径: {path}")
                continue

            valid_files.append(file_info)

        if not valid_files:
            self.warnings.append("所有文件路径被过滤，使用默认文件计划")
            valid_files = [
                {"path": "main.py", "description": "主程序入口", "priority": 1},
                {"path": "requirements.txt", "description": "依赖列表", "priority": 2},
                {"path": "README.md", "description": "项目文档", "priority": 3}
            ]

        return valid_files

    async def _profile_project(self) -> Optional[ProjectProfile]:
        """分析项目模式"""
        try:
            profiler = ProjectProfiler()
            profile = profiler.profile(self.output_dir)
            logger.info(f"项目指纹 | 架构={profile.architecture.pattern} | 风险点={len(profile.risk_areas)} | 测试约定={len(profile.test_patterns)}")
            return profile
        except Exception as e:
            logger.error(f"项目分析失败：{e}")
            return None

    def _compute_layers(self, file_plan: List[Dict]) -> List[List[str]]:
        groups: Dict[int, List[str]] = {}
        for fi in file_plan:
            p = fi.get("priority", 3)
            if p not in groups:
                groups[p] = []
            groups[p].append(fi.get("path", ""))

        return [groups[p] for p in sorted(groups.keys())]

    async def _cache_specs(
        self,
        requirement: str,
        architecture: Dict,
        file_plan: List[Dict],
        requirement_vector: Optional[List[float]] = None
    ):
        if not self.spec_cache:
            return

        specs = {}
        if self.complexity:
            specs["complexity"] = {
                "level": self.complexity.level.value,
                "estimated_files": self.complexity.estimated_files,
                "has_frontend": self.complexity.has_frontend,
                "has_backend": self.complexity.has_backend,
                "has_database": self.complexity.has_database,
            }

        self.spec_cache.save(
            requirement=requirement,
            specs=specs,
            architecture=architecture,
            file_plan=file_plan,
            complexity=specs.get("complexity", {}),
            tech_stack=architecture.get("tech_stack", []),
            requirement_vector=requirement_vector
        )

    async def _record_learning_data(
        self,
        requirement: str,
        architecture: Dict,
        file_plan: List[Dict]
    ):
        if not self.feedback_learner:
            return

        all_errors = []
        if self.error_recovery:
            for fix_attempt in self.error_recovery.fix_history:
                all_errors.append(fix_attempt.error_message)

        error_embeddings = {}
        if all_errors:
            error_embeddings = await self.feedback_learner.compute_error_embeddings(all_errors)

        if self.error_recovery:
            for fix_attempt in self.error_recovery.fix_history:
                self.feedback_learner.record_fix(
                    file_path=fix_attempt.file_path,
                    file_type="python",
                    original_content="",
                    fixed_content="",
                    errors={"validation_error": [fix_attempt.error_message]},
                    model_name=self.model_assignment.backend_model if self.model_assignment else "",
                    success=fix_attempt.fix_applied,
                    error_embeddings=error_embeddings
                )

    async def _wait_for_approval(self, key: str, timeout: float = 300.0) -> bool:
        if not self.approval_callback:
            return True

        try:
            approved = await asyncio.wait_for(
                self.approval_callback(key),
                timeout=timeout
            )
            return approved
        except asyncio.TimeoutError:
            logger.warning(f"审批超时（{timeout}s）: {key}，自动跳过")
            self.warnings.append(f"审批超时，自动跳过: {key}")
            return False

    def _should_check_api_consistency(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        if ext in {'.vue', '.js', '.jsx', '.ts', '.tsx'}:
            return True
        if ext == '.py' and ('api' in file_path.lower() or 'route' in file_path.lower()):
            return True
        return False

    async def _check_and_report_api_issues(self, file_path: str, content: str):
        if not self.api_contract_checker:
            return

        is_frontend = self._is_frontend_file(file_path)

        if is_frontend:
            backend_files = {}
            for py_file in self.output_dir.rglob('*.py'):
                if '__pycache__' not in str(py_file):
                    try:
                        backend_files[str(py_file.relative_to(self.output_dir))] = py_file.read_text()
                    except Exception:
                        pass

            issues = self.api_contract_checker.check_single_file_consistency(
                file_path=file_path,
                code=content,
                is_frontend=True,
                counterpart_files=backend_files
            )
        else:
            frontend_files = {}
            for ext in ['*.vue', '*.js', '*.jsx', '*.ts', '*.tsx']:
                for f in self.output_dir.rglob(ext):
                    try:
                        frontend_files[str(f.relative_to(self.output_dir))] = f.read_text()
                    except Exception:
                        pass

            issues = self.api_contract_checker.check_single_file_consistency(
                file_path=file_path,
                code=content,
                is_frontend=False,
                counterpart_files=frontend_files
            )

        for issue in issues:
            self._report_progress(
                "api_consistency_issue",
                len(self.generated_files) + 1,
                len(self.generated_files) + 5,
                issue_type=issue.issue_type,
                severity=issue.severity,
                message=issue.message,
                suggestion=issue.suggestion,
                file_path=file_path
            )
            if issue.severity == 'error':
                self.errors.append(f"API 不一致: {issue.message}")
            else:
                self.warnings.append(f"API 警告: {issue.message}")

    async def _save_to_memory(self, requirement: str, architecture: Dict):
        if not self.memory_enabled:
            return

        try:
            from app.agent.memory import MemoryEntry

            entry = MemoryEntry(
                type="project_generation",
                content=f"需求: {requirement[:500]}\n架构: {json.dumps(architecture, ensure_ascii=False)[:1000]}",
                importance=0.8
            )
            self.conversation_memory.add(entry)

            tech_stack = architecture.get("tech_stack", [])
            for tech in tech_stack[:5]:
                tech_entry = MemoryEntry(
                    type="tech_stack",
                    content=f"项目使用了 {tech} 技术栈",
                    importance=0.7,
                    metadata={"source": "orchestrator_generation", "category": "tech_stack"}
                )
                self.knowledge_memory.add(tech_entry)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    async def _call_llm_for_patch(self, prompt: str, system_prompt: str) -> str:
        try:
            engineer = self.backend_engineer or self.architect
            if engineer:
                return await engineer.call_llm(prompt, system_prompt)
            return ""
        except Exception as e:
            logger.error(f"LLM patch 调用失败: {e}")
            return ""

    def _estimate_generation_cost(self, architecture: Dict, file_plan: List[Dict]) -> Dict:
        estimated_files = len(file_plan)
        level = self.complexity.level.value if self.complexity else "unknown"

        cost_estimates = {
            "simple": {"tokens": 5000, "cost_usd": 0.005},
            "small": {"tokens": 15000, "cost_usd": 0.015},
            "medium": {"tokens": 45000, "cost_usd": 0.045},
            "large": {"tokens": 100000, "cost_usd": 0.10},
            "enterprise": {"tokens": 250000, "cost_usd": 0.25}
        }

        estimate = cost_estimates.get(level, cost_estimates["medium"])

        if estimate["cost_usd"] < 0.01:
            cost_level = "low"
            suggestion = "成本较低，可直接生成"
        elif estimate["cost_usd"] < 0.10:
            cost_level = "medium"
            suggestion = "成本适中，建议开启 review 提高质量"
        else:
            cost_level = "high"
            suggestion = f"成本较高（约 ${estimate['cost_usd']:.2f}），建议：1) 简化需求 2) 使用更便宜的模型 3) 分阶段生成"

        return {
            "estimated_tokens": estimate["tokens"],
            "estimated_cost_usd": estimate["cost_usd"],
            "cost_level": cost_level,
            "suggestion": suggestion,
            "level": level,
            "estimated_files": estimated_files
        }

    async def _git_save_snapshot(self, message: str):
        if hasattr(self, 'snapshot_mgr') and self.snapshot_mgr:
            snapshot = await self.snapshot_mgr.save_snapshot(
                self.output_dir,
                session_id=self.session_id or "default",
                description=message,
                files_changed=[],
                model_used=getattr(self, 'model_name', '') or "",
                duration=0.0,
            )
            if snapshot:
                logger.info(f"Git 快照已保存 (SnapshotManager): {snapshot.tag}")
                return
            logger.info("SnapshotManager 保存失败，回退到原始逻辑")

        GITIGNORE_CONTENT = """*.env
*.key
*.pem
*.secret
__pycache__/
node_modules/
test_sandbox.db*
"""

        git_dir = self.output_dir / ".git"
        if not git_dir.exists():
            try:
                sp.run(
                    ['git', 'init'],
                    cwd=str(self.output_dir),
                    capture_output=True, timeout=10, check=True
                )
                sp.run(
                    ['git', 'config', 'user.name', 'CodingMatrix Agent'],
                    cwd=str(self.output_dir),
                    capture_output=True, timeout=10, check=True
                )
                sp.run(
                    ['git', 'config', 'user.email', 'agent@codingmatrix.ai'],
                    cwd=str(self.output_dir),
                    capture_output=True, timeout=10, check=True
                )
                gitignore = self.output_dir / ".gitignore"
                if not gitignore.exists():
                    gitignore.write_text(GITIGNORE_CONTENT, encoding='utf-8')
            except sp.TimeoutExpired:
                logger.warning("git init 超时")
                return
            except sp.CalledProcessError as e:
                logger.warning(f"git init 失败: {e.stderr.decode(errors='replace')[:200]}")
                return

        try:
            sp.run(
                ['git', 'add', '-A'],
                cwd=str(self.output_dir),
                capture_output=True, timeout=30, check=True
            )
            sp.run(
                ['git', 'commit', '-m', message, '--allow-empty'],
                cwd=str(self.output_dir),
                capture_output=True, timeout=30
            )
            logger.info(f"Git 快照已保存: {message[:80]}")
        except sp.TimeoutExpired:
            logger.warning("git commit 超时")
        except sp.CalledProcessError as e:
            stderr = e.stderr.decode(errors='replace')[:200] if e.stderr else ''
            if 'nothing to commit' in stderr:
                logger.info("Git: 无变更需提交")
            else:
                logger.warning(f"git commit 失败: {stderr}")
