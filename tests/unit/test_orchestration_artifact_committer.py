"""Tests for verified artifact commits and final success consistency."""

from pathlib import Path

import pytest

from app.agent.orchestration import (
    ARTIFACT_COMMIT_FAILED,
    ARTIFACT_CONSISTENCY_FAILED,
    ArtifactCommitter,
    ArtifactCompletionEvent,
    build_file_plan,
    check_artifact_success_gate,
)
from app.agent.shared_context import SharedContext


def make_committer(
    tmp_path: Path,
    *,
    writer=None,
    reader=None,
    max_file_bytes: int = 1024,
) -> tuple[ArtifactCommitter, SharedContext]:
    context = SharedContext("create an app", tmp_path)
    kwargs = {}
    if writer is not None:
        kwargs["writer"] = writer
    if reader is not None:
        kwargs["reader"] = reader
    return (
        ArtifactCommitter(
            tmp_path,
            context,
            task_id="task-1",
            max_file_bytes=max_file_bytes,
            **kwargs,
        ),
        context,
    )


def commit_valid_file(
    committer: ArtifactCommitter,
    context: SharedContext,
    path: str,
    content: str,
) -> ArtifactCompletionEvent:
    result = committer.commit(path, content, model_name="test-model")
    assert result.success is True
    assert result.completion_event is not None
    context.update_file_validation(path, True)
    return result.completion_event


def test_commit_writes_verifies_and_registers_artifact(tmp_path: Path) -> None:
    committer, context = make_committer(tmp_path)

    result = committer.commit("src/main.py", "def main():\n    return 1\n", model_name="model-a")

    assert result.success is True
    assert result.idempotent is False
    assert result.completion_event is not None
    assert result.completion_event.event_type == "file_completed"
    assert (tmp_path / "src/main.py").read_text(encoding="utf-8") == "def main():\n    return 1\n"
    assert context.get_artifact_manifest()["src/main.py"]["content_hash"] == result.content_hash


@pytest.mark.parametrize(
    ("path", "content", "max_file_bytes"),
    [
        ("../main.py", "content", 1024),
        ("main.py", "   \n", 1024),
        ("main.py", "content", 3),
    ],
)
def test_commit_rejects_invalid_path_empty_content_and_oversized_file(
    tmp_path: Path,
    path: str,
    content: str,
    max_file_bytes: int,
) -> None:
    committer, context = make_committer(tmp_path, max_file_bytes=max_file_bytes)

    result = committer.commit(path, content, model_name="model-a")

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_COMMIT_FAILED
    assert context.get_artifact_manifest() == {}


@pytest.mark.parametrize(
    "writer",
    [
        lambda output_dir, path, content: False,
        lambda output_dir, path, content: (_ for _ in ()).throw(OSError("disk full")),
    ],
)
def test_commit_reports_atomic_write_failures(tmp_path: Path, writer) -> None:
    committer, context = make_committer(tmp_path, writer=writer)

    result = committer.commit("main.py", "print('ok')\n", model_name="model-a")

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_COMMIT_FAILED
    assert context.get_artifact_manifest() == {}


def test_commit_reports_disk_read_failure_without_registering(tmp_path: Path) -> None:
    def fail_read(path: Path) -> bytes:
        raise OSError("read unavailable")

    committer, context = make_committer(tmp_path, reader=fail_read)

    result = committer.commit("main.py", "print('ok')\n", model_name="model-a")

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_COMMIT_FAILED
    assert context.get_artifact_manifest() == {}


def test_commit_detects_hash_mismatch_without_completion_event(tmp_path: Path) -> None:
    committer, context = make_committer(tmp_path, reader=lambda path: b"changed on disk\n")

    result = committer.commit("main.py", "print('ok')\n", model_name="model-a")

    assert result.success is False
    assert result.completion_event is None
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_CONSISTENCY_FAILED
    assert context.get_artifact_manifest() == {}


