"""CheckpointStore 缺失文件分支补测。"""

from app.agent.state.checkpoint import CheckpointStore
from app.agent.state.models import State


def test_load_returns_none_when_checkpoint_absent(tmp_path):
    store = CheckpointStore(tmp_path)
    assert store.load("missing") is None


def test_save_and_load_roundtrip(tmp_path):
    store = CheckpointStore(tmp_path)
    state = State(session_id="s1", task_id="t1", revision=3)

    path = store.save(state)

    assert path.exists()
    assert store.load("t1") == state
