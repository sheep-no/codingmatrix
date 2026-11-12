"""Branch coverage for app/api/v1/ai_agent/helpers.py."""

import asyncio
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1.ai_agent import helpers


def _session(session_id="s1", **overrides):
    values = dict(
        session_id=session_id,
        user_id="1",
        requirement="req",
        output_dir=None,
        status="running",
        files_generated=0,
        files_total=0,
        error_message=None,
        created_at=datetime.now(timezone.utc),
        last_activity_at=None,
        completed_at=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _scalar_result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


def _all_result(values):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: values))


class _DB:
    def __init__(self, *results, execute_error=None):
        self._results = list(results)
        self._execute_error = execute_error
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, *_a, **_k):
        if self._execute_error is not None:
            raise self._execute_error
        return self._results.pop(0) if self._results else _scalar_result(None)


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def test_normalize_project_path_rejects_empty():
    with pytest.raises(HTTPException) as error:
        helpers._normalize_project_path("   ")
    assert error.value.status_code == 400


def test_normalize_project_path_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    absolute = tmp_path / "abs"
    assert helpers._normalize_project_path(str(absolute)) == absolute.resolve()
    assert helpers._normalize_project_path("./projects/1/demo") == (tmp_path / "1/demo").resolve()
    assert helpers._normalize_project_path("projects/1/demo") == (tmp_path / "1/demo").resolve()
    assert helpers._normalize_project_path("1/demo") == (tmp_path / "1/demo").resolve()


def test_validate_target_rejects_outside_and_other_user(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path / "base"))
    with pytest.raises(HTTPException) as error:
        helpers._validate_project_target("../escape", "1")
    assert error.value.status_code == 403

    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as error:
        helpers._validate_project_target("1/demo", "2")
    assert error.value.status_code == 403


def test_validate_target_accepts_supported_layouts(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    assert helpers._validate_project_target("1/demo", "1") == tmp_path / "1/demo"
    assert (
        helpers._validate_project_target("user_uploads/1/demo", "1")
        == tmp_path / "user_uploads/1/demo"
    )
    assert (
        helpers._validate_project_target("20240101_abc_1", "1")
        == tmp_path / "20240101_abc_1"
    )
    # Anonymous callers skip ownership checks.
    assert helpers._validate_project_target("other/x", "anonymous") == tmp_path / "other/x"


def test_validate_project_path_missing_and_file(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as error:
        helpers._validate_project_path("1/missing", "1")
    assert error.value.status_code == 404

    (tmp_path / "1").mkdir()
    (tmp_path / "1/file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(HTTPException) as error:
        helpers._validate_project_path("1/file.txt", "1")
    assert error.value.status_code == 400


def test_resolve_output_dir_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    assert helpers.resolve_output_dir("./projects/legacy/x") == (
        Path("./projects/legacy/x").resolve()
    )
    assert helpers.resolve_output_dir("1/demo") == (tmp_path / "1/demo").resolve()


# ---------------------------------------------------------------------------
# Imported project materialization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", None),
        (None, None),
        ("  ", None),
        ("C:", None),
        ("a/./b.py", "a/b.py"),
        ("../secret.py", None),
        ("a/__MACOSX/b.py", None),
        ("a/.DS_Store", None),
        ("/abs/path.py", "abs/path.py"),
        ("a\\b.py", "a/b.py"),
    ],
)
def test_sanitize_imported_relpath(raw, expected):
    assert helpers._sanitize_imported_relpath(raw) == expected


def test_materialize_imported_project_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="无效的用户身份"):
        helpers.materialize_imported_project("anonymous", [{"path": "a.py", "content": "x"}])
    with pytest.raises(ValueError, match="没有可导入的文件"):
        helpers.materialize_imported_project("1", [])

    monkeypatch.setattr(helpers, "MAX_IMPORT_FILES", 1)
    with pytest.raises(ValueError, match="超过上限"):
        helpers.materialize_imported_project(
            "1", [{"path": "a.py", "content": ""}, {"path": "b.py", "content": ""}]
        )


def test_materialize_imported_project_content_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(helpers, "MAX_TEXT_FILE_SIZE", 4)
    with pytest.raises(ValueError, match="文件过大"):
        helpers.materialize_imported_project(
            "1", [{"path": "a.py", "content": "12345"}]
        )

    monkeypatch.setattr(helpers, "MAX_TEXT_FILE_SIZE", 100)
    monkeypatch.setattr(helpers, "MAX_IMPORT_TOTAL_BYTES", 3)
    with pytest.raises(ValueError, match="大小上限"):
        helpers.materialize_imported_project(
            "1", [{"path": "a.py", "content": "ab"}, {"path": "b.py", "content": "cd"}]
        )


