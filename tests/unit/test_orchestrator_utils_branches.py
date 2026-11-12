"""UtilsMixin 全分支回归：反模式、缓存、校验、档案、记忆与快照。"""

import asyncio
import json
import subprocess as sp
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agent.orchestrator_utils as ou
from app.agent.api_contract_checker import ConsistencyIssue
from app.agent.complexity import ComplexityAnalysis, ProjectComplexity
from app.agent.orchestrator_utils import UtilsMixin
from app.agent.project_profiler import (
    ArchitectureInfo,
    ProjectProfile,
    RiskAreas,
    TestPatterns,
)


class _Host(UtilsMixin):
    def __init__(self, **kwargs):
        self.warnings = []
        self.errors = []
        self.generated_files = []
        self.output_dir = kwargs.pop("output_dir", Path("/tmp"))
        self.feedback_learner = kwargs.pop("feedback_learner", None)
        self.reviewer = kwargs.pop("reviewer", None)
        self.spec_cache = kwargs.pop("spec_cache", None)
        self.complexity = kwargs.pop("complexity", None)
        self.error_recovery = kwargs.pop("error_recovery", None)
        self.model_assignment = kwargs.pop("model_assignment", None)
        self.approval_callback = kwargs.pop("approval_callback", None)
        self.api_contract_checker = kwargs.pop("api_contract_checker", None)
        self.memory_enabled = kwargs.pop("memory_enabled", False)
        self.conversation_memory = kwargs.pop("conversation_memory", None)
        self.knowledge_memory = kwargs.pop("knowledge_memory", None)
        self.backend_engineer = kwargs.pop("backend_engineer", None)
        self.architect = kwargs.pop("architect", None)
        self.snapshot_mgr = kwargs.pop("snapshot_mgr", None)
        self.session_id = kwargs.pop("session_id", "s")
        self.model_name = kwargs.pop("model_name", "")
        self.progress = []
        for key, value in kwargs.items():
            setattr(self, key, value)

    def _is_frontend_file(self, file_path):
        return file_path.endswith((".js", ".ts", ".vue", ".tsx", ".jsx"))

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))


class _Pattern:
    def __init__(self, error_pattern, error_type="x", failure_reason="why"):
        self.error_pattern = error_pattern
        self.error_type = error_type
        self.failure_reason = failure_reason


class _Learner:
    def __init__(self, patterns=()):
        self.patterns = list(patterns)

    def get_anti_patterns(self):
        return self.patterns


def test_anti_pattern_disabled_without_learner():
    assert _Host()._is_anti_pattern("anything") is False


def test_anti_pattern_matches_and_skips_invalid_regex():
    host = _Host(feedback_learner=_Learner([_Pattern("("), _Pattern("danger")]))
    assert host._is_anti_pattern("this is DANGER") is True


def test_anti_pattern_no_match():
    host = _Host(feedback_learner=_Learner([_Pattern("danger")]))
    assert host._is_anti_pattern("safe") is False


@pytest.mark.asyncio
async def test_cache_review_gate_blocks_anti_pattern():
    host = _Host(feedback_learner=_Learner([_Pattern("bad")]), reviewer=None)
    cached = SimpleNamespace(requirement="bad", architecture={})
    assert await host._cache_review_gate(cached) is False


@pytest.mark.asyncio
async def test_select_dynamic_model(monkeypatch):
    import app.agent.dynamic_model_router as dmr

    class _Router:
        async def get_best_model(self, models, task):
            return f"{task}:{models[0]}"

    async def _get_router():
        return _Router()

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    assert await _Host()._select_dynamic_model(["m"], "code") == "code:m"


@pytest.mark.parametrize(
    "path,warn",
    [
        ("", None),
        ("a b.py", "非法路径"),
        ("a/../b.py", "非法路径"),
        ("a/b/c/d/e/f/g.py", "过深路径"),
        ("file.exe", "不支持的文件类型"),
    ],
)
def test_validate_file_plan_rejections(path, warn):
    host = _Host()
    with pytest.raises(ValueError):
        host._validate_file_plan([{"path": path}])
    if warn:
        assert any(warn in w for w in host.warnings)


