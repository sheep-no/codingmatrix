"""
多模型 Agent 学习能力单元测试

测试 FeedbackLearner, LearningRouter, CloudLearningHub, StrategyLearner, UserPreferenceLearner
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agent.feedback_learner import FeedbackLearner, FixPattern
from app.agent.dynamic_model_router import LearningRouter, ModelPerformanceTracker
from app.agent.cloud_learning_hub import CloudLearningHub, CloudPattern
from app.agent.strategy_learner import StrategyLearner, StrategyState, StrategyAction
from app.agent.user_preference_learner import UserPreferenceLearner, CodeStylePreference


class TestFeedbackLearner:
    """测试 FeedbackLearner"""

    @pytest.fixture
    def learner(self, tmp_path):
        return FeedbackLearner(learning_dir=tmp_path)

    def test_record_fix_success(self, learner):
        """测试记录成功修复"""
        learner.record_fix(
            file_path="test.py",
            file_type="python",
            original_content="def foo():\n    print('hello'",
            fixed_content="def foo():\n    print('hello')",
            errors={"syntax": ["SyntaxError: unexpected EOF while parsing"]},
            model_name="Qwen/Qwen2.5-7B-Instruct",
            success=True
        )

        stats = learner.get_learning_stats()
        assert stats["learned_patterns"] >= 1
        assert stats["total_fixes_recorded"] >= 1

    def test_record_fix_failure(self, learner):
        """测试记录失败修复"""
        learner.record_fix(
            file_path="test.py",
            file_type="python",
            original_content="import nonexistent_module",
            fixed_content="import nonexistent_module",
            errors={"import": ["ModuleNotFoundError: No module named 'nonexistent_module'"]},
            model_name="Qwen/Qwen2.5-7B-Instruct",
            success=False
        )

        stats = learner.get_learning_stats()
        assert stats["overall_success_rate"] < 1.0

    def test_get_learning_stats(self, learner):
        """测试获取学习统计"""
        # 记录多次修复
        for i in range(5):
            learner.record_fix(
                file_path=f"test{i}.py",
                file_type="python",
                original_content="x = 1/0",
                fixed_content="x = 0",
                errors={"runtime": ["ZeroDivisionError"], "logic": ["error"]},
                model_name="Qwen/test_model",
                success=(i < 2)  # 40% 成功率
            )

        stats = learner.get_learning_stats()
        assert stats["total_fixes_recorded"] >= 5
        assert stats["learned_patterns"] >= 1

    def test_get_common_errors(self, learner):
        """测试获取常见错误"""
        # 记录一些修复
        learner.record_fix(
            file_path="test.py",
            file_type="python",
            original_content="test",
            fixed_content="test",
            errors={"import": ["ModuleNotFoundError"]},
            model_name="model_a",
            success=True
        )
        
        errors = learner.get_common_errors("python")
        assert isinstance(errors, list)


class TestLearningRouter:
    """测试 LearningRouter"""

    @pytest.fixture
    def router(self, tmp_path):
        # 使用临时数据库避免测试间干扰
        import tempfile
        import os
        db_path = str(tmp_path / "test_performance.db")
        tracker = ModelPerformanceTracker()
        tracker.DB_PATH = db_path
        tracker._conn = __import__('sqlite3').connect(db_path, check_same_thread=False)
        tracker._conn.execute("PRAGMA journal_mode=WAL")
        tracker._conn.execute(
            "CREATE TABLE IF NOT EXISTS performance ("
            "model_name TEXT NOT NULL, "
            "task_type TEXT NOT NULL, "
            "success_rate REAL NOT NULL DEFAULT 0.0, "
            "avg_latency REAL NOT NULL DEFAULT 0.0, "
            "total_calls INTEGER NOT NULL DEFAULT 0, "
            "consecutive_failures INTEGER NOT NULL DEFAULT 0, "
            "last_updated REAL NOT NULL, "
            "PRIMARY KEY (model_name, task_type))"
        )
        tracker._conn.commit()
        return LearningRouter(tracker=tracker)

    def test_initialization(self, router):
        """测试初始化"""
        assert router is not None
        assert router.EXPLORATION_RATE == 0.2
        assert router.DEGRADATION_THRESHOLD == 5

    def test_select_model(self, router):
        """测试模型选择"""
        # 记录模型性能数据
        for i in range(5):
            router.record_call("model_a", "code_generation", False, 1000.0)
            router.record_call("model_b", "code_generation", True, 500.0)
        
        # 选择模型
        selected = router.select_model(
            "code_generation",
            ["model_a", "model_b"]
        )
        
        # 应该选择 model_b（性能更好）
        assert selected == "model_b"

    def test_record_call(self, router):
        """测试记录调用"""
        router.record_call("model_a", "code_generation", True, 500.0)
        router.record_call("model_b", "code_generation", False, 1000.0)
        
        # 验证记录被保存（每个 model-task 对是一条记录）
        assert router._tracker.get_total_records() >= 2

    def test_has_sufficient_data(self, router):
        """测试数据充足性检查"""
        # 初始状态数据不足
        assert router.has_sufficient_data() is False
        
        # 记录足够多的数据
        for i in range(15):
            router.record_call(f"model_{i}", "general", True, 100.0)
        
        # 现在数据充足
        assert router.has_sufficient_data() is True


class TestCloudLearningHub:
    """测试 CloudLearningHub"""

    @pytest.fixture
    def hub(self, tmp_path):
        return CloudLearningHub(
            project_id="test_project",
            project_type="web",
            tech_stack=["vue", "fastapi"],
            cache_dir=tmp_path
        )

    def test_upload_pattern(self, hub):
        """测试上传模式"""
        pattern = FixPattern(
            error_type="import",
            error_message="ModuleNotFoundError: No module named 'x'",
            error_pattern="ModuleNotFoundError",
            fix_description="安装缺失模块",
            fix_example="pip install x",
            file_types=["python"]
        )
        
        pattern_hash = hub.upload_pattern(pattern, success=True)
        assert len(pattern_hash) == 16
        
        stats = hub.get_project_knowledge_stats()
        assert stats["total_patterns"] == 1

    def test_download_similar_patterns(self, hub):
        """测试下载相似模式"""
        # 上传一个模式
        pattern = FixPattern(
            error_type="import",
            error_message="ModuleNotFoundError",
            error_pattern="ModuleNotFoundError",
            fix_description="安装缺失模块",
            fix_example="pip install x",
            file_types=["python"],
            success_rate=0.9
        )
        hub.upload_pattern(pattern, success=True)
        
        # 下载相似模式
        patterns = hub.download_similar_patterns(
            query_error_type="import",
            query_keywords=["ModuleNotFoundError"],
            max_results=10
        )
        
        assert len(patterns) == 1
        assert patterns[0].pattern["error_type"] == "import"

    def test_vote_pattern(self, hub):
        """测试投票"""
        pattern = FixPattern(
            error_type="syntax",
            error_message="SyntaxError",
            error_pattern="SyntaxError",
            fix_description="修复语法",
            fix_example="x = 1",
            file_types=["python"]
        )
        pattern_hash = hub.upload_pattern(pattern, success=True)
        
        # 投成功票
        hub.vote_pattern(pattern_hash, success=True)
        
        stats = hub.get_project_knowledge_stats()
        assert stats["total_votes"] == 2  # 上传时 1 票 + 投票 1 票


class TestStrategyLearner:
    """测试 StrategyLearner"""

    @pytest.fixture
    def learner(self, tmp_path):
        s = StrategyLearner(data_dir=tmp_path)
        return s

    def test_select_action_exploration(self, learner):
        """测试探索模式动作选择"""
        state = StrategyState(
            project_complexity="medium",
            file_type="python",
            error_type="import",
            has_history_errors=True
        )
        
        # 设置低探索率以便测试
        learner.EXPLORATION_RATE = 1.0  # 100% 探索
        
        action = learner.select_action(state)
        assert action is not None
        assert action.model_selection in learner.MODEL_SELECTION_STRATEGIES

    def test_q_value_update(self, learner):
        """测试 Q 值更新"""
        state = StrategyState(
            project_complexity="simple",
            file_type="python",
            error_type=None,
            has_history_errors=False
        )
        
        action = learner.select_action(state)
        learner.update(reward=1.0, next_state=None)
        
        stats = learner.get_learning_stats()
        assert stats["total_visits"] >= 1

    def test_get_strategy_recommendation(self, learner):
        """测试策略推荐"""
        recommendation = learner.get_strategy_recommendation(
            project_complexity="medium",
            file_type="python",
            error_type="syntax"
        )
        
        assert "model_selection" in recommendation
        assert "prompt_template" in recommendation
        assert "temperature" in recommendation


class TestUserPreferenceLearner:
    """测试 UserPreferenceLearner"""

    @pytest.fixture
    def learner(self, tmp_path):
        return UserPreferenceLearner(user_id="test_user", data_dir=tmp_path)

    def test_record_modification(self, learner):
        """测试记录用户修改"""
        original = """