def test_materialize_imported_project_skips_invalid_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="没有可写入的有效文件"):
        helpers.materialize_imported_project(
            "1",
            [
                None,
                {"path": "../escape.py", "content": "x"},
                {"path": "b.py", "content": 123},
            ],
        )


def test_materialize_imported_project_normalizes_name_and_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    first = helpers.materialize_imported_project(
        "1", [{"path": "a.py", "content": "x"}], project_name="My Project.zip"
    )
    assert first["project_path"] == "1/My_Project"
    assert (tmp_path / "1/My_Project/a.py").is_file()

    second = helpers.materialize_imported_project(
        "1", [{"path": "a.py", "content": "y"}], project_name="My Project"
    )
    assert second["project_path"].startswith("1/My_Project_")

    unnamed = helpers.materialize_imported_project(
        "1", [{"path": "a.py", "content": "z"}]
    )
    assert unnamed["project_path"].startswith("1/imported_")


def test_cleanup_session_files_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    existing = tmp_path / "1/demo"
    existing.mkdir(parents=True)
    assert helpers.cleanup_session_files("1/demo") is True
    assert not existing.exists()
    assert helpers.cleanup_session_files("1/absent") is True

    def _boom(_path):
        raise RuntimeError("rmtree failed")

    monkeypatch.setattr(helpers.shutil, "rmtree", _boom)
    again = tmp_path / "1/again"
    again.mkdir(parents=True)
    assert helpers.cleanup_session_files("1/again") is False


# ---------------------------------------------------------------------------
# File collection / zip / config
# ---------------------------------------------------------------------------


def test_collect_files_sync_swallows_scan_errors(tmp_path, monkeypatch):
    def _boom(self, pattern):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(Path, "rglob", _boom)
    assert helpers._collect_files_sync(tmp_path) == []