def test_validate_file_plan_duplicates_and_dedup():
    host = _Host()
    plan = [{"path": "main.py"}, {"path": "main.py"}, {"path": "MANIFEST.in"}]
    valid = host._validate_file_plan(plan)
    assert [f["path"] for f in valid] == ["main.py", "MANIFEST.in"]
    assert any("重复路径" in w for w in host.warnings)


def test_validate_file_plan_allows_no_extension():
    host = _Host()
    valid = host._validate_file_plan([{"path": "Makefile"}])
    assert valid[0]["path"] == "Makefile"


@pytest.mark.asyncio
async def test_profile_project_success_and_failure(tmp_path, monkeypatch):
    captured = {}

    class _Profiler:
        def __init__(self, root, language=None):
            captured["root"] = root
            captured["language"] = language

        def profile(self):
            return ProjectProfile(
                architecture=ArchitectureInfo(pattern="layered", language="go"),
                risk_areas=RiskAreas(high_dependency=["a"]),
                test_patterns=TestPatterns(framework="go test"),
            )

    monkeypatch.setattr(ou, "ProjectProfiler", _Profiler)
    host = _Host(output_dir=tmp_path)
    profile = await host._profile_project("go")
    assert profile.architecture.pattern == "layered"
    assert captured["language"] == "go"

    monkeypatch.setattr(ou, "detect_project_language", lambda root: "rust")
    await host._profile_project()
    assert captured["language"] == "rust"


@pytest.mark.asyncio
async def test_profile_project_swallows_errors(tmp_path, monkeypatch):
    class _Broken:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("no")

    monkeypatch.setattr(ou, "ProjectProfiler", _Broken)
    assert await _Host(output_dir=tmp_path)._profile_project() is None


def test_compute_layers_groups_and_sorts():
    host = _Host()
    plan = [
        {"path": "c", "priority": 2},
        {"path": "a", "priority": 1},
        {"path": "b", "priority": 2},
        {"path": "d"},
    ]
    assert host._compute_layers(plan) == [["a"], ["c", "b"], ["d"]]


@pytest.mark.asyncio
async def test_cache_specs_skips_without_cache():
    await _Host()._cache_specs("r", {}, [])


@pytest.mark.asyncio
async def test_cache_specs_with_complexity_and_vector():
    calls = []

    class _Cache:
        def save(self, **kwargs):
            calls.append(kwargs)

    complexity = ComplexityAnalysis(
        level=ProjectComplexity.MEDIUM,
        estimated_files=7,
        has_frontend=True,
        has_backend=False,
        has_database=True,
    )
    host = _Host(spec_cache=_Cache(), complexity=complexity)
    await host._cache_specs(
        "req",
        {"tech_stack": ["FastAPI"]},
        [{"path": "a.py"}],
        requirement_vector=[0.1],
    )
    call = calls[0]
    assert call["specs"]["complexity"]["level"] == "medium"
    assert call["complexity"]["estimated_files"] == 7
    assert call["tech_stack"] == ["FastAPI"]
    assert call["requirement_vector"] == [0.1]


@pytest.mark.asyncio
async def test_cache_specs_without_complexity():
    calls = []

    class _Cache:
        def save(self, **kwargs):
            calls.append(kwargs)

    await _Host(spec_cache=_Cache())._cache_specs("req", {}, [])
    assert calls[0]["specs"] == {}
    assert calls[0]["complexity"] == {}


@pytest.mark.asyncio
async def test_record_learning_data_skips_without_learner():
    await _Host()._record_learning_data("r", {}, [])


@pytest.mark.asyncio
async def test_wait_for_approval_paths():
    async def _approve(key):
        return True

    host = _Host(approval_callback=_approve)
    assert await host._wait_for_approval("k") is True
    assert await _Host()._wait_for_approval("k") is True

    async def _slow(key):
        await asyncio.sleep(1)
        return True

    host = _Host(approval_callback=_slow)
    assert await host._wait_for_approval("k", timeout=0.01) is False
    assert any("审批超时" in w for w in host.warnings)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/app.vue", True),
        ("src/app.ts", True),
        ("app/api/routes.py", True),
        ("app/main.py", False),
        ("README.md", False),
    ],
)
def test_should_check_api_consistency(path, expected):
    assert _Host()._should_check_api_consistency(path) is expected


