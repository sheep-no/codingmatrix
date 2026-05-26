"""
v4.8.0 新功能测试 - REQ-1 到 REQ-4
"""
import pytest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime


class TestCrossFileDependencyAnalysis:
    """REQ-1: 跨文件依赖分析测试"""

    @pytest.fixture
    def dep_graph(self):
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        dg.add_file('models.py')
        dg.add_file('services.py')
        dg.add_file('api.py')
        dg.add_file('utils.py')
        dg.add_dependency('services.py', 'models.py')
        dg.add_dependency('api.py', 'services.py')
        dg.add_dependency('api.py', 'utils.py')
        return dg

    def test_get_affected_files_direct(self, dep_graph):
        """测试直接依赖检测"""
        affected = dep_graph.get_affected_files(['models.py'])
        assert 'services.py' in affected['models.py']

    def test_get_affected_files_transitive(self, dep_graph):
        """测试传递依赖检测 (models -> services -> api)"""
        affected = dep_graph.get_affected_files(['models.py'])
        assert 'api.py' in affected['models.py']
        assert 'services.py' in affected['models.py']

    def test_get_affected_files_multiple_changes(self, dep_graph):
        """测试多文件变更"""
        affected = dep_graph.get_affected_files(['models.py', 'utils.py'])
        assert 'services.py' in affected['models.py']
        assert 'api.py' in affected['utils.py']
        assert 'api.py' in affected['models.py']

    def test_get_affected_files_no_dependents(self, dep_graph):
        """测试无下游依赖的文件"""
        affected = dep_graph.get_affected_files(['api.py'])
        assert len(affected['api.py']) == 0

    def test_max_depth_limit(self):
        """测试最大深度限制"""
        from app.agent.dependency_graph import DependencyGraph
        dg = DependencyGraph()
        for i in range(15):
            dg.add_file(f'file_{i}.py')
        if i > 0:
            dg.add_dependency(f'file_{i}.py', f'file_{i-1}.py')

        result = dg._get_transitive_dependents('file_0.py', max_depth=5)
        assert len(result) <= 6


class TestFrameworkDetector:
    """REQ-2: 测试框架自动检测"""

    @pytest.fixture
    def temp_project(self):
        project_dir = Path(tempfile.mkdtemp())
        yield project_dir
        shutil.rmtree(project_dir)

    def test_detect_python_pytest(self, temp_project):
        """测试检测 Python pytest 项目"""
        from app.agent.framework_detector import FrameworkDetector
        (temp_project / "requirements.txt").write_text("pytest\nflask\n")
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.language == "python"
        assert config.framework == "pytest"

    def test_detect_javascript_jest(self, temp_project):
        """测试检测 JavaScript Jest 项目"""
        from app.agent.framework_detector import FrameworkDetector
        pkg = {"devDependencies": {"jest": "^29.0"}, "scripts": {"test": "jest"}}
        (temp_project / "package.json").write_text(json.dumps(pkg))
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.language == "javascript"
        assert config.framework == "jest"

    def test_detect_java_maven(self, temp_project):
        """测试检测 Java Maven 项目"""
        from app.agent.framework_detector import FrameworkDetector
        (temp_project / "pom.xml").write_text("<project></project>")
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.language == "java"
        assert config.framework == "maven"

    def test_detect_go_test(self, temp_project):
        """测试检测 Go 测试项目"""
        from app.agent.framework_detector import FrameworkDetector
        (temp_project / "go.mod").write_text("module example\n")
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.language == "go"
        assert config.framework == "go_test"

    def test_detect_rust_cargo(self, temp_project):
        """测试检测 Rust Cargo 项目"""
        from app.agent.framework_detector import FrameworkDetector
        (temp_project / "Cargo.toml").write_text("[package]\nname = \"test\"\n")
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.language == "rust"
        assert config.framework == "cargo"

    def test_detect_cpp_make(self, temp_project):
        """测试检测 C++ Make 项目"""
        from app.agent.framework_detector import FrameworkDetector
        (temp_project / "Makefile").write_text("test:\n\t./run_tests\n")
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.language == "cpp"
        assert config.framework == "make"

    def test_detect_default_pytest(self, temp_project):
        """测试默认 pytest fallback"""
        from app.agent.framework_detector import FrameworkDetector
        fd = FrameworkDetector()
        config = fd.detect(temp_project)
        assert config.framework == "pytest"

    def test_framework_presets_count(self):
        """测试框架预设数量"""
        from app.agent.test_framework_config import FRAMEWORK_PRESETS
        assert len(FRAMEWORK_PRESETS) == 6


