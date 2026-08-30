from app.services.artifact_service import create_artifact
from app.services.session_state_service import append_message, create_session
from app.services.task_checkpoint_service import save_checkpoint
from app.services.task_event_service import append_task_event, replay_task_events
from app.services.task_state_service import create_task, transition_task


def test_unified_service_contracts_expose_domain_operations():
    assert callable(create_session)
    assert callable(append_message)
    assert callable(create_task)
    assert callable(transition_task)
    assert callable(append_task_event)
    assert callable(replay_task_events)
    assert callable(save_checkpoint)
    assert callable(create_artifact)
