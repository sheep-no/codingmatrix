import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from app.agent.test_runner import IsolatedTestRunner
from app.agent.impact_analyzer import ImpactAnalyzer
from app.agent.project_profiler import ProjectProfile
from app.agent.test_selector import TestSelector
from app.agent.failure_clusterer import FailureClusterer, FailureCluster
from app.utils.performance_metrics import metrics_collector
from app.agent.orchestrator_progress import PROGRESS_LABELS

logger = logging.getLogger(__name__)


class TestingMixin:

    async def _run_dynamic_tests(
        self,
        runner: IsolatedTestRunner,
        modified_files: Optional[List[str]] = None,
        project_profile: Optional[ProjectProfile] = None
    ) -> Dict[str, Any]:
        self._report_progress(PROGRESS_LABELS["running_tests"], 0, 1, phase="testing")
        self._update_phase("running_tests")

        test_start = metrics_collector.start_timer('TestingMixin')

        # 智能测试选择
        test_files = await self._select_tests(modified_files, project_profile)

        test_cmd = self._detect_test_command(self.output_dir, test_files)

        docker_result = await self._run_tests_in_docker(test_cmd)
        if docker_result is not None:
            return docker_result

        try:
            result = await runner.run_tests()

            summary = {
                "success": result.success,
                "total": result.total_tests,
                "passed": result.passed,
                "failed": result.failed,
                "errors": result.errors,
                "failed_tests": result.failed_tests,
                "logs_preview": result.logs[:1000]
            }

            # 测试失败聚类
            if not result.success and result.failed_tests:
                clusters = await self._cluster_test_failures(result.failed_tests, result.logs)
                summary["failure_clusters"] = [
                    {
                        "root_cause": c.root_cause,
                        "suggested_fix": c.suggested_fix,
                        "test_count": len(c.tests),
                        "tests": c.tests[:5]  # 限制显示数量
                    }
                    for c in clusters[:3]  # 只显示前 3 个集群
                ]
                self.warnings.append(f"测试失败聚类：{len(clusters)} 个根因 | {len(result.failed_tests)} 个失败")
                self._report_warning(
                    message=f"测试失败聚类：{len(clusters)} 个根因 | {len(result.failed_tests)} 个失败",
                    code="test_failure_cluster",
                    cluster_count=len(clusters),
                    failed_count=len(result.failed_tests),
                )

            # 推送测试结果事件
            self._report_test_results({
                "summary": {
                    "passed": result.passed,
                    "failed": result.failed,
                    "skipped": result.errors,
                    "total": result.total_tests,
                    "coverage": None  # 可以后续扩展覆盖率
                },
                "duration": metrics_collector.get_last_duration('TestingMixin', 'run_tests'),
                "failed_tests": result.failed_tests[:10] if result.failed_tests else [],
                "success": result.success
            })

            self._report_progress(
                PROGRESS_LABELS.get("tests_finished", "测试完成"),
                1, 1,
                phase="testing",
                **summary
            )

            if not result.success:
                self.warnings.append(f"测试失败: {result.logs[:200]}")
                self._report_progress(PROGRESS_LABELS["tests_failed_recovering"], 1, 1, phase="testing")

            return summary
        except Exception as e:
            logger.error(f"测试执行异常：{e}")
            return {"success": False, "message": str(e)}
        finally:
            metrics_collector.end_timer('TestingMixin', test_start, 'run_tests', {'test_count': len(test_files)})

    async def _select_tests(
        self,
        modified_files: Optional[List[str]],
        project_profile: Optional[ProjectProfile]
    ) -> List[str]:
        """智能测试选择"""
        if not modified_files or not project_profile:
            # 回退到全量测试
            return []

        try:
            # 分析变更
            analyzer = ImpactAnalyzer()
            changes = analyzer.analyze(modified_files)

            # 选择测试
            selector = TestSelector()
            test_files = selector.select_tests(changes, project_profile)

            logger.info(f"智能测试选择：{len(test_files)}/{len(self._collect_all_tests())} 个测试")
            return test_files
        except Exception as e:
            logger.error(f"测试选择失败，回退到全量测试：{e}")
            return []

    async def _cluster_test_failures(
        self,
        failed_tests: List[str],
        logs: str
    ) -> List[FailureCluster]:
        """测试失败聚类"""
        try:
            # 解析测试结果
            clusterer = FailureClusterer()
            test_results = []

            for test_name in failed_tests:
                # 从 logs 中提取 traceback
                import re
                pattern = rf"FAILED {test_name}.*?(?=FAILED|PASSED|ERROR|$)"
                match = re.search(pattern, logs, re.DOTALL)
                traceback = match.group(0) if match else ""

                test_results.append({
                    "name": test_name,
                    "traceback": traceback,
                    "error_message": traceback.split('\n')[-2] if traceback else ""
                })

            clusters = clusterer.cluster(test_results)
            logger.info(f"测试失败聚类：{len(clusters)} 个根因")
            return clusters
        except Exception as e:
            logger.error(f"测试失败聚类失败：{e}")
            return []

    def _detect_test_command(self, project_path: Path, test_files: Optional[List[str]] = None) -> str:
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding='utf-8'))
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    if test_files:
                        # 指定测试文件
                        files_str = ' '.join(test_files)
                        return f"cd /app && npm run test -- {files_str}"
                    return "cd /app && npm run test"
            except Exception as e:
                logger.debug(f"测试执行失败：{e}")

        playwright_config = (
            project_path / "playwright.config.js"
            or project_path / "playwright.config.ts"
        )
        if playwright_config.exists():
            if test_files:
                files_str = ' '.join(test_files)
                return f"cd /app && npx playwright test --reporter=list {files_str}"
            return "cd /app && npx playwright test --reporter=list"

        pytest_dir = project_path / "tests" or project_path / "test"
        if pytest_dir.exists() or list(project_path.glob("test_*.py")):
            if test_files:
                files_str = ' '.join(test_files)
                return f"cd /app && python -m pytest -v --tb=short -q --color=no {files_str}"
            return "cd /app && python -m pytest -v --tb=short -q --color=no"

        if test_files:
            files_str = ' '.join(test_files)
            return f"cd /app && python -m pytest -v --tb=short -q --color=no {files_str}"
        return "cd /app && python -m pytest -v --tb=short -q --color=no"

    def _collect_all_tests(self) -> List[str]:
        """收集所有测试文件"""
        test_files = []
        for pattern in ["test_*.py", "tests/**/*.py", "test/**/*.py", "**/*.test.js", "**/*.spec.js"]:
            test_files.extend(str(f) for f in self.output_dir.glob(pattern))
        return test_files

    async def _run_tests_in_docker(self, test_command: str) -> Optional[Dict[str, Any]]:
        try:
            from app.utils.docker_runner import (
                DockerRunner, DockerSecurityConfig,
                DOCKER_AVAILABLE, ValidationResult
            )
            from app.utils.service_container_manager import detect_project_services
        except ImportError:
            logger.info("DockerRunner 不可用，回退到本地 TestRunner")
            return None

        if not DOCKER_AVAILABLE:
            logger.info("Docker 库未安装，回退到本地 TestRunner")
            return None

        try:
            from app.agent.framework_detector import FrameworkDetector

            required_services = detect_project_services(self.output_dir)
            detected_config = FrameworkDetector().detect(self.output_dir)

            config = DockerSecurityConfig(
                network_enabled=len(required_services) > 0,
                remove=True
            )
            docker_runner = DockerRunner(config=config, timeout=120)

            req_path = self.output_dir / "requirements.txt"
            pkg_path = self.output_dir / "package.json"

            install_deps = req_path.exists() or pkg_path.exists()

            try:
                result: ValidationResult = await docker_runner.run_validation(
                    project_path=self.output_dir,
                    requirements_path=req_path if req_path.exists() else None,
                    test_command=test_command,
                    install_deps=install_deps,
                    auto_detect_framework=True,
                    required_services=required_services,
                )
            finally:
                try:
                    await docker_runner.cleanup()
                except Exception as e:
                    logger.debug(f"Docker 清理失败：{e}")

            summary = {
                "success": result.success,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": len(result.errors),
                "failed_tests": [],
                "logs_preview": "\n".join(result.logs[:50])[:1000],
                "method": "docker"
            }

            from app.agent.output_parser import OutputParser

            output_format = "pytest_xml"
            if detected_config:
                output_format = detected_config.output_format

            raw_output = "\n".join(result.logs)
            parsed = OutputParser.parse(raw_output, output_format)
            summary["passed"] = parsed.passed
            summary["failed"] = parsed.failed
            summary["total"] = parsed.passed + parsed.failed
            if parsed.errors:
                summary["errors"] = len(parsed.errors)
                summary["failed_tests"] = [e[:100] for e in parsed.errors[:20]]

            self._report_progress(
                PROGRESS_LABELS.get("tests_finished", "测试完成"),
                1, 1,
                phase="testing",
                **summary
            )

            if not result.success:
                self.warnings.append(f"Docker 测试失败: {result.error or 'exit_code=' + str(result.exit_code)}")
                self._report_progress(
                    PROGRESS_LABELS.get("tests_failed_recovering", "测试失败"),
                    1, 1, phase="testing"
                )

            logger.info(f"Docker 测试完成 | success={result.success} | 容器已自动释放")
            return summary

        except RuntimeError as e:
            logger.warning(f"Docker 不可用: {e}，回退到本地 TestRunner")
            return None
        except Exception as e:
            logger.error(f"Docker 测试异常: {e}，回退到本地 TestRunner")
            return None