def test_collect_files_sync_skips_unreadable_file(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")

    real_open = open

    def _fake_open(path, *a, **k):
        if str(path).endswith("a.py"):
            raise PermissionError("denied")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", _fake_open)
    assert helpers._collect_files_sync(tmp_path) == []


@pytest.mark.asyncio
async def test_collect_files_yields_entries(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    entries = [entry async for entry in helpers._collect_files(tmp_path)]
    assert entries[0]["name"] == "a.py"


def test_build_agent_config_sets_venv(monkeypatch):
    from app.schema.codeRequest import ALLOWED_MODELS_LIST

    req = SimpleNamespace(
        model=ALLOWED_MODELS_LIST[0], max_thinking_tokens=1, max_output_tokens=2,
        temperature=0.2,
        enable_validation=True, enable_venv_validation=True,
    )
    config = helpers._build_agent_config(req, stream=True)
    assert config.stream is True
    assert config.shared_base_venv == "/opt/base_venv"

    req.enable_venv_validation = False
    assert helpers._build_agent_config(req).shared_base_venv is None


class _FakePath:
    content = "{}"

    def __init__(self, *_parts):
        pass

    def __truediv__(self, _other):
        return self

    @property
    def parent(self):
        return self

    def exists(self):
        return True

    def read_text(self, encoding=None):
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


def test_load_dependency_graph_cache_hit(monkeypatch):
    monkeypatch.setattr(helpers, "_dependency_graph_cache", {"cached": True})
    assert helpers.load_dependency_graph() == {"cached": True}


def test_load_dependency_graph_loads_and_handles_errors(monkeypatch):
    monkeypatch.setattr(helpers, "_dependency_graph_cache", None)
    _FakePath.content = '{"file_count": 2, "edge_count": 1}'
    monkeypatch.setattr(helpers, "Path", _FakePath)
    assert helpers.load_dependency_graph() == {"file_count": 2, "edge_count": 1}

    monkeypatch.setattr(helpers, "_dependency_graph_cache", None)
    _FakePath.content = RuntimeError("bad json")
    assert helpers.load_dependency_graph() is None

    class _Missing(_FakePath):
        def exists(self):
            return False

    monkeypatch.setattr(helpers, "_dependency_graph_cache", None)
    monkeypatch.setattr(helpers, "Path", _Missing)
    assert helpers.load_dependency_graph() is None


def test_load_guard_contracts_cache_and_failure(monkeypatch):
    monkeypatch.setattr(helpers, "_guard_contracts_cache", {"cached": True})
    assert helpers.load_guard_contracts() == {"cached": True}

    monkeypatch.setattr(helpers, "_guard_contracts_cache", None)
    contracts = SimpleNamespace(rules=[1, 2], to_dict=lambda: {"rules": [1, 2]})
    monkeypatch.setattr(helpers, "get_guard_contracts", lambda: contracts)
    assert helpers.load_guard_contracts() == {"rules": [1, 2]}

    monkeypatch.setattr(helpers, "_guard_contracts_cache", None)

    def _boom():
        raise RuntimeError("contracts down")

    monkeypatch.setattr(helpers, "get_guard_contracts", _boom)
    assert helpers.load_guard_contracts() is None


def test_get_agent_knowledge_base(monkeypatch):
    monkeypatch.setattr(helpers, "load_dependency_graph", lambda: {"g": 1})
    monkeypatch.setattr(helpers, "load_guard_contracts", lambda: {"c": 1})
    monkeypatch.setattr(
        helpers, "get_skills_manager",
        lambda: SimpleNamespace(get_all_skills_context=lambda: ["s"]),
    )
    assert helpers.get_agent_knowledge_base() == {
        "dependency_graph": {"g": 1},
        "guard_contracts": {"c": 1},
        "cognitive_skills": ["s"],
    }


@pytest.mark.asyncio
async def test_safe_update_progress_retries_then_succeeds(monkeypatch):
    attempts = []

    async def _update(**kwargs):
        attempts.append(kwargs)
        if len(attempts) < 3:
            raise RuntimeError("not yet")

    async def _sleep(_delay):
        return None

    monkeypatch.setattr(helpers.asyncio, "sleep", _sleep)
    assert await helpers._safe_update_progress(_update, progress=1) is True
    assert len(attempts) == 3

    async def _always_fail(**_kwargs):
        raise RuntimeError("nope")

    assert await helpers._safe_update_progress(_always_fail) is False


def test_create_zip_archive_safe_failure(tmp_path, monkeypatch):
    def _boom(*_a, **_k):
        raise OSError("zip failed")

    monkeypatch.setattr(helpers.zipfile, "ZipFile", _boom)
    assert helpers._create_zip_archive_safe(tmp_path, tmp_path / "x.zip") is False


def test_create_zip_archive_safe_skips_hidden(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("x", encoding="utf-8")
    (source / ".hidden").write_text("x", encoding="utf-8")
    zip_path = tmp_path / "out.zip"
    assert helpers._create_zip_archive_safe(source, zip_path) is True
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == ["a.py"]


def test_cleanup_temp_dir_variants(tmp_path, monkeypatch):
    helpers._cleanup_temp_dir(str(tmp_path / "absent"), "p")
    helpers._cleanup_temp_dir(str(tmp_path), "p")
    assert tmp_path.exists() is False or not tmp_path.exists()


def test_cleanup_temp_dir_swallows_errors(monkeypatch):
    monkeypatch.setattr(helpers.os.path, "exists", lambda path: True)

    def _boom(*_a, **_k):
        raise OSError("cannot remove")

    monkeypatch.setattr(helpers.shutil, "rmtree", _boom)
    helpers._cleanup_temp_dir("/tmp/whatever", "p")


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_singleton_getters_create_once(monkeypatch):
    import app.agent.feedback_learner as feedback_module
    import app.agent.session_manager as session_module
    import app.agent.spec_cache as spec_module

    sentinel = SimpleNamespace()
    created = []

    def _factory(**kwargs):
        created.append(kwargs)
        return sentinel

    monkeypatch.setattr(helpers, "_session_manager", None)
    monkeypatch.setattr(helpers, "_spec_cache", None)
    monkeypatch.setattr(helpers, "_feedback_learner", None)
    monkeypatch.setattr(session_module, "SessionManager", _factory)
    monkeypatch.setattr(spec_module, "SpecCache", lambda: sentinel)
    monkeypatch.setattr(feedback_module, "FeedbackLearner", lambda: sentinel)

    assert await helpers.get_session_manager() is sentinel
    assert await helpers.get_session_manager() is sentinel
    assert await helpers.get_spec_cache() is sentinel
    assert await helpers.get_spec_cache() is sentinel
    assert await helpers.get_feedback_learner() is sentinel
    assert await helpers.get_feedback_learner() is sentinel
    assert len(created) == 1


# ---------------------------------------------------------------------------
# Session cleanup / lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_old_session_keeps_under_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_PROJECT_SESSIONS_PER_USER", 5, raising=False)
    db = _DB(_all_result([_session("a")]))
    await helpers._cleanup_old_session("1", db)
    assert db.commit.await_count == 0


@pytest.mark.asyncio
async def test_cleanup_old_session_deletes_history_and_files(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_PROJECT_SESSIONS_PER_USER", 1, raising=False)
    old = _session("old", status="completed", output_dir=str(tmp_path / "old"))
    keep = _session("keep", status="completed")
    db = _DB(_all_result([keep, old]))
    sm = SimpleNamespace(_session_file=lambda sid: tmp_path / f"{sid}.json")
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    deleted = []
    monkeypatch.setattr(
        helpers, "_delete_session_files",
        lambda session_file, output_dir: deleted.append(session_file.name),
    )
    await helpers._cleanup_old_session("1", db)
    assert deleted == ["old.json"]
    assert old.status == "cancelled"
    assert db.commit.await_count == 1


def test_delete_session_files_tolerates_os_errors(tmp_path, monkeypatch):
    session_file = tmp_path / "s.json"
    session_file.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def _boom(*_a, **_k):
        raise OSError("denied")

    monkeypatch.setattr(Path, "unlink", _boom)
    monkeypatch.setattr(helpers.shutil, "rmtree", _boom)
    helpers._delete_session_files(session_file, str(output_dir))


@pytest.mark.asyncio
async def test_detect_zombie_timeout_and_exception(monkeypatch):
    stale = _session(
        "stale",
        status="running",
        output_dir="1/stale",
        last_activity_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    sm = SimpleNamespace(_get_state=AsyncMock(return_value=object()))
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(helpers, "cleanup_session_files", lambda path: True)
    db = _DB(_all_result([stale]))
    assert await helpers._detect_and_clean_zombie_sessions(db, "1") == 1
    assert stale.status == "failed"

    db = _DB(execute_error=RuntimeError("db down"))
    assert await helpers._detect_and_clean_zombie_sessions(db, "1") == 0


@pytest.mark.asyncio
async def test_detect_zombie_naive_timestamp_still_checked(monkeypatch):
    naive_old = _session(
        "naive",
        status="running",
        last_activity_at=datetime.now() - timedelta(days=30),
    )
    sm = SimpleNamespace(_get_state=AsyncMock(return_value=object()))
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(helpers, "cleanup_session_files", lambda path: True)
    db = _DB(_all_result([naive_old]))
    assert await helpers._detect_and_clean_zombie_sessions(db, "1") == 1


@pytest.mark.asyncio
async def test_create_project_session_success_and_conflict():
    db = _DB()
    session = await helpers._create_project_session(db, 1, "s", "req", "1/s")
    assert session.status == "running"
    db.add.assert_called_once()

    db = _DB()
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    with pytest.raises(HTTPException) as error:
        await helpers._create_project_session(db, 1, "s", "req", "1/s")
    assert error.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_session_activity_paths(monkeypatch):
    session = _session("s")
    db = _DB(_scalar_result(session))
    await helpers._update_session_activity(db, "s")
    assert session.last_activity_at is not None

    db = _DB(_scalar_result(None))
    await helpers._update_session_activity(db, "missing")
    assert db.commit.await_count == 0

    db = _DB(execute_error=RuntimeError("db down"))
    await helpers._update_session_activity(db, "s")


@pytest.mark.asyncio
async def test_update_project_session_status_paths(monkeypatch):
    await helpers._update_project_session_status(None, "s", "completed")

    db = _DB(_scalar_result(None))
    await helpers._update_project_session_status(db, "missing", "completed")

    cleaned = []
    monkeypatch.setattr(
        helpers, "cleanup_session_files", lambda path: cleaned.append(path) or True
    )
    session = _session("s", output_dir="1/s")
    sm = SimpleNamespace(
        _get_state=AsyncMock(return_value=SimpleNamespace(
            status="running", completed_at=None, updated_at=None,
        )),
        _save_session=AsyncMock(),
    )
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    db = _DB(_scalar_result(session))
    await helpers._update_project_session_status(
        db, "s", "failed", files_generated=1, files_total=2,
        error_message="boom",
    )
    assert cleaned == ["1/s"]
    assert session.status == "failed"
    sm._save_session.assert_awaited_once()

    db = _DB(execute_error=SQLAlchemyError("db down"))
    await helpers._update_project_session_status(db, "s", "completed")


@pytest.mark.asyncio
async def test_update_project_session_status_swallows_memory_sync_error(monkeypatch):
    session = _session("s")
    sm = SimpleNamespace(
        _get_state=AsyncMock(side_effect=RuntimeError("state down")),
        _save_session=AsyncMock(),
    )
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    db = _DB(_scalar_result(session))
    await helpers._update_project_session_status(db, "s", "completed")
    assert session.status == "completed"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def test_verify_admin_token():
    assert helpers.verify_admin_token({"role": "admin"}) == {"role": "admin"}
    with pytest.raises(HTTPException) as error:
        helpers.verify_admin_token({"role": "user"})
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_session_ownership_paths():
    session = _session("s")
    assert await helpers.verify_session_ownership(
        _DB(_scalar_result(session)), "s", "1"
    ) is session

    with pytest.raises(HTTPException) as error:
        await helpers.verify_session_ownership(_DB(_scalar_result(None)), "s", "1")
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        await helpers.verify_session_ownership(
            _DB(execute_error=RuntimeError("db down")), "s", "1"
        )
    assert error.value.status_code == 500


# ---------------------------------------------------------------------------
# Resume intent / session matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_resume_intent_no_keyword():
    result = await helpers.detect_resume_intent("build a calculator")
    assert result["is_resume"] is False


@pytest.mark.asyncio
async def test_detect_resume_intent_parses_llm_json(monkeypatch):
    import app.utils as utils

    monkeypatch.setattr(utils, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content":
            '{"is_resume": true, "has_changes": true, "additional_requirement": "add x"}'}}]
    }))
    result = await helpers.detect_resume_intent("继续生成")
    assert result["is_resume"] is True
    assert result["additional_requirement"] == "add x"


