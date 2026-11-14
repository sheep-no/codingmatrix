"""FeedbackLearner 边界补测：向量匹配、反模式、持久化失败与裁剪。"""

import asyncio
import json

import pytest

from app.agent.feedback_learner import MAX_SESSION_RECORDS, FeedbackLearner, FixPattern


@pytest.fixture
def learner(tmp_path):
    return FeedbackLearner(learning_dir=tmp_path)


class _EmbeddingStub:
    def __init__(self, mapping=None, error=None):
        self.mapping = mapping or {}
        self.error = error
        self.calls = []

    async def __call__(self, text):
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return self.mapping.get(text, [0.0, 0.0])


def _pattern(**overrides):
    values = dict(
        error_type="syntax",
        error_message="boom",
        error_pattern="boom",
        fix_description="修复",
        fix_example="",
        file_types=[".py"],
    )
    values.update(overrides)
    return FixPattern(**values)


def test_cosine_similarity_delegates():
    assert FeedbackLearner._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_record_fix_skips_empty_error_lists(learner):
    learner.record_fix(
        file_path="a.py",
        file_type="backend",
        original_content="a",
        fixed_content="b",
        errors={"syntax": []},
        model_name="m",
        success=True,
    )

    assert learner._fix_patterns == {}
    assert len(learner._session_records) == 1


def test_record_fix_uses_provided_embedding(learner):
    learner.record_fix(
        file_path="a.py",
        file_type="backend",
        original_content="a",
        fixed_content="b",
        errors={"syntax": ["boom"]},
        model_name="m",
        success=True,
        error_embeddings={"boom": [0.1, 0.2]},
    )

    pattern = learner._fix_patterns["syntax:boom"]
    assert pattern.error_embedding == [0.1, 0.2]
    assert learner._error_vectors["syntax:boom"] == [0.1, 0.2]


def test_record_fix_reuses_existing_vector(learner):
    learner._error_vectors["syntax:boom"] = [0.3, 0.4]

    learner.record_fix(
        file_path="a.py",
        file_type="backend",
        original_content="a",
        fixed_content="b",
        errors={"syntax": ["boom"]},
        model_name="m",
        success=True,
    )

    assert learner._fix_patterns["syntax:boom"].error_embedding == [0.3, 0.4]


def test_record_fix_updates_failure_branch(learner):
    learner.record_fix(
        file_path="a.py",
        file_type="backend",
        original_content="a",
        fixed_content="b",
        errors={"syntax": ["boom"]},
        model_name="m",
        success=True,
    )
    learner.record_fix(
        file_path="a.py",
        file_type="backend",
        original_content="a",
        fixed_content="b",
        errors={"syntax": ["boom"]},
        model_name="m",
        success=False,
    )

    pattern = learner._fix_patterns["syntax:boom"]
    assert pattern.frequency == 2
    assert pattern.failed_count == 1
    assert pattern.last_failed_at is not None
    assert pattern.failure_reason == "boom"
    assert pattern.success_rate == pytest.approx(0.5)


def test_session_records_are_trimmed(learner, monkeypatch):
    monkeypatch.setattr("app.agent.feedback_learner.MAX_SESSION_RECORDS", 3)
    for _ in range(5):
        learner.record_fix(
            file_path="a.py",
            file_type="backend",
            original_content="a",
            fixed_content="b",
            errors={},
            model_name="m",
            success=True,
        )

    assert len(learner._session_records) == 3


def test_get_prevention_prompt_embedding_failure_degrades(learner, monkeypatch):
    monkeypatch.setattr(
        "app.utils.AiCodeUtil.get_embedding", _EmbeddingStub(error=RuntimeError("down"))
    )

    prompt = asyncio.run(
        learner.get_prevention_prompt("a.py", "backend", {}, error_context="stack")
    )

    assert prompt == ""


def test_get_prevention_prompt_uses_vector_similarity(learner, monkeypatch):
    stub = _EmbeddingStub({"error context: boom": [1.0, 0.0]})
    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", stub)
    learner._fix_patterns["syntax:boom"] = _pattern(
        error_embedding=[1.0, 0.0], success_rate=0.9, frequency=2
    )
    learner._fix_patterns["syntax:low"] = _pattern(
        error_embedding=[0.0, 1.0], success_rate=0.9, frequency=2
    )

    prompt = asyncio.run(
        learner.get_prevention_prompt("a.py", "backend", {}, error_context="boom")
    )

    assert "历史修复经验" in prompt
    assert len(stub.calls) == 1


