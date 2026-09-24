"""UtilsMixin._record_learning_data 学习样本与 file_type 测试（OU4 回归防线）。"""

import asyncio

from app.agent.error_recovery import FixAttempt
from app.agent.orchestrator_utils import UtilsMixin


class _RecordingLearner:
    def __init__(self):
        self.calls = []

    async def compute_error_embeddings(self, errors):
        return {}

    def record_fix(self, **kwargs):
        self.calls.append(kwargs)


class _ErrorRecovery:
    def __init__(self, history):
        self.fix_history = history


class _Host(UtilsMixin):
    def __init__(self, history):
        self.feedback_learner = _RecordingLearner()
        self.error_recovery = _ErrorRecovery(history)
        self.model_assignment = None

    def _is_frontend_file(self, file_path):
        return file_path.endswith((".js", ".ts", ".vue", ".tsx", ".jsx"))


def test_real_sample_content_is_recorded():
    history = [
        FixAttempt(
            file_path="web/app.js",
            error_type="syntax_error",
            error_message="unexpected token",
            fix_applied=True,
            attempts=1,
            original_content="const a = ;",
            fixed_content="const a = 1;",
        )
    ]
    host = _Host(history)

    asyncio.run(host._record_learning_data("req", {}, []))

    call = host.feedback_learner.calls[0]
    assert call["original_content"] == "const a = ;"
    assert call["fixed_content"] == "const a = 1;"


def test_file_type_is_inferred_from_extension():
    history = [
        FixAttempt(
            file_path="web/app.js",
            error_type="syntax_error",
            error_message="e",
            fix_applied=True,
            attempts=1,
        ),
        FixAttempt(
            file_path="app/main.py",
            error_type="syntax_error",
            error_message="e",
            fix_applied=True,
            attempts=1,
        ),
    ]
    host = _Host(history)

    asyncio.run(host._record_learning_data("req", {}, []))

    assert [c["file_type"] for c in host.feedback_learner.calls] == [
        "frontend",
        "backend",
    ]


def test_missing_content_degrades_to_empty_string():
    history = [
        FixAttempt(
            file_path="app/main.py",
            error_type="syntax_error",
            error_message="e",
            fix_applied=False,
            attempts=2,
        )
    ]
    host = _Host(history)

    asyncio.run(host._record_learning_data("req", {}, []))

    call = host.feedback_learner.calls[0]
    assert call["original_content"] == ""
    assert call["fixed_content"] == ""
