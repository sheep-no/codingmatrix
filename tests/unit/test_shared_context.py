from pathlib import Path

from app.agent.shared_context import SharedContext


def test_file_artifact_manifest_contains_metadata_without_content(tmp_path: Path):
    context = SharedContext("create a task API", tmp_path)
    context.dependencies["services/task.py"] = ["models/task.py"]
    context.save_file_content(
        "models/task.py",
        "class Task:\n    pass\n",
        "test-model",
    )
    context.update_file_validation("models/task.py", True)
    context.save_file_content(
        "services/task.py",
        "from models.task import Task\n\nclass TaskService:\n    pass\n",
        "test-model",
    )
    context.update_file_validation("services/task.py", True)

    manifest = context.get_artifact_manifest()

    assert manifest["models/task.py"]["content_hash"]
    assert manifest["services/task.py"]["imports"] == ["models.task"]
    assert manifest["services/task.py"]["exports"] == ["TaskService"]
    assert "content" not in manifest["services/task.py"]
    assert context.is_file_ready("services/task.py") is True


def test_invalid_upstream_blocks_downstream_readiness(tmp_path: Path):
    context = SharedContext("create a task API", tmp_path)
    context.dependencies["services/task.py"] = ["models/task.py"]
    context.save_file_content("models/task.py", "class Task: pass\n", "test-model")
    context.update_file_validation("models/task.py", False, ["syntax error"])
    context.save_file_content("services/task.py", "class TaskService: pass\n", "test-model")
    context.update_file_validation("services/task.py", True)

    assert context.is_file_ready("services/task.py") is False


def test_new_file_content_invalidates_previous_validation(tmp_path: Path):
    context = SharedContext("create a task API", tmp_path)
    context.save_file_content("models/task.py", "class Task: pass\n", "qwen3.5-4b")
    context.update_file_validation("models/task.py", True)
    assert context.is_file_ready("models/task.py") is True

    context.save_file_content("models/task.py", "class Task:\n    pass\n", "qwen2.5-7b")

    artifact = context.files["models/task.py"]
    assert artifact.validation_passed is False
    assert artifact.validation_content_hash == ""
    assert context.is_file_ready("models/task.py") is False


def test_validation_evidence_is_bound_to_current_content_hash(tmp_path: Path):
    context = SharedContext("create a task API", tmp_path)
    context.save_file_content("models/task.py", "class Task: pass\n", "qwen3.5-4b")

    context.update_file_validation("models/task.py", True)

    artifact = context.files["models/task.py"]
    assert artifact.validation_content_hash == artifact.content_hash
    assert context.is_file_ready("models/task.py") is True


def test_advance_revision_invalidates_all_validation_evidence(tmp_path: Path):
    context = SharedContext("create a task API", tmp_path)
    context.save_file_content("models/task.py", "class Task: pass\n", "test-model")
    context.update_file_validation("models/task.py", True)
    assert context.is_file_ready("models/task.py") is True

    assert context.advance_revision() == 1

    artifact = context.files["models/task.py"]
    assert artifact.validation_passed is False
    assert artifact.validation_revision == -1
    assert context.is_file_ready("models/task.py") is False


def test_validation_records_current_revision(tmp_path: Path):
    context = SharedContext("create a task API", tmp_path)
    context.save_file_content("models/task.py", "class Task: pass\n", "test-model")
    context.advance_revision()
    context.update_file_validation("models/task.py", True)

    artifact = context.files["models/task.py"]
    assert artifact.validation_revision == context.revision == 1
    assert context.is_file_ready("models/task.py") is True