class _Checker:
    def __init__(self, issues, fail_frontend_read=False):
        self.issues = issues
        self.fail_frontend_read = fail_frontend_read
        self.calls = []

    def check_single_file_consistency(self, **kwargs):
        self.calls.append(kwargs)
        return self.issues


@pytest.mark.asyncio
async def test_check_and_report_api_issues_skips_without_checker():
    await _Host()._check_and_report_api_issues("a.py", "")


@pytest.mark.asyncio
async def test_check_and_report_api_issues_frontend(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "routes.py").write_text("x")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "junk.py").write_text("junk")
    checker = _Checker(
        [
            ConsistencyIssue(severity="error", issue_type="t", message="e", suggestion="s"),
            ConsistencyIssue(severity="warning", issue_type="t", message="w"),
        ]
    )
    host = _Host(output_dir=tmp_path, api_contract_checker=checker)
    await host._check_and_report_api_issues("web/app.vue", "code")
    assert set(checker.calls[0]["counterpart_files"]) == {"api/routes.py"}
    assert checker.calls[0]["is_frontend"] is True
    assert host.errors == ["API 不一致: e"]
    assert host.warnings == ["API 警告: w"]
    assert len(host.progress) == 2


@pytest.mark.asyncio
async def test_check_and_report_api_issues_backend(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "app.vue").write_text("x")
    (tmp_path / "web" / "main.js").write_text("y")
    checker = _Checker([])
    host = _Host(output_dir=tmp_path, api_contract_checker=checker)
    await host._check_and_report_api_issues("api/routes.py", "code")
    assert set(checker.calls[0]["counterpart_files"]) == {"web/app.vue", "web/main.js"}
    assert checker.calls[0]["is_frontend"] is False


