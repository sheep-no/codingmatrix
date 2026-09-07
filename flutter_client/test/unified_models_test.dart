import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('round-trips unified models with *_json fields', () {
    final session = Session.fromJson({
      'id': 'sess-1',
      'user_id': 9,
      'module': 'agent',
      'title': 'Workbench',
      'status': 'active',
      'created_at': '2026-09-06T00:00:00Z',
    });
    expect(session.toJson()['user_id'], 9);

    final task = Task.fromJson({
      'task_id': 'task-1',
      'session_id': session.id,
      'status': 'running',
      'progress': 30,
      'result_json': {'files': 2},
      'error_json': {'code': 'none'},
    });
    expect(task.toJson()['result_json']['files'], 2);

    final event = TaskEvent.fromJson({
      'task_id': task.taskId,
      'sequence': 3,
      'event_type': 'progress',
      'payload_json': {'stage': 'generating'},
      'schema_version': '1',
    });
    expect(event.toJson()['payload_json']['stage'], 'generating');

    final artifact = Artifact.fromJson({
      'id': 'art-1',
      'user_id': 9,
      'task_id': task.taskId,
      'artifact_type': 'file',
      'storage_uri': 'file://src/main.dart',
      'metadata_json': {'language': 'dart'},
    });
    expect(artifact.toJson()['metadata_json']['language'], 'dart');

    final context = ModelContext.fromJson({
      'schema_version': '1',
      'config_version': '2',
      'roles': {'planner': 'model-a'},
      'current_model': 'model-a',
      'current_agent': 'orchestrator',
      'assignments': {
        'planner': {'model': 'model-a', 'calls': 4, 'success_rate': 100},
      },
      'fallback_history': [
        {'from_model': 'model-b', 'to_model': 'model-a'},
      ],
      'updated_at': '2026-09-06T01:00:00Z',
    });
    expect(context.toJson()['assignments']['planner']['calls'], 4);
    expect(context.fallbackHistory.single['to_model'], 'model-a');
  });
}
