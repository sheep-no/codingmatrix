"""
output_dir 解析逻辑单元测试

修复：incremental 模式（前端传 project_path）原本被 Pydantic 静默丢弃，
后端走默认时间戳目录，导致 incremental 永远找不到原项目。
本测试验证：resolve_sync_output_dir / resolve_stream_output_dir 行为正确。
"""
from app.api.v1.ai_agent.orchestrate_endpoints import (
    resolve_sync_output_dir,
    resolve_stream_output_dir,
)


class TestResolveSyncOutputDir:
    """/orchestrate 端点 output_dir 解析"""

    def test_project_path_takes_priority(self):
        """project_path 优先级最高（incremental 模式）"""
        result = resolve_sync_output_dir(
            project_path="orchestrator/20260101_120000_1",
            output_dir="/tmp/old_path",
            user_id="1",
            timestamp="20260102_120000",
        )
        assert result == "orchestrator/20260101_120000_1"

    def test_fallback_to_request_output_dir(self):
        """project_path 缺失时用 request.output_dir"""
        result = resolve_sync_output_dir(
            project_path=None,
            output_dir="/workspace/projects/orchestrator/manual_path",
            user_id="1",
            timestamp="20260102_120000",
        )
        assert result == "/workspace/projects/orchestrator/manual_path"

    def test_fallback_to_timestamp_dir(self):
        """都没传时用时间戳目录"""
        result = resolve_sync_output_dir(
            project_path=None,
            output_dir=None,
            user_id="42",
            timestamp="20260102_120000",
        )
        assert result == "./projects/orchestrator/20260102_120000_42"

    def test_empty_string_project_path_treated_as_none(self):
        """空字符串 project_path 应当被当作 None（不覆盖）"""
        result = resolve_sync_output_dir(
            project_path="",
            output_dir="/tmp/fallback",
            user_id="1",
            timestamp="20260102_120000",
        )
        assert result == "/tmp/fallback"


class TestResolveStreamOutputDirIncremental:
    """/orchestrate/stream 端点 - 增量模式 (project_path)"""

    def test_project_path_with_explicit_session_id(self):
        """project_path + 显式 session_id 应当都用"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path="orchestrator/20260101_120000_1",
            session_id="1_my_incremental",
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "orchestrator/20260101_120000_1"
        assert project_name == "20260101_120000_1"
        assert session_id == "1_my_incremental"

    def test_project_path_derives_session_id(self):
        """project_path 不传 session_id 时应当自动派生"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path="users/1/myproject",
            session_id=None,
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "users/1/myproject"
        assert project_name == "myproject"
        assert session_id == "1_myproject"

    def test_project_path_nested_path_uses_last_segment(self):
        """嵌套路径应当用最后一段当 project_name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path="a/b/c/deep-project-name",
            session_id=None,
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert project_name == "deep-project-name"
        assert session_id == "1_deep-project-name"

    def test_incremental_with_old_timestamp_format(self):
        """增量模式兼容旧的时间戳目录格式"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path="orchestrator/20260101_120000_1",
            session_id=None,
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "orchestrator/20260101_120000_1"
        assert project_name == "20260101_120000_1"


class TestResolveStreamOutputDirSessionResume:
    """/orchestrate/stream 端点 - 续传模式 (session_id)"""

    def test_session_id_with_user_id_prefix(self):
        """session_id 带 user_id_ 前缀时正确提取 project_name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path=None,
            session_id="1_myproject",
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "1/myproject"
        assert project_name == "myproject"
        assert session_id == "1_myproject"

    def test_session_id_without_user_id_prefix(self):
        """session_id 不带 user_id_ 前缀时整段当 project_name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path=None,
            session_id="orphan_session",
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "1/orphan_session"
        assert project_name == "orphan_session"

    def test_session_id_with_different_user_prefix(self):
        """user_id 不在 session_id 开头时整段当 name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path=None,
            session_id="otheruser_something",
            project_name=None,
            user_id="1",
            timestamp="20260204_120000",
        )
        assert project_name == "otheruser_something"
        assert output_dir == "1/otheruser_something"


class TestResolveStreamOutputDirNewProject:
    """/orchestrate/stream 端点 - 全新生成"""

    def test_explicit_project_name(self):
        """用户指定 project_name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path=None,
            session_id=None,
            project_name="my-shop",
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "1/my-shop"
        assert project_name == "my-shop"
        assert session_id == "1_my-shop"

    def test_auto_generate_project_name(self):
        """无 project_name 时用时间戳生成 untitled_*"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path=None,
            session_id=None,
            project_name=None,
            user_id="42",
            timestamp="20260204_120000",
        )
        assert project_name == "untitled_20260204_120000"
        assert output_dir == "42/untitled_20260204_120000"
        assert session_id == "42_untitled_20260204_120000"


class TestResolveStreamPriorityOrder:
    """/orchestrate/stream 端点 - 优先级"""

    def test_project_path_beats_session_id(self):
        """project_path 优先于 session_id"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path="explicit/path",
            session_id="should_be_ignored",
            project_name="ignored",
            user_id="1",
            timestamp="20260204_120000",
        )
        assert output_dir == "explicit/path"
        assert project_name == "path"

    def test_project_path_beats_explicit_project_name(self):
        """project_path 优先于 project_name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path="explicit/path",
            session_id=None,
            project_name="ignored",
            user_id="1",
            timestamp="20260204_120000",
        )
        assert project_name == "path"

    def test_session_id_beats_project_name(self):
        """session_id 优先于 project_name"""
        output_dir, project_name, session_id = resolve_stream_output_dir(
            project_path=None,
            session_id="1_existing",
            project_name="ignored",
            user_id="1",
            timestamp="20260204_120000",
        )
        assert project_name == "existing"
        assert output_dir == "1/existing"