@pytest.mark.asyncio
async def test_check_and_report_swallows_unreadable_files(tmp_path, monkeypatch):
    (tmp_path / "api").mkdir()
    broken = tmp_path / "api" / "routes.py"
    broken.write_text("x")
    checker = _Checker([])
    host = _Host(output_dir=tmp_path, api_contract_checker=checker)

    original_read_text = Path.read_text
    calls = {"count": 0}

    def _flaky(self, *args, **kwargs):
        if self.name == "routes.py":
            calls["count"] += 1
            raise OSError("denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _flaky)
    await host._check_and_report_api_issues("web/app.vue", "code")
    assert checker.calls[0]["counterpart_files"] == {}
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_save_to_memory_disabled():
    await _Host(memory_enabled=False)._save_to_memory("r", {})


@pytest.mark.asyncio
async def test_save_to_memory_records_entries():
    entries = []

    class _Memory:
        def add(self, entry):
            entries.append(entry)

    host = _Host(
        memory_enabled=True,
        conversation_memory=_Memory(),
        knowledge_memory=_Memory(),
    )
    await host._save_to_memory("req", {"tech_stack": ["a", "b", "c", "d", "e", "f"]})
    assert len(entries) == 6
    assert entries[0].type == "project_generation"
    assert entries[1].metadata["category"] == "tech_stack"


@pytest.mark.asyncio
async def test_save_to_memory_swallows_errors():
    class _Broken:
        def add(self, entry):
            raise RuntimeError("nope")

    host = _Host(
        memory_enabled=True,
        conversation_memory=_Broken(),
        knowledge_memory=_Broken(),
    )
    await host._save_to_memory("req", {})


@pytest.mark.asyncio
async def test_call_llm_for_patch_uses_backend_engineer():
    class _Engineer:
        async def call_llm(self, prompt, system_prompt):
            return f"{prompt}|{system_prompt}"

    host = _Host(backend_engineer=_Engineer())
    assert await host._call_llm_for_patch("p", "s") == "p|s"


@pytest.mark.asyncio
async def test_call_llm_for_patch_falls_back_to_architect():
    class _Architect:
        async def call_llm(self, prompt, system_prompt):
            return "arch"

    host = _Host(architect=_Architect())
    assert await host._call_llm_for_patch("p", "s") == "arch"


@pytest.mark.asyncio
async def test_call_llm_for_patch_without_engineer_raises():
    with pytest.raises(RuntimeError) as exc:
        await _Host()._call_llm_for_patch("p", "s")
    assert "no engineer" in str(exc.value)


@pytest.mark.asyncio
async def test_call_llm_for_patch_wraps_unexpected_error():
    class _Engineer:
        async def call_llm(self, prompt, system_prompt):
            raise ValueError("bad")

    with pytest.raises(RuntimeError) as exc:
        await _Host(backend_engineer=_Engineer())._call_llm_for_patch("p", "s")
    assert "LLM patch call failed: bad" in str(exc.value)


@pytest.mark.parametrize(
    "level,expected_level,tokens",
    [
        ("simple", "low", 5000),
        ("small", "medium", 15000),
        ("medium", "medium", 45000),
        ("large", "high", 100000),
        ("enterprise", "high", 250000),
        ("unknown", "medium", 45000),
    ],
)
def test_estimate_generation_cost_levels(level, expected_level, tokens):
    complexity = ComplexityAnalysis(
        level=ProjectComplexity(level),
        estimated_files=1,
        has_frontend=False,
        has_backend=False,
        has_database=False,
    ) if level != "unknown" else None
    payload = _Host(complexity=complexity)._estimate_generation_cost({}, [{"path": "a"}])
    assert payload["cost_level"] == expected_level
    assert payload["estimated_tokens"] == tokens
    assert payload["estimated_files"] == 1


class _Snapshot:
    def __init__(self, result="snap"):
        self.result = result
        self.calls = []

    async def save_snapshot(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.result is None:
            return None
        return SimpleNamespace(tag=self.result)


@pytest.mark.asyncio
async def test_git_snapshot_uses_snapshot_manager(monkeypatch):
    snapshot = _Snapshot()
    host = _Host(snapshot_mgr=snapshot, model_name="m")
    called = []
    monkeypatch.setattr(host, "_git_save_snapshot_sync", lambda msg: called.append(msg))
    await host._git_save_snapshot("desc")
    assert snapshot.calls[0][1]["model_used"] == "m"
    assert called == []


@pytest.mark.asyncio
async def test_git_snapshot_falls_back_when_manager_returns_none(monkeypatch):
    snapshot = _Snapshot(result=None)
    host = _Host(snapshot_mgr=snapshot)
    called = []
    monkeypatch.setattr(host, "_git_save_snapshot_sync", lambda msg: called.append(msg))
    await host._git_save_snapshot("desc")
    assert called == ["desc"]


def _git(host, message="msg"):
    host._git_save_snapshot_sync(message)


def test_git_sync_handles_init_failures(tmp_path, monkeypatch):
    host = _Host(output_dir=tmp_path)

    def _timeout(*args, **kwargs):
        raise sp.TimeoutExpired(cmd="git init", timeout=10)

    monkeypatch.setattr(ou.sp, "run", _timeout)
    _git(host)
    assert not (tmp_path / ".git").exists()


def test_git_sync_handles_init_called_process_error(tmp_path, monkeypatch):
    host = _Host(output_dir=tmp_path)

    def _fail(*args, **kwargs):
        raise sp.CalledProcessError(returncode=1, cmd="git init", stderr=b"boom")

    monkeypatch.setattr(ou.sp, "run", _fail)
    _git(host)


def test_git_sync_creates_gitignore_when_missing(tmp_path, monkeypatch):
    host = _Host(output_dir=tmp_path)
    recorded = []

    class _Done:
        returncode = 0
        stderr = b""

    def _run(cmd, **kwargs):
        recorded.append(cmd)
        if cmd[0] == "git" and cmd[1] == "init":
            (tmp_path / ".git").mkdir()
        return _Done()

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host, "commit")
    assert (tmp_path / ".gitignore").exists()
    assert any(cmd[:2] == ["git", "add"] for cmd in recorded)


def test_git_sync_skips_gitignore_when_present(tmp_path, monkeypatch):
    host = _Host(output_dir=tmp_path)
    (tmp_path / ".gitignore").write_text("keep")

    class _Done:
        returncode = 0
        stderr = b""

    def _run(cmd, **kwargs):
        if cmd[0] == "git" and cmd[1] == "init":
            (tmp_path / ".git").mkdir()
        return _Done()

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host)
    assert (tmp_path / ".gitignore").read_text() == "keep"