def test_vector_search_skips_low_success_anti_and_low_similarity(learner):
    learner._fix_patterns = {
        "low_success": _pattern(error_embedding=[1.0, 0.0], success_rate=0.2),
        "anti": _pattern(
            error_embedding=[1.0, 0.0], success_rate=0.1, failed_count=5
        ),
        "disjoint": _pattern(error_embedding=[0.0, 1.0], success_rate=0.9),
        "missing": _pattern(error_embedding=None, success_rate=0.9),
        "match": _pattern(error_embedding=[1.0, 0.0], success_rate=0.9),
    }

    results = asyncio.run(
        learner._find_relevant_patterns_async("a.py", "backend", [1.0, 0.0])
    )

    assert [p.fix_description for p in results] == ["修复"]
    assert len(results) == 1


def test_frequency_search_filters_and_orders(learner):
    learner._fix_patterns = {
        "rare": _pattern(frequency=1, success_rate=0.9, file_types=[".py"]),
        "wrong_type": _pattern(frequency=3, success_rate=0.9, file_types=[".go"]),
        "top": _pattern(frequency=5, success_rate=0.9, file_types=[".py"]),
        "mid": _pattern(frequency=2, success_rate=0.9, file_types=[".py"]),
    }

    py_results = asyncio.run(learner._find_relevant_patterns_async("a.py", "backend"))
    unknown_results = asyncio.run(learner._find_relevant_patterns_async("a.go", "unknown"))

    assert py_results == []

    learner._fix_patterns["go"] = _pattern(frequency=4, success_rate=0.9, file_types=[".py"])
    unknown_results = asyncio.run(learner._find_relevant_patterns_async("a.go", "unknown"))

    assert [p.frequency for p in unknown_results] == [5, 4, 3, 2]


def test_common_errors_sorted_and_limited(learner):
    learner._fix_patterns = {
        f"p{i}": _pattern(frequency=i, file_types=[".py"]) for i in range(12)
    }

    common = learner.get_common_errors(".py")

    assert len(common) == 10
    assert common[0]["frequency"] == 11


def test_fix_description_branches(learner):
    assert "依赖" in learner._extract_fix_description("", "", "依赖缺失")
    assert "依赖" in learner._extract_fix_description("", "", "dependency missing")
    assert "类型" in learner._extract_fix_description("", "", "类型错误")
    assert "类型" in learner._extract_fix_description("", "", "type mismatch")


def test_compute_error_embeddings_skips_failures(monkeypatch):
    class _Stub:
        async def __call__(self, text):
            if text.endswith("bad"):
                raise RuntimeError("no vector")
            return [1.0]

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", _Stub())
    learner = FeedbackLearner.__new__(FeedbackLearner)

    result = asyncio.run(learner.compute_error_embeddings(["good", "bad"]))

    assert result == {"good": [1.0]}


def test_load_patterns_handles_corrupt_file(tmp_path):
    (tmp_path / "fix_patterns.json").write_text("{not json", encoding="utf-8")

    learner = FeedbackLearner(learning_dir=tmp_path)

    assert learner._fix_patterns == {}


def test_load_patterns_restores_vectors(tmp_path):
    data = {
        "syntax:boom": {
            "error_type": "syntax",
            "error_message": "boom",
            "error_pattern": "boom",
            "fix_description": "修复",
            "fix_example": "",
            "file_types": [".py"],
            "error_embedding": [0.5],
        }
    }
    (tmp_path / "fix_patterns.json").write_text(json.dumps(data), encoding="utf-8")

    learner = FeedbackLearner(learning_dir=tmp_path)

    assert learner._error_vectors["syntax:boom"] == [0.5]


def test_save_patterns_failure_is_logged(tmp_path, monkeypatch):
    learner = FeedbackLearner(learning_dir=tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    learner._save_patterns()


def test_fix_description_import_branch(learner):
    assert "导入" in learner._extract_fix_description("", "", "导入失败")


def test_common_errors_skips_unrelated_file_types(learner):
    learner._fix_patterns = {
        "py": _pattern(file_types=[".py"]),
        "go": _pattern(file_types=[".go"]),
    }

    common = learner.get_common_errors(".py")

    assert len(common) == 1