@pytest.mark.asyncio
async def test_detect_resume_intent_falls_back(monkeypatch):
    import app.utils as utils

    monkeypatch.setattr(utils, "call_llm", AsyncMock(side_effect=RuntimeError("down")))
    result = await helpers.detect_resume_intent("继续生成")
    assert result["is_resume"] is True

    monkeypatch.setattr(utils, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "no json here"}}],
    }))
    result = await helpers.detect_resume_intent("resume the project")
    assert result["is_resume"] is True


@pytest.mark.asyncio
async def test_resolve_resume_session_falls_back_to_running(monkeypatch):
    recent = _session("recent")
    monkeypatch.setattr(
        helpers, "get_user_recent_session", AsyncMock(return_value=recent)
    )
    result = await helpers.resolve_resume_session(_DB(_all_result([])), "1", "继续")
    assert result is recent


@pytest.mark.asyncio
async def test_resolve_resume_session_matches_index(monkeypatch):
    import app.utils as utils

    rows = [
        _session("a", status="completed", files_generated=1, files_total=2),
        _session("b", status="failed", files_generated=0, files_total=0),
    ]
    monkeypatch.setattr(utils, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "2"}}],
    }))
    result = await helpers.resolve_resume_session(
        _DB(_all_result(rows)), "1", "fix login"
    )
    assert result.session_id == "b"