def test_git_sync_commit_nothing_to_commit(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    class _Result:
        returncode = 1
        stderr = b"nothing to commit"

    def _run(cmd, **kwargs):
        return _Result()

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host)


def test_git_sync_commit_failure_logs_warning(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    class _Result:
        returncode = 1
        stderr = b"fatal error"

    monkeypatch.setattr(ou.sp, "run", _run_result(_Result()))
    _git(host)


def test_git_sync_commit_failure_without_stderr(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    class _Result:
        returncode = 1
        stderr = None

    monkeypatch.setattr(ou.sp, "run", _run_result(_Result()))
    _git(host)


def test_git_sync_timeout_on_commit(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    def _run(cmd, **kwargs):
        if cmd[1] == "add":
            raise sp.TimeoutExpired(cmd="git add", timeout=30)
        return object()

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host)


def test_git_sync_called_process_error_on_add(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    def _run(cmd, **kwargs):
        raise sp.CalledProcessError(returncode=1, cmd=cmd, stderr=b"fatal")

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host)


def test_git_sync_called_process_error_nothing_to_commit(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    def _run(cmd, **kwargs):
        raise sp.CalledProcessError(
            returncode=1, cmd=cmd, stderr=b"nothing to commit"
        )

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host)


def test_git_sync_called_process_error_without_stderr(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    host = _Host(output_dir=tmp_path)

    def _run(cmd, **kwargs):
        raise sp.CalledProcessError(returncode=1, cmd=cmd, stderr=None)

    monkeypatch.setattr(ou.sp, "run", _run)
    _git(host)


def _run_result(result):
    def _run(cmd, **kwargs):
        return result

    return _run


@pytest.mark.asyncio
async def test_check_backend_swallows_unreadable_frontend(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    broken = tmp_path / "web" / "app.vue"
    broken.write_text("x")
    checker = _Checker([])
    host = _Host(output_dir=tmp_path, api_contract_checker=checker)

    original_read_text = Path.read_text

    def _flaky(self, *args, **kwargs):
        if self.name == "app.vue":
            raise OSError("denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _flaky)
    await host._check_and_report_api_issues("api/routes.py", "code")
    assert checker.calls[0]["counterpart_files"] == {}


@pytest.mark.asyncio
async def test_git_snapshot_without_snapshot_attribute(monkeypatch):
    class _NoSnapshotHost(UtilsMixin):
        def __init__(self):
            self.output_dir = Path("/tmp")
            self.called = []

        def _git_save_snapshot_sync(self, message):
            self.called.append(message)

    host = _NoSnapshotHost()
    await host._git_save_snapshot("desc")
    assert host.called == ["desc"]


class _RecordingLearner:
    def __init__(self):
        self.calls = []
        self.embedding_calls = []

    async def compute_error_embeddings(self, errors):
        self.embedding_calls.append(errors)
        return {"e": [1.0]}

    def record_fix(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_record_learning_data_without_error_recovery():
    learner = _RecordingLearner()
    host = _Host(feedback_learner=learner, error_recovery=None)
    await host._record_learning_data("r", {}, [])
    assert learner.calls == []
    assert learner.embedding_calls == []


@pytest.mark.asyncio
async def test_record_learning_data_with_empty_history():
    learner = _RecordingLearner()
    host = _Host(
        feedback_learner=learner,
        error_recovery=SimpleNamespace(fix_history=[]),
    )
    await host._record_learning_data("r", {}, [])
    assert learner.calls == []
    assert learner.embedding_calls == []


@pytest.mark.asyncio
async def test_record_learning_data_uses_model_assignment_and_embeddings():
    learner = _RecordingLearner()
    fix = SimpleNamespace(
        error_message="e",
        file_path="app/main.py",
        original_content=None,
        fixed_content=None,
        fix_applied=True,
    )
    host = _Host(
        feedback_learner=learner,
        error_recovery=SimpleNamespace(fix_history=[fix]),
        model_assignment=SimpleNamespace(backend_model="qwen"),
    )
    await host._record_learning_data("r", {}, [])
    call = learner.calls[0]
    assert call["model_name"] == "qwen"
    assert call["error_embeddings"] == {"e": [1.0]}