class TestOutputParser:
    """REQ-2: 测试输出解析"""

    def test_parse_pytest_output(self):
        """测试解析 pytest 输出"""
        from app.agent.output_parser import OutputParser
        output = "test_api.py::test_login PASSED\ntest_api.py::test_logout FAILED\n2 passed, 1 failed"
        result = OutputParser.parse(output, "pytest_xml")
        assert result.passed == 2
        assert result.failed == 1

    def test_parse_go_test_output(self):
        """测试解析 Go test 输出"""
        from app.agent.output_parser import OutputParser
        output = "--- PASS: TestAdd (0.00s)\n--- FAIL: TestSub (0.00s)\nPASS\nFAIL"
        result = OutputParser.parse(output, "go_json")
        assert result.passed == 1
        assert result.failed == 1

    def test_parse_rust_test_output(self):
        """测试解析 Rust cargo test 输出"""
        from app.agent.output_parser import OutputParser
        output = "running 3 tests\ntest test_add ... ok\ntest test_sub ... FAILED\n2 passed, 1 failed"
        result = OutputParser.parse(output, "rust_text")
        assert result.passed == 2
        assert result.failed == 1

    def test_parse_generic_output(self):
        """测试通用解析器 fallback"""
        from app.agent.output_parser import OutputParser
        output = "5 passed, 2 failed, ERROR: something went wrong"
        result = OutputParser.parse(output, "unknown_format")
        assert result.passed == 5
        assert result.failed == 2
        assert len(result.errors) > 0

    def test_parse_empty_output(self):
        """测试空输出"""
        from app.agent.output_parser import OutputParser
        result = OutputParser.parse("", "pytest_xml")
        assert result.passed == 0
        assert result.failed == 0


class TestDynamicChunker:
    """REQ-4 Part A: 动态分片测试"""

    def test_default_chunk_size(self):
        """测试默认分片大小"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
        assert chunker.get_chunk_size() == 5 * 1024 * 1024

    def test_adjust_increase_on_fast_upload(self):
        """测试快速上传时增大分片"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
  # 5MB in 0.3s = ~16.7MB/s (fast)
        chunker.adjust_chunk_size(0.3, 5 * 1024 * 1024)
        assert chunker.get_chunk_size() > 5 * 1024 * 1024

    def test_adjust_decrease_on_slow_upload(self):
        """测试慢速上传时缩小分片"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
  # 5MB in 5s = 1MB/s (slow)
        chunker.adjust_chunk_size(5.0, 5 * 1024 * 1024)
        assert chunker.get_chunk_size() < 5 * 1024 * 1024

    def test_failure_threshold_reduces_to_min(self):
        """测试连续失败 3 次降至最小分片"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
        chunker.on_upload_failure()
        chunker.on_upload_failure()
        chunker.on_upload_failure()
        assert chunker.get_chunk_size() == DynamicChunker.MIN_CHUNK_SIZE

    def test_success_resets_failures(self):
        """测试成功后重置失败计数"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
        chunker.on_upload_failure()
        chunker.on_upload_failure()
        chunker.on_upload_success()
        assert chunker.consecutive_failures == 0

    def test_max_chunk_size_cap(self):
        """测试最大分片上限"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
        chunker.current_chunk_size = 40 * 1024 * 1024
  # Very fast upload
        chunker.adjust_chunk_size(0.1, 40 * 1024 * 1024)
        assert chunker.get_chunk_size() <= DynamicChunker.MAX_CHUNK_SIZE

    def test_reset(self):
        """测试重置所有状态"""
        from app.utils.dynamic_chunker import DynamicChunker
        chunker = DynamicChunker()
        chunker.adjust_chunk_size(0.1, 5 * 1024 * 1024)
        chunker.on_upload_failure()
        chunker.reset()
        assert chunker.get_chunk_size() == DynamicChunker.DEFAULT_CHUNK_SIZE
        assert chunker.consecutive_failures == 0