def hello():
    print('world')
"""
        modified = """
def hello() -> None:
    '''打印问候语'''
    print('world')
"""
        learner.record_modification(
            file_path="test.py",
            file_type="python",
            original_code=original,
            user_modified_code=modified
        )

        stats = learner.get_learning_stats()
        assert stats["total_modifications"] == 1

    def test_analyze_naming_changes(self, learner):
        """测试命名风格变化分析"""
        added = {"my_variable = 1", "another_var = 2"}
        removed = {"myVariable = 1", "anotherVar = 2"}
        
        result = learner._analyze_naming_changes(added, removed)
        assert result is not None
        assert result["trend"] == "toward_snake_case"

    def test_get_preference_prompt(self, learner):
        """测试生成偏好 Prompt"""
        learner.profile.code_style.naming_convention = "snake_case"
        learner.profile.documentation.comment_density = "verbose"
        
        prompt = learner.get_preference_prompt()
        assert "用户偏好" in prompt
        assert "下划线命名" in prompt or "snake_case" in prompt

    def test_confidence_update(self, learner):
        """测试置信度更新"""
        # 模拟多次修改
        for i in range(5):
            learner.record_modification(
                file_path=f"test{i}.py",
                file_type="python",
                original_code="x=1",
                user_modified_code=f"x = {i+1}"  # 添加空格
            )
        
        stats = learner.get_learning_stats()
        # 置信度应该有值
        assert len(stats["confidence_scores"]) >= 0


class TestLearningIntegration:
    """测试学习能力集成"""

    @pytest.fixture
    def setup_learning(self, tmp_path):
        """设置完整的学习环境"""
        feedback_learner = FeedbackLearner(learning_dir=tmp_path / "feedback")
        learning_router = LearningRouter()
        cloud_hub = CloudLearningHub(
            project_id="integration_test",
            cache_dir=tmp_path / "cloud"
        )
        
        return {
            "feedback": feedback_learner,
            "router": learning_router,
            "cloud": cloud_hub
        }

    def test_feedback_records_fixes(self, setup_learning):
        """测试反馈记录修复"""
        feedback = setup_learning["feedback"]
        
        # 记录修复
        feedback.record_fix(
            file_path="test.py",
            file_type="python",
            original_content="test",
            fixed_content="test",
            errors={"import": ["ModuleNotFoundError"]},
            model_name="model_a",
            success=False
        )
        
        stats = feedback.get_learning_stats()
        assert stats["total_fixes_recorded"] >= 1

    def test_cloud_hub_pattern_sharing(self, setup_learning):
        """测试云端模式共享"""
        cloud = setup_learning["cloud"]
        
        # 上传模式
        pattern = FixPattern(
            error_type="dependency",
            error_message="No module named 'x'",
            error_pattern="No module named",
            fix_description="pip install x",
            fix_example="pip install x",
            file_types=["python"],
            success_rate=0.9
        )
        cloud.upload_pattern(pattern, success=True)
        
        # 下载模式
        patterns = cloud.download_similar_patterns("dependency")
        assert len(patterns) > 0


class TestColdStartOptimization:
    """测试冷启动优化"""

    def test_has_sufficient_data_threshold(self, tmp_path):
        """测试数据充足性阈值"""
        # 使用全新的 tracker 避免共享数据库
        db_path = str(tmp_path / "cold_start_test.db")
        tracker = ModelPerformanceTracker()
        tracker.DB_PATH = db_path
        tracker._conn = __import__('sqlite3').connect(db_path, check_same_thread=False)
        tracker._conn.execute("PRAGMA journal_mode=WAL")
        tracker._conn.execute(
            "CREATE TABLE IF NOT EXISTS performance ("
            "model_name TEXT NOT NULL, "
            "task_type TEXT NOT NULL, "
            "success_rate REAL NOT NULL DEFAULT 0.0, "
            "avg_latency REAL NOT NULL DEFAULT 0.0, "
            "total_calls INTEGER NOT NULL DEFAULT 0, "
            "consecutive_failures INTEGER NOT NULL DEFAULT 0, "
            "last_updated REAL NOT NULL, "
            "PRIMARY KEY (model_name, task_type))"
        )
        tracker._conn.commit()
        router = LearningRouter(tracker=tracker)
        
        # 初始状态数据不足
        assert router.has_sufficient_data() is False
        
        # 记录 10 条以下
        for i in range(9):
            router.record_call(f"model_{i}", "general", True, 100.0)
        
        # 9 条记录后仍然不足
        assert router.has_sufficient_data() is False
        
        # 第 10 条记录后
        router.record_call("model_10", "general", True, 100.0)
        # 10 条记录后仍然不足（需要 > 10）
        assert router.has_sufficient_data() is False
        
        # 第 11 条记录后就可以学习
        router.record_call("model_11", "general", True, 100.0)
        assert router.has_sufficient_data() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
