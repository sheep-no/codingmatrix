"""
增量修改 Mixin — 基于依赖图的定向修改

核心理念：依赖图是项目的结构化表示，增量修改以它为核心，不重新扫描项目。

三种场景：
1. 新增需求 — 在依赖图上追加新节点
2. 修改 bug — 定向修改已有文件
3. 修改功能 — 更新已有文件 + 可能新增/删除文件
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.agent.dependency_graph import DependencyGraph
from app.agent.orchestrator_progress import PROGRESS_LABELS
from app.agent.models import DEFAULT_ARCHITECT_MODEL, DEFAULT_FAST_MODEL, DEFAULT_REASONING_MODEL

logger = logging.getLogger(__name__)


class IncrementalModifyMixin:
    """增量修改 Mixin — 基于依赖图的定向修改"""

    async def generate_incremental(
        self,
        requirement: str,
        callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        增量修改主流程（P3: 快速模式）

        1. 加载依赖图（不重新扫描项目）
        2. 架构师分析需求 + 依赖图 → 输出变更计划
        3. 按变更类型分派：add / modify / delete
        4. 更新依赖图

        P3 优化：跳过复杂度分析、规范生成、交叉验证等非必要步骤
        """
        start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.generated_files = []
        self.errors = []
        self.warnings = []

        # P3: 快速模式 - 跳过完整初始化，只初始化必要的组件
        await self._initialize_components_fast(requirement)

        # ========== Step 1: 加载依赖图 ==========
        dep_graph_path = self.output_dir / ".dep_graph.json"
        from app.agent.language_detector import LanguageDetector
        from app.agent.adapters.language_adapter import LanguageAdapterRegistry

        lang_result = LanguageDetector.detect(requirement)
        detected_language = lang_result.language
        language_adapter = LanguageAdapterRegistry.get_adapter(detected_language)

        dep_graph = DependencyGraph.load(str(dep_graph_path), language_adapter=language_adapter)
        if dep_graph is None:
            logger.warning("依赖图不存在，回退到完整生成流程")
            return await self.generate_with_spec_first(requirement, callback)

        logger.info(f"加载依赖图: {len(dep_graph.nodes)} 个节点")

        # 从依赖图构建项目摘要（给架构师看）
        project_summary = self._build_project_summary_from_graph(dep_graph)

        self._report_progress(
            "incremental_loaded", 1, 6,
            callback=callback,
            nodes_count=len(dep_graph.nodes),
            project_summary_len=len(project_summary)
        )

        # ========== Step 2: 架构师分析变更计划 ==========
        change_plan = await self._analyze_changes_with_architect(
            requirement, project_summary, dep_graph, callback
        )

        if not change_plan:
            logger.warning("架构师未返回变更计划，回退到完整生成流程")
            return await self.generate_with_spec_first(requirement, callback)

        self._report_progress(
            "incremental_plan", 2, 6,
            callback=callback,
            changes_count=len(change_plan),
            changes=[c.get("action", "") + " " + c.get("path", "") for c in change_plan]
        )

        # ========== Step 3: 按变更类型分派生成 ==========
        from app.agent.orchestrator_generation.spec_first_generate import SharedContext
        ctx = SharedContext(requirement, self.output_dir)

        # P3: 快速模式 - 使用默认复杂度（跳过复杂度分析）
        if self.complexity:
            ctx.complexity = {
                "level": self.complexity.level.value,
                "estimated_files": self.complexity.estimated_files,
                "has_frontend": self.complexity.has_frontend,
                "has_backend": self.complexity.has_backend,
                "has_database": self.complexity.has_database,
                "key_technologies": self.complexity.key_technologies
            }
        else:
            # 快速模式：使用默认复杂度
            ctx.complexity = {
                "level": "small",
                "estimated_files": len(change_plan),
                "has_frontend": False,
                "has_backend": True,
                "has_database": False,
                "key_technologies": ["Python"]
            }

        project_context = {
            "requirement": requirement,
            "complexity": ctx.complexity,
            "output_dir": str(self.output_dir),
            "is_incremental": True,
        }

        generated_contents = {}
        files_generated = 0
        files_failed = 0

        # 分组：add / modify / delete
        add_files = [c for c in change_plan if c.get("action") == "add"]
        modify_files = [c for c in change_plan if c.get("action") == "modify"]
        delete_files = [c for c in change_plan if c.get("action") == "delete"]

        logger.info(f"变更计划: add={len(add_files)}, modify={len(modify_files)}, delete={len(delete_files)}")

        # ========== Step 3a: 处理新增文件 ==========
        if add_files:
            for file_info in add_files:
                file_path = file_info.get("path", "")
                if file_path and file_path not in dep_graph.nodes:
                    dep_graph.add_file(
                        file_path,
                        file_type=file_info.get("file_type"),
                        priority=file_info.get("priority", 3),
                        description=file_info.get("description", "")
                    )

        # ========== Step 3b: 处理修改文件（核心差异） ==========
        all_files_to_generate = []

        for file_info in modify_files:
            file_path = file_info.get("path", "")
            if not file_path:
                continue

            # 读取原文件内容
            full_path = self.output_dir / file_path
            original_content = ""
            if full_path.exists():
                original_content = full_path.read_text(encoding="utf-8")

            # P7: 文件内容差异检测 — 检查原文件是否已经满足需求
            if original_content and self._content_already_satisfies(
                original_content, file_info.get("reason", ""), requirement
            ):
                logger.info(f"文件已满足需求，跳过生成: {file_path}")
                generated_contents[file_path] = original_content[:8000]
                continue

            all_files_to_generate.append({
                "path": file_path,
                "action": "modify",
                "description": file_info.get("description", ""),
                "reason": file_info.get("reason", ""),
                "original_content": original_content,
                "file_type": file_info.get("file_type"),
                "priority": file_info.get("priority", 3),
            })

        for file_info in add_files:
            all_files_to_generate.append({
                "path": file_info.get("path", ""),
                "action": "add",
                "description": file_info.get("description", ""),
                "file_type": file_info.get("file_type"),
                "priority": file_info.get("priority", 3),
            })

        # ========== Step 3c: 处理删除文件 ==========
        for file_info in delete_files:
            file_path = file_info.get("path", "")
            if file_path:
                full_path = self.output_dir / file_path
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"删除文件: {file_path}")
                if file_path in dep_graph.nodes:
                    del dep_graph.nodes[file_path]

        if not all_files_to_generate:
            logger.info("无需生成的文件")
            dep_graph.save(str(dep_graph_path))
            return {
                "success": True,
                "total_files_created": 0,
                "total_files": 0,
                "elapsed_time": time.time() - start_time,
                "generated_files": [],
                "errors": [],
                "warnings": []
            }

        # ========== Step 4: 拓扑排序 + 生成 ==========
        # 重新构建依赖关系（包括新增的文件）
        for file_info in all_files_to_generate:
            file_path = file_info.get("path", "")
            if file_path and file_path not in dep_graph.nodes:
                dep_graph.add_file(
                    file_path,
                    file_type=file_info.get("file_type"),
                    priority=file_info.get("priority", 3),
                    description=file_info.get("description", "")
                )

        # 构建 file_plan 供拓扑调度器使用
        file_plan = []
        for fi in all_files_to_generate:
            file_plan.append({
                "path": fi["path"],
                "file_type": fi.get("file_type"),
                "priority": fi.get("priority", 3),
                "description": fi.get("description", ""),
                "action": fi.get("action", "add"),
                "original_content": fi.get("original_content", ""),
                "reason": fi.get("reason", ""),
            })

        # 使用动态拓扑调度生成
        from app.agent.spec_first_generator import SpecFirstGenerator
        spec_generator = SpecFirstGenerator(ctx, language=detected_language, api_key_token=self.api_key_token)

        result = await self._generate_with_dynamic_topology_incremental(
            ctx, dep_graph, spec_generator, requirement,
            project_context, generated_contents, file_plan, callback, language_adapter
        )

        files_generated = result.get("files_generated", 0)
        files_failed = result.get("files_failed", 0)
        self.generated_files = result.get("generated_files", [])
        self.errors.extend(result.get("errors", []))
        self.warnings.extend(result.get("warnings", []))

        # ========== Step 5: P6 增量依赖图更新 ==========
        # 根据生成的文件内容更新依赖关系
        await self._update_dependency_graph_incremental(
            dep_graph, generated_contents, language_adapter
        )

        # 保存更新后的依赖图
        dep_graph.save(str(dep_graph_path))
        logger.info(f"依赖图已更新并保存: {len(dep_graph.nodes)} 个节点")

        elapsed = time.time() - start_time
        logger.info(f"增量修改完成: {files_generated} 文件, {files_failed} 失败, {elapsed:.1f}s")

        return {
            "success": files_failed == 0,
            "total_files_created": files_generated,
            "total_files": len(all_files_to_generate),
            "elapsed_time": elapsed,
            "generated_files": self.generated_files,
            "errors": self.errors,
            "warnings": self.warnings,
            "changes": {
                "added": len(add_files),
                "modified": len(modify_files),
                "deleted": len(delete_files)
            }
        }

    def _build_project_summary_from_graph(self, dep_graph: DependencyGraph) -> str:
        """从依赖图构建项目摘要（给架构师看）"""
        lines = []
        lines.append("## 已有项目文件")
        for path, node in dep_graph.nodes.items():
            deps = dep_graph.adjacency.get(path, set())
            dep_str = f" -> {', '.join(deps)}" if deps else ""
            lines.append(f"- {path} (type={node.file_type}, priority={node.priority}){dep_str}")
            if node.description:
                lines.append(f"  描述: {node.description}")

        # 生成顺序
        try:
            layers = dep_graph.get_generation_layers()
            order = [f for layer in layers for f in layer]
            lines.append(f"\n## 生成顺序")
            for i, f in enumerate(order, 1):
                lines.append(f"{i}. {f}")
        except Exception:
            pass

        return "\n".join(lines)

    async def _analyze_changes_with_architect(
        self,
        requirement: str,
        project_summary: str,
        dep_graph: DependencyGraph,
        callback: Optional[callable] = None
    ) -> List[Dict]:
        """架构师分析需求 + 依赖图 → 输出变更计划（支持缓存）"""

        # P1: 架构师分析缓存
        import hashlib
        cache_key = hashlib.sha256(f"{requirement}:{project_summary}".encode()).hexdigest()
        cached_plan = self._get_cached_change_plan(cache_key)
        if cached_plan:
            logger.info(f"命中架构师分析缓存: {cache_key[:16]}...")
            self._report_progress("architect_cache_hit", 1, 1, callback=callback)
            return cached_plan

        prompt = f"""你是一个项目架构师，负责分析用户的增量修改需求。

## 用户需求
{requirement}

## 已有项目结构（依赖图）
{project_summary}

## 你的任务
分析用户需求，输出需要对已有项目做的变更列表。

## 输出格式（严格 JSON 数组）
```json
[
  {{"action": "modify", "path": "src/main.py", "reason": "Flask→FastAPI", "file_type": "entry", "priority": 1}},
  {{"action": "add", "path": "src/config.py", "description": "新增配置文件", "file_type": "config", "priority": 2}},
  {{"action": "delete", "path": "src/old_file.py", "reason": "不再需要"}}
]
```

## 变更类型
- **modify**: 修改已有文件（保留原文件的功能，根据需求修改）
- **add**: 新增文件（项目中不存在的新文件）
- **delete**: 删除文件（不再需要的文件）

## 规则
1. 只输出需要变更的文件，不要输出"无需修改"的文件
2. path 必须是项目中已有的路径（modify/delete）或新路径（add）
3. file_type 可选值: entry, model, router, api, config, utils, frontend_page, frontend_component, frontend_style, test
4. priority: 1(最高)-5(最低)
5. 严格输出 JSON 数组，不要有其他文字

## JSON 数组:
"""

        try:
            response = await self.architect.call_llm(
                prompt,
                system_prompt="你是项目架构师，负责分析增量修改需求并输出变更计划。只输出 JSON 数组。"
            )

            # 解析 JSON
            import re
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                change_plan = json.loads(json_match.group())
                if isinstance(change_plan, list):
                    logger.info(f"架构师变更计划: {len(change_plan)} 个变更")
                    # P1: 保存到缓存
                    self._save_cached_change_plan(cache_key, change_plan)
                    return change_plan

            logger.warning(f"架构师返回格式错误: {response[:200]}")
            return []

        except Exception as e:
            logger.error(f"架构师分析失败: {e}")
            return []

    # ========== P1: 架构师分析缓存 ==========

    def _get_cached_change_plan(self, cache_key: str) -> Optional[List[Dict]]:
        """获取缓存的变更计划"""
        try:
            cache_file = self.output_dir / ".cache" / "change_plans.json"
            if not cache_file.exists():
                return None

            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            if cache_key in cache:
                entry = cache[cache_key]
                # 检查是否过期（24 小时）
                if time.time() - entry.get("timestamp", 0) < 86400:
                    return entry.get("plan")
            return None
        except Exception:
            return None

    def _save_cached_change_plan(self, cache_key: str, plan: List[Dict]):
        """保存变更计划到缓存"""
        try:
            cache_dir = self.output_dir / ".cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "change_plans.json"

            cache = {}
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)

            cache[cache_key] = {
                "plan": plan,
                "timestamp": time.time()
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            logger.info(f"变更计划已缓存: {cache_key[:16]}...")
        except Exception as e:
            logger.warning(f"缓存保存失败: {e}")

    async def _generate_with_dynamic_topology_incremental(
        self,
        ctx,
        dep_graph: DependencyGraph,
        spec_generator,
        requirement: str,
        project_context: Dict,
        generated_contents: Dict[str, str],
        file_plan: List[Dict],
        callback=None,
        language_adapter=None
    ) -> Dict[str, Any]:
        """增量模式的动态拓扑调度生成 — 支持并行生成无依赖文件"""

        from app.agent.utils import extract_engineer_content, is_valid_code_content, write_file_atomic
        from app.agent.spec_first_generator import SpecFirstGenerator

        files_generated = 0
        files_failed = 0
        generated_files_list = []
        errors_list = []
        warnings_list = []
        state_lock = asyncio.Lock()
        total_files = len(file_plan)

        # 构建 file_plan lookup（按 path 索引）
        file_plan_by_path = {fi["path"]: fi for fi in file_plan}

        # 获取依赖图分层（支持并行）
        layers = dep_graph.get_generation_layers()
        logger.info(f"依赖图分层: {len(layers)} 层, 共 {total_files} 个文件")

        # 只处理 file_plan 中的文件
        plan_paths = set(file_plan_by_path.keys())

        # P8: 并行度动态调整 — 根据模型并发限制创建信号量池
        # 默认每个模型最多 2 个并发请求
        model_semaphores: Dict[str, asyncio.Semaphore] = {}
        MAX_CONCURRENT_PER_MODEL = 2

        async def generate_single_file(file_path: str, tracker=None) -> Optional[str]:
            """生成单个文件（P4: 根据复杂度选择模型，P8: 并发控制）"""
            nonlocal files_generated, files_failed

            file_info = file_plan_by_path.get(file_path, {})
            action = file_info.get("action", "add")
            description = file_info.get("description", f"生成 {file_path}")
            original_content = file_info.get("original_content", "")

            # P4: 根据变更复杂度选择模型
            is_simple = self._is_simple_change(file_info)
            if is_simple:
                # 简单变更用轻量模型（更快）
                from app.agent.models import DEFAULT_FAST_MODEL
                engineer = self._select_engineer(file_path, force_model=DEFAULT_FAST_MODEL)
                model_name = DEFAULT_FAST_MODEL
                logger.info(f"简单变更，使用轻量模型: {file_path}")
            else:
                engineer = self._select_engineer(file_path)
                model_name = self._select_model_for_file(file_path)

            # P8: 获取模型专属信号量，控制并发
            model_semaphore = self._get_model_semaphore(model_name)
            logger.info(f"等待模型信号量: {model_name} ({file_path})")

            async with model_semaphore:
                logger.info(f"获取信号量成功: {model_name} ({file_path})")
                return await self._generate_file_with_model(
                    file_path, file_info, engineer, model_name,
                    project_context, generated_contents, spec_generator,
                    dep_graph, callback, tracker
                )

        # 按层并行生成
        for layer_idx, layer in enumerate(layers):
            # 只处理 file_plan 中的文件
            layer_files = [f for f in layer if f in plan_paths]
            if not layer_files:
                continue

            logger.info(f"并行生成第 {layer_idx + 1}/{len(layers)} 层: {len(layer_files)} 个文件")
            self._report_progress(
                "generating_layer", layer_idx + 1, len(layers),
                callback=callback,
                layer_files=layer_files,
                total_files=total_files
            )

            # 并行生成当前层的所有文件
            tasks = []
            for file_path in layer_files:
                tasks.append(generate_single_file(file_path))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            failed_files = []
            for i, result in enumerate(results):
                file_path = layer_files[i]
                if isinstance(result, Exception):
                    logger.error(f"文件生成失败: {file_path} - {result}")
                    failed_files.append(file_path)
                elif result:
                    async with state_lock:
                        generated_contents[file_path] = result[:8000]
                        generated_files_list.append({
                            "path": file_path,
                            "description": file_plan_by_path.get(file_path, {}).get("description", ""),
                            "success": True,
                            "size": len(result),
                            "action": file_plan_by_path.get(file_path, {}).get("action", "add"),
                        })
                        files_generated += 1

            # P5: 智能重试 — 失败文件用降级模型重试
            if failed_files:
                logger.info(f"尝试用降级模型重试 {len(failed_files)} 个失败文件")
                retry_results = await self._retry_with_fallback_model(
                    failed_files, file_plan_by_path, project_context,
                    generated_contents, dep_graph, spec_generator, callback
                )
                for file_path, content in retry_results.items():
                    if content:
                        async with state_lock:
                            generated_contents[file_path] = content[:8000]
                            generated_files_list.append({
                                "path": file_path,
                                "description": file_plan_by_path.get(file_path, {}).get("description", ""),
                                "success": True,
                                "size": len(content),
                                "action": file_plan_by_path.get(file_path, {}).get("action", "add"),
                                "retried": True,
                            })
                            files_generated += 1
                            failed_files.remove(file_path)

                # 记录仍然失败的文件
                for file_path in failed_files:
                    errors_list.append(f"文件生成失败（重试后）: {file_path}")
                    files_failed += 1

            # 检查取消信号
            if self.cancel_event and self.cancel_event.is_set():
                logger.info("检测到取消信号，停止生成")
                break

        return {
            "files_generated": files_generated,
            "files_failed": files_failed,
            "generated_files": generated_files_list,
            "errors": errors_list,
            "warnings": warnings_list,
            "total_files": total_files,
        }

    def _get_context_length(self, model_name: str) -> int:
        """获取模型上下文长度"""
        try:
            from app.agent.context_budget import get_context_length
            return get_context_length(model_name)
        except Exception:
            return 32768

    async def _initialize_components_fast(self, requirement: str):
        """P3: 快速初始化 — 只初始化增量修改必需的组件"""
        import time as _time
        self._start_time = _time.time()
        self._update_phase("analyzing")

        # 只初始化模型路由和工程师，跳过复杂度分析、规范生成等
        from app.agent.dynamic_model_router import LayeredModelRouter
        from app.agent.specialist_base import get_global_llm_semaphore
        from app.agent.models import DEFAULT_ARCHITECT_MODEL, DEFAULT_CODE_MODEL, DEFAULT_REASONING_MODEL

        self.model_router = LayeredModelRouter()
        self.model_assignment = self.model_router.get_assignment()

        def _get_model(attr: str, default: str) -> str:
            return getattr(self.model_assignment, attr, default) if self.model_assignment else default

        semaphore = get_global_llm_semaphore()
        cost_tracker = getattr(self, 'cost_tracker', None)

        from app.agent.specialists import Architect, FrontendEngineer, BackendEngineer
        self.architect = Architect(
            "架构师", _get_model("architect_model", DEFAULT_ARCHITECT_MODEL),
            task_type="generate", api_key_token=self.api_key_token,
            provider_id=self.provider_id, semaphore=semaphore,
            cost_tracker=cost_tracker, cancel_event=self.cancel_event
        )
        self.frontend_engineer = FrontendEngineer(
            "前端工程师", _get_model("frontend_model", DEFAULT_CODE_MODEL),
            task_type="generate", api_key_token=self.api_key_token,
            provider_id=self.provider_id, semaphore=semaphore,
            cost_tracker=cost_tracker, cancel_event=self.cancel_event
        )
        self.backend_engineer = BackendEngineer(
            "后端工程师", _get_model("backend_model", DEFAULT_REASONING_MODEL),
            task_type="generate", api_key_token=self.api_key_token,
            provider_id=self.provider_id, semaphore=semaphore,
            cost_tracker=cost_tracker, cancel_event=self.cancel_event
        )

        # 跳过：ComplexityAnalyzer, CodeValidator, ErrorRecoveryLoop, CodeReviewer
        # 跳过：APIContractChecker, CodePatcher, CrossFilePatcher
        # 跳过：规范生成, 依赖图验证, 交叉验证

        logger.info("快速模式初始化完成（跳过复杂度分析、规范生成、交叉验证）")

    def _is_simple_change(self, file_info: Dict) -> bool:
        """P4: 判断是否为简单变更（可用轻量模型）"""
        action = file_info.get("action", "add")
        description = file_info.get("description", "").lower()
        reason = file_info.get("reason", "").lower()

        # 简单变更特征
        simple_keywords = [
            "添加端点", "add endpoint", "健康检查", "health",
            "添加注释", "add comment", "修改配置", "update config",
            "添加导入", "add import", "修复拼写", "fix typo"
        ]

        # 复杂变更特征
        complex_keywords = [
            "重构", "refactor", "迁移", "migrate", "flask→fastapi",
            "重写", "rewrite", "架构", "architecture", "数据库", "database"
        ]

        # 检查是否为复杂变更
        for keyword in complex_keywords:
            if keyword in description or keyword in reason:
                return False

        # 检查是否为简单变更
        for keyword in simple_keywords:
            if keyword in description or keyword in reason:
                return True

        # 新增文件默认为简单变更
        if action == "add":
            return True

        # 修改文件默认为复杂变更（需要理解原代码）
        return False

    async def _retry_with_fallback_model(
        self,
        failed_files: List[str],
        file_plan_by_path: Dict,
        project_context: Dict,
        generated_contents: Dict[str, str],
        dep_graph: DependencyGraph,
        spec_generator,
        callback=None
    ) -> Dict[str, Optional[str]]:
        """P5: 用降级模型重试失败文件"""
        from app.agent.utils import extract_engineer_content, is_valid_code_content, write_file_atomic
        from app.agent.spec_first_generator import SpecFirstGenerator

        # 降级模型链：GLM-4-9B → DeepSeek-R1 → Qwen3-8B
        fallback_models = [
            DEFAULT_ARCHITECT_MODEL,
            DEFAULT_REASONING_MODEL,
            DEFAULT_FAST_MODEL
        ]

        results = {}

        for file_path in failed_files:
            file_info = file_plan_by_path.get(file_path, {})
            description = file_info.get("description", f"生成 {file_path}")
            original_content = file_info.get("original_content", "")
            action = file_info.get("action", "add")

            # 尝试每个降级模型
            for model_name in fallback_models:
                try:
                    logger.info(f"尝试用 {model_name} 重试: {file_path}")

                    # 选择工程师
                    if "frontend" in file_path or file_path.endswith(('.html', '.css', '.js', '.vue')):
                        from app.agent.specialists import FrontendEngineer
                        engineer = FrontendEngineer("前端工程师", model_name, task_type="generate",
                                                   api_key_token=self.api_key_token, cancel_event=self.cancel_event)
                    else:
                        from app.agent.specialists import BackendEngineer
                        engineer = BackendEngineer("后端工程师", model_name, task_type="generate",
                                                  api_key_token=self.api_key_token, cancel_event=self.cancel_event)

                    # 构建上下文
                    combined_context = {**project_context}
                    if action == "modify" and original_content:
                        combined_context["original_content"] = original_content
                        combined_context["modification_reason"] = file_info.get("reason", "")
                        combined_context["is_modification"] = True

                    spec_context = {}
                    if spec_generator:
                        file_type = file_info.get("file_type", "unknown")
                        spec_context = spec_generator.get_spec_context_for_file(
                            file_path, file_type,
                            max_chars_per_spec=SpecFirstGenerator.get_spec_budget(
                                self._get_context_length(model_name)
                            )
                        )

                    dep_context = dep_graph.get_context_for_file(
                        file_path,
                        generated_contents,
                        model_context_length=self._get_context_length(model_name),
                        project_spec=project_context.get("architecture", {}).get("project_spec"),
                    )

                    # 生成文件
                    content = await engineer.generate_file(
                        file_path, description, combined_context, spec_context, dep_context,
                        project_path=str(self.output_dir), callback=callback,
                        is_existing_file=(action == "modify")
                    )

                    if asyncio.iscoroutine(content):
                        content = await content

                    # 提取内容
                    if content:
                        content = await extract_engineer_content(
                            content, engineer, self.output_dir, file_path,
                            expected_language="Python",
                            llm_caller=self._quick_llm_check,
                        )

                    if content and content.strip():
                        # 写入文件
                        normalized = self._strip_output_dir_prefix(file_path)
                        write_file_atomic(self.output_dir, normalized, content)
                        logger.info(f"重试成功: {file_path} (模型: {model_name})")
                        results[file_path] = content
                        break

                except Exception as e:
                    logger.warning(f"重试失败: {file_path} (模型: {model_name}) - {e}")
                    continue

            if file_path not in results:
                logger.error(f"所有模型重试失败: {file_path}")
                results[file_path] = None

        return results

    async def _update_dependency_graph_incremental(
        self,
        dep_graph: DependencyGraph,
        generated_contents: Dict[str, str],
        language_adapter=None
    ):
        """P6: 增量更新依赖图 — 根据生成的文件内容更新依赖关系"""
        import re

        for file_path, content in generated_contents.items():
            if not content:
                continue

            # 提取 import 语句
            imports = self._extract_imports_from_content(content, file_path)

            # 更新依赖关系
            for imported_path in imports:
                if imported_path in dep_graph.nodes:
                    dep_graph.add_dependency(file_path, imported_path)
                    logger.debug(f"更新依赖: {file_path} -> {imported_path}")

        # 重新构建拓扑排序
        try:
            layers = dep_graph.get_generation_layers()
            logger.info(f"依赖图更新后: {len(layers)} 层")
        except Exception as e:
            logger.warning(f"依赖图拓扑排序失败: {e}")

    def _extract_imports_from_content(self, content: str, file_path: str) -> List[str]:
        """从文件内容中提取 import 语句"""
        imports = []
        lines = content.split('\n')

        # 获取所有文件路径（相对于 output_dir）
        all_files = self._get_all_file_paths()
        relative_files = set()
        for f in all_files:
            try:
                relative_files.add(str(f.relative_to(self.output_dir)))
            except ValueError:
                continue

        for line in lines:
            line = line.strip()

            # Python import
            if line.startswith('import ') or line.startswith('from '):
                # from .xxx import yyy
                if line.startswith('from .'):
                    # 相对导入
                    match = re.match(r'from\s+\.(\w+)', line)
                    if match:
                        module = match.group(1)
                        # 转换为文件路径
                        dir_path = '/'.join(file_path.split('/')[:-1])
                        potential_path = f"{dir_path}/{module}.py"
                        if potential_path in relative_files:
                            imports.append(potential_path)

                # from xxx import yyy
                elif line.startswith('from ') and ' import ' in line:
                    match = re.match(r'from\s+(\w+)', line)
                    if match:
                        module = match.group(1)
                        # 尝试不同的路径
                        potential_paths = [
                            f"src/{module}.py",
                            f"src/{module}/__init__.py",
                            f"{module}.py",
                        ]
                        for path in potential_paths:
                            if path in relative_files:
                                imports.append(path)
                                break

        return imports

    def _get_all_file_paths(self) -> set:
        """获取所有文件路径"""
        try:
            return set(self.output_dir.rglob('*.py'))
        except Exception:
            return set()

    def _content_already_satisfies(
        self,
        original_content: str,
        reason: str,
        requirement: str
    ) -> bool:
        """P7: 检查原文件内容是否已经满足需求"""
        if not original_content or not reason:
            return False

        # 简单的关键词匹配检测
        reason_lower = reason.lower()
        content_lower = original_content.lower()

        # 检查是否已经包含所需功能
        # 例如：需求是"添加 /health 端点"，检查是否已有 /health
        if "添加" in reason or "add" in reason_lower:
            # 提取关键词
            keywords = []
            if "/health" in reason_lower or "健康检查" in reason_lower:
                keywords.append("/health")
            if "/status" in reason_lower or "状态" in reason_lower:
                keywords.append("/status")
            if "/api" in reason_lower:
                keywords.append("/api")

            # 检查是否已有这些关键词
            for keyword in keywords:
                if keyword in content_lower:
                    return True

        # 检查是否已经使用了所需框架
        if "fastapi" in reason_lower:
            if "from fastapi" in content_lower or "fastapi" in content_lower:
                return True

        if "flask" in reason_lower:
            if "from flask" in content_lower or "flask" in content_lower:
                return True

        return False

    async def _generate_file_with_model(
        self,
        file_path: str,
        file_info: Dict,
        engineer,
        model_name: str,
        project_context: Dict,
        generated_contents: Dict[str, str],
        spec_generator,
        dep_graph: DependencyGraph,
        callback=None,
        tracker=None
    ) -> Optional[str]:
        """使用指定模型生成单个文件"""
        from app.agent.utils import extract_engineer_content, is_valid_code_content, write_file_atomic
        from app.agent.spec_first_generator import SpecFirstGenerator

        action = file_info.get("action", "add")
        description = file_info.get("description", f"生成 {file_path}")
        original_content = file_info.get("original_content", "")

        self._report_model_info(engineer.name if hasattr(engineer, 'name') else str(engineer), model_name)
        combined_context = {**project_context}

        # 注入上游文件内容
        upstream_context = {k: v for k, v in generated_contents.items()}
        if upstream_context:
            combined_context["upstream_files"] = {
                path: content[:8000]
                for path, content in upstream_context.items()
            }

        spec_context = {}
        if spec_generator:
            file_type = file_info.get("file_type", "unknown")
            spec_context = spec_generator.get_spec_context_for_file(
                file_path, file_type,
                max_chars_per_spec=SpecFirstGenerator.get_spec_budget(
                    self._get_context_length(model_name)
                )
            )
        dep_context = dep_graph.get_context_for_file(
            file_path,
            upstream_context,
            model_context_length=self._get_context_length(model_name),
            project_spec=project_context.get("architecture", {}).get("project_spec"),
        )

        # 根据 action 决定生成策略
        if action == "modify" and original_content:
            combined_context["original_content"] = original_content
            combined_context["modification_reason"] = file_info.get("reason", "")
            combined_context["is_modification"] = True

            logger.info(f"增量修改模式: {file_path} (原文件 {len(original_content)} 字节)")

            initial_content = await engineer.generate_file(
                file_path, description, combined_context, spec_context, dep_context,
                project_path=str(self.output_dir), callback=callback,
                is_existing_file=True,
                heartbeat_tracker=tracker
            )
        else:
            initial_content = await engineer.generate_file(
                file_path, description, combined_context, spec_context, dep_context,
                project_path=str(self.output_dir), callback=callback,
                is_existing_file=False,
                heartbeat_tracker=tracker
            )

        if asyncio.iscoroutine(initial_content):
            initial_content = await initial_content

        # 提取内容
        raw_content = initial_content
        architecture = project_context.get("architecture", {})
        target_language = architecture.get("language", "")
        from app.agent.utils import get_expected_language_for_file
        file_expected_language = get_expected_language_for_file(file_path, target_language)

        initial_content = await extract_engineer_content(
            initial_content, engineer, self.output_dir, file_path,
            expected_language=file_expected_language,
            llm_caller=self._quick_llm_check,
        )

        if initial_content is None or not initial_content.strip():
            _, invalid_reason = is_valid_code_content(file_path, raw_content or "")
            if not invalid_reason:
                invalid_reason = "内容提取失败或语言不匹配"
            recovered = await self._recover_invalid_content(
                file_path, description, combined_context, invalid_reason,
                engineer, spec_context, dep_context, callback,
                heartbeat_tracker=tracker
            )
            if recovered:
                initial_content = recovered
            else:
                initial_content = await self._retry_generate_file(
                    file_path, description, combined_context, spec_context, dep_context,
                    engineer, callback, heartbeat_tracker=tracker, reason=invalid_reason
                )
                if not initial_content:
                    raise ValueError(f"文件生成失败: {file_path}")

        # 写入文件
        normalized = self._strip_output_dir_prefix(file_path)
        full_path = self.output_dir / normalized
        logger.info(f"写入文件: {normalized} ({len(initial_content)} 字节)")
        write_file_atomic(self.output_dir, normalized, initial_content)
        logger.info(f"文件已写入: {full_path}")

        return initial_content

    def _get_model_semaphore(self, model_name: str) -> asyncio.Semaphore:
        """P8: 获取模型专属信号量（类方法版本）"""
        if not hasattr(self, '_model_semaphores'):
            self._model_semaphores = {}
        
        MAX_CONCURRENT_PER_MODEL = 2
        
        if model_name not in self._model_semaphores:
            self._model_semaphores[model_name] = asyncio.Semaphore(MAX_CONCURRENT_PER_MODEL)
        
        return self._model_semaphores[model_name]