@pytest.mark.asyncio
async def test_resolve_resume_session_out_of_range_and_error(monkeypatch):
    import app.utils as utils

    rows = [_session("a", status="completed")]
    monkeypatch.setattr(utils, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "9"}}],
    }))
    result = await helpers.resolve_resume_session(
        _DB(_all_result(rows)), "1", "x"
    )
    assert result.session_id == "a"

    monkeypatch.setattr(utils, "call_llm", AsyncMock(side_effect=RuntimeError("down")))
    result = await helpers.resolve_resume_session(
        _DB(_all_result(rows)), "1", "x"
    )
    assert result.session_id == "a"


@pytest.mark.asyncio
async def test_analyze_files_to_regenerate_paths(monkeypatch):
    import app.utils as utils

    monkeypatch.setattr(utils, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": '["a.py", "unknown.py"]'}}],
    }))
    assert await helpers.analyze_files_to_regenerate(
        "orig", "new", ["a.py"]
    ) == ["a.py"]

    monkeypatch.setattr(utils, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "no list"}}],
    }))
    assert await helpers.analyze_files_to_regenerate("orig", "new", ["a.py"]) == []

    monkeypatch.setattr(utils, "call_llm", AsyncMock(side_effect=RuntimeError("down")))
    assert await helpers.analyze_files_to_regenerate("orig", "new", ["a.py"]) == []


@pytest.mark.asyncio
async def test_get_user_recent_session_paths():
    session = _session("s")
    assert await helpers.get_user_recent_session(
        _DB(_scalar_result(session)), "1"
    ) is session
    assert await helpers.get_user_recent_session(
        _DB(_scalar_result(session)), "1", status_filter="running"
    ) is session

    class _Boom:
        async def execute(self, *_a, **_k):
            raise RuntimeError("db down")

    assert await helpers.get_user_recent_session(_Boom(), "1") is None
