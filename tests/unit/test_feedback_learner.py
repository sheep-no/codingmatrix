import pytest
import asyncio

class TestFeedbackLearner:
    @pytest.fixture
    def learner(self):
        from app.agent.feedback_learner import FeedbackLearner
        return FeedbackLearner()
    
    def test_record_fix(self, learner):
        learner.record_fix(
            file_path="test.py",
            file_type="backend",
            original_content="old",
            fixed_content="new",
            errors={"validation_error": ["error1"]},
            model_name="test-model",
            success=True
        )
        
        assert len(learner._session_records) == 1
    
    def test_compute_error_embeddings(self, learner):
        errors = ["error1", "error2", "error3"]
        embeddings = asyncio.run(learner.compute_error_embeddings(errors))
        assert isinstance(embeddings, dict)
    
    def test_get_prevention_prompt(self, learner):
        learner.record_fix(
            file_path="test.py",
            file_type="backend",
            original_content="old",
            fixed_content="new",
            errors={"validation_error": ["error1"]},
            model_name="test-model",
            success=True
        )
        
        prompt = asyncio.run(learner.get_prevention_prompt(
            file_path="test.py",
            file_type="backend",
            project_context={}
        ))
        assert prompt is not None