class TestResumeManager:
    """REQ-4 Part A: 断点续传测试"""

    @pytest.fixture
    def resume_mgr(self):
        from app.utils.resume_manager import ResumeManager
        temp_dir = Path(tempfile.mkdtemp())
        mgr = ResumeManager(resume_dir=temp_dir)
        yield mgr
        shutil.rmtree(temp_dir)

    def test_save_and_get_state(self, resume_mgr):
        """测试保存和获取状态"""
        import asyncio
        asyncio.run(resume_mgr.save_chunk_state("test_upload", 0, "hash0"))
        asyncio.run(resume_mgr.save_chunk_state("test_upload", 1, "hash1"))

        state = asyncio.run(resume_mgr.get_resume_state("test_upload", 5))
        assert 0 in state.completed_chunks
        assert 1 in state.completed_chunks
        assert state.next_chunk_index == 2

    def test_empty_resume_state(self, resume_mgr):
        """测试空状态"""
        import asyncio
        state = asyncio.run(resume_mgr.get_resume_state("nonexistent", 10))
        assert len(state.completed_chunks) == 0
        assert state.next_chunk_index == 0

    def test_clear_state(self, resume_mgr):
        """测试清除状态"""
        import asyncio
        asyncio.run(resume_mgr.save_chunk_state("test_clear", 0, "hash0"))
        asyncio.run(resume_mgr.clear_state("test_clear"))
        state = asyncio.run(resume_mgr.get_resume_state("test_clear", 10))
        assert len(state.completed_chunks) == 0


class TestConcurrentLimitManager:
    """REQ-4 Part B: 并发限制动态管理测试"""

    @pytest.fixture
    def limit_mgr(self):
        from app.utils.dynamic_concurrent import ConcurrentLimitManager
        return ConcurrentLimitManager()

    def test_default_limits(self, limit_mgr):
        """测试默认限制值"""
        assert limit_mgr.get_limit("free") == 1
        assert limit_mgr.get_limit("premium") == 5

    def test_can_create_session(self, limit_mgr):
        """测试会话创建判断"""
        assert limit_mgr.can_create_session("free") is True
        limit_mgr.register_session("free")
        assert limit_mgr.can_create_session("free") is False

    def test_gradual_enforcement(self, limit_mgr):
        """测试渐进式生效：降低限制后已有会话继续"""
        import asyncio
        limit_mgr.register_session("premium")
        limit_mgr.register_session("premium")
        limit_mgr.register_session("premium")

        asyncio.run(limit_mgr.update_limit("premium", 1, "admin"))
  # 3 active, new limit 1 -> cannot create new
        assert limit_mgr.can_create_session("premium") is False
  # 但活跃会话仍然存在
        assert limit_mgr.get_active_count("premium") == 3

    def test_unregister_session(self, limit_mgr):
        """测试注销会话"""
        limit_mgr.register_session("basic")
        assert limit_mgr.get_active_count("basic") == 1
        limit_mgr.unregister_session("basic")
        assert limit_mgr.get_active_count("basic") == 0

    def test_audit_log(self, limit_mgr):
        """测试审计日志"""
        import asyncio
        asyncio.run(limit_mgr.update_limit("free", 3, "admin", "test reason"))
        history = limit_mgr.get_change_history()
        assert len(history) == 1
        assert history[0].old_limit == 1
        assert history[0].new_limit == 3
        assert history[0].changed_by == "admin"


class TestGitOperationsUnit:
    """REQ-3: Git 操作单元测试（不依赖真实 git）"""

    def test_snapshot_info_creation(self):
        """测试 SnapshotInfo 创建"""
        from app.agent.git_operations import SnapshotInfo
        info = SnapshotInfo(
        tag="agent-123-120000",
        commit_hash="abc123",
        message="test commit",
        timestamp="2026-05-15T12:00:00",
        )
        assert info.tag == "agent-123-120000"
        assert info.commit_hash == "abc123"

    def test_rollback_result_creation(self):
        """测试 RollbackResult 创建"""
        from app.agent.snapshot_manager import RollbackResult
        result = RollbackResult(
        success=True,
        previous_tag="v1",
        current_tag="v2",
        )
        assert result.success is True

    def test_finalize_result_creation(self):
        """测试 FinalizeResult 创建"""
        from app.agent.snapshot_manager import FinalizeResult
        result = FinalizeResult(
        merged=True,
        final_tag="agent-123-final",
        branch_deleted=True,
        )
        assert result.merged is True
        assert result.final_tag == "agent-123-final"