def test_duplicate_commit_is_idempotent_and_emits_no_second_event(tmp_path: Path) -> None:
    write_count = 0

    def counted_writer(output_dir: Path, path: str, content: str) -> bool:
        nonlocal write_count
        write_count += 1
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

    committer, context = make_committer(tmp_path, writer=counted_writer)

    first = committer.commit("main.py", "print('ok')\n", model_name="model-a")
    duplicate = committer.commit("./main.py", "print('ok')\n", model_name="model-a")

    assert first.success is True
    assert first.completion_event is not None
    assert duplicate.success is True
    assert duplicate.idempotent is True
    assert duplicate.completion_event is None
    assert write_count == 1
    assert tuple(context.get_artifact_manifest()) == ("main.py",)


def test_success_gate_accepts_matching_valid_artifacts_and_hidden_metadata(tmp_path: Path) -> None:
    plan = build_file_plan(
        [{"path": "model.py"}, {"path": "service.py", "dependencies": ["model.py"]}],
        requested_paths=["model.py", "service.py"],
    )
    committer, context = make_committer(tmp_path)
    events = [
        commit_valid_file(committer, context, "model.py", "class Model:\n    pass\n"),
        commit_valid_file(committer, context, "service.py", "def load():\n    return Model\n"),
    ]
    (tmp_path / ".orchestration").mkdir()
    (tmp_path / ".orchestration/checkpoint.json").write_text("{}", encoding="utf-8")

    result = check_artifact_success_gate(plan, context.get_artifact_manifest(), events, tmp_path)

    assert result.success is True
    assert result.planned_paths == result.manifest_paths == result.completed_paths == result.disk_paths


@pytest.mark.parametrize("difference", ["missing_event", "extra_manifest", "extra_disk"])
def test_success_gate_rejects_file_set_differences(tmp_path: Path, difference: str) -> None:
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    committer, context = make_committer(tmp_path)
    event = commit_valid_file(committer, context, "main.py", "print('ok')\n")
    manifest = context.get_artifact_manifest()
    events = [event]
    if difference == "missing_event":
        events = []
    elif difference == "extra_manifest":
        manifest["extra.py"] = dict(manifest["main.py"], path="extra.py")
    else:
        (tmp_path / "extra.py").write_text("extra\n", encoding="utf-8")

    result = check_artifact_success_gate(plan, manifest, events, tmp_path)

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_CONSISTENCY_FAILED


def test_success_gate_rejects_disk_hash_drift(tmp_path: Path) -> None:
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    committer, context = make_committer(tmp_path)
    event = commit_valid_file(committer, context, "main.py", "print('ok')\n")
    (tmp_path / "main.py").write_text("print('changed')\n", encoding="utf-8")

    result = check_artifact_success_gate(
        plan,
        context.get_artifact_manifest(),
        [event],
        tmp_path,
    )

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_CONSISTENCY_FAILED
    assert result.diagnostic.path == "main.py"


def test_success_gate_rejects_disk_read_failure(tmp_path: Path, monkeypatch) -> None:
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    committer, context = make_committer(tmp_path)
    event = commit_valid_file(committer, context, "main.py", "print('ok')\n")
    original_read_bytes = Path.read_bytes

    def fail_artifact_read(path: Path) -> bytes:
        if path == tmp_path / "main.py":
            raise OSError("read unavailable")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_artifact_read)

    result = check_artifact_success_gate(
        plan,
        context.get_artifact_manifest(),
        [event],
        tmp_path,
    )

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_CONSISTENCY_FAILED
    assert result.diagnostic.path == "main.py"


def test_success_gate_rejects_artifact_before_validation_terminal(tmp_path: Path) -> None:
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    committer, context = make_committer(tmp_path)
    committed = committer.commit("main.py", "print('ok')\n", model_name="model-a")
    assert committed.completion_event is not None

    result = check_artifact_success_gate(
        plan,
        context.get_artifact_manifest(),
        [committed.completion_event],
        tmp_path,
    )

    assert result.success is False
    assert result.diagnostic is not None
    assert result.diagnostic.code == ARTIFACT_CONSISTENCY_FAILED
    assert "validation" in result.diagnostic.message
