/// Unified Agent workbench models compatible with backend snake_case JSON.
class Agent {
  const Agent({
    required this.id,
    required this.name,
    this.status = 'idle',
    this.currentModel,
  });

  final String id;
  final String name;
  final String status;
  final String? currentModel;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'status': status,
      'current_model': currentModel,
    };
  }

  factory Agent.fromJson(Map<String, dynamic> json) {
    return Agent(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      status: json['status'] as String? ?? 'idle',
      currentModel: json['current_model'] as String?,
    );
  }
}

class Session {
  const Session({
    required this.id,
    required this.userId,
    required this.module,
    this.externalId,
    this.title,
    this.status = 'active',
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final int userId;
  final String module;
  final String? externalId;
  final String? title;
  final String status;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'user_id': userId,
      'module': module,
      'external_id': externalId,
      'title': title,
      'status': status,
      'created_at': createdAt?.toIso8601String(),
      'updated_at': updatedAt?.toIso8601String(),
    };
  }

  factory Session.fromJson(Map<String, dynamic> json) {
    return Session(
      id: json['id'] as String? ?? '',
      userId: (json['user_id'] as num?)?.toInt() ?? 0,
      module: json['module'] as String? ?? 'agent',
      externalId: json['external_id'] as String?,
      title: json['title'] as String?,
      status: json['status'] as String? ?? 'active',
      createdAt: _parseDate(json['created_at']),
      updatedAt: _parseDate(json['updated_at']),
    );
  }
}

class Task {
  const Task({
    required this.taskId,
    this.sessionId,
    this.revision = 0,
    this.taskType = 'code_generate',
    this.status = 'pending',
    this.stage,
    this.progress = 0,
    this.resultJson = const <String, dynamic>{},
    this.errorJson = const <String, dynamic>{},
    this.createdAt,
  });

  final String taskId;
  final String? sessionId;
  final int revision;
  final String taskType;
  final String status;
  final String? stage;
  final int progress;
  final Map<String, dynamic> resultJson;
  final Map<String, dynamic> errorJson;
  final DateTime? createdAt;

  Map<String, dynamic> toJson() {
    return {
      'task_id': taskId,
      'session_id': sessionId,
      'revision': revision,
      'task_type': taskType,
      'status': status,
      'stage': stage,
      'progress': progress,
      'result_json': resultJson,
      'error_json': errorJson,
      'created_at': createdAt?.toIso8601String(),
    };
  }

  factory Task.fromJson(Map<String, dynamic> json) {
    return Task(
      taskId: json['task_id'] as String? ?? '',
      sessionId: json['session_id'] as String?,
      revision: (json['revision'] as num?)?.toInt() ?? 0,
      taskType: json['task_type'] as String? ?? 'code_generate',
      status: json['status'] as String? ?? 'pending',
      stage: json['stage'] as String?,
      progress: (json['progress'] as num?)?.toInt() ?? 0,
      resultJson: _asStringKeyedMap(json['result_json'] ?? json['result']),
      errorJson: _asStringKeyedMap(json['error_json']),
      createdAt: _parseDate(json['created_at']),
    );
  }

  Task copyWith({
    String? status,
    String? stage,
    int? progress,
    int? revision,
    Map<String, dynamic>? resultJson,
    Map<String, dynamic>? errorJson,
  }) {
    return Task(
      taskId: taskId,
      sessionId: sessionId,
      revision: revision ?? this.revision,
      taskType: taskType,
      status: status ?? this.status,
      stage: stage ?? this.stage,
      progress: progress ?? this.progress,
      resultJson: resultJson ?? this.resultJson,
      errorJson: errorJson ?? this.errorJson,
      createdAt: createdAt,
    );
  }
}

class TaskEvent {
  const TaskEvent({
    required this.taskId,
    required this.sequence,
    required this.eventType,
    this.status,
    this.progress,
    this.payloadJson = const <String, dynamic>{},
    this.schemaVersion = '1',
    this.createdAt,
  });

  final String taskId;
  final int sequence;
  final String eventType;
  final String? status;
  final int? progress;
  final Map<String, dynamic> payloadJson;
  final String schemaVersion;
  final DateTime? createdAt;

  Map<String, dynamic> toJson() {
    return {
      'task_id': taskId,
      'sequence': sequence,
      'event_type': eventType,
      'status': status,
      'progress': progress,
      'payload_json': payloadJson,
      'schema_version': schemaVersion,
      'created_at': createdAt?.toIso8601String(),
    };
  }

  factory TaskEvent.fromJson(Map<String, dynamic> json) {
    return TaskEvent(
      taskId: json['task_id'] as String? ?? '',
      sequence: (json['sequence'] as num?)?.toInt() ?? 0,
      eventType: json['event_type'] as String? ?? '',
      status: json['status'] as String?,
      progress: (json['progress'] as num?)?.toInt(),
      payloadJson: _asStringKeyedMap(json['payload_json']),
      schemaVersion: json['schema_version']?.toString() ?? '1',
      createdAt: _parseDate(json['created_at']),
    );
  }
}

class Artifact {
  const Artifact({
    required this.id,
    required this.userId,
    required this.artifactType,
    required this.storageUri,
    this.sessionId,
    this.taskId,
    this.version = 1,
    this.contentHash,
    this.metadataJson = const <String, dynamic>{},
    this.createdAt,
  });

  final String id;
  final int userId;
  final String? sessionId;
  final String? taskId;
  final String artifactType;
  final int version;
  final String storageUri;
  final String? contentHash;
  final Map<String, dynamic> metadataJson;
  final DateTime? createdAt;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'user_id': userId,
      'session_id': sessionId,
      'task_id': taskId,
      'artifact_type': artifactType,
      'version': version,
      'storage_uri': storageUri,
      'content_hash': contentHash,
      'metadata_json': metadataJson,
      'created_at': createdAt?.toIso8601String(),
    };
  }

  factory Artifact.fromJson(Map<String, dynamic> json) {
    return Artifact(
      id: json['id'] as String? ?? '',
      userId: (json['user_id'] as num?)?.toInt() ?? 0,
      sessionId: json['session_id'] as String?,
      taskId: json['task_id'] as String?,
      artifactType: json['artifact_type'] as String? ?? '',
      version: (json['version'] as num?)?.toInt() ?? 1,
      storageUri: json['storage_uri'] as String? ?? '',
      contentHash: json['content_hash'] as String?,
      metadataJson: _asStringKeyedMap(json['metadata_json']),
      createdAt: _parseDate(json['created_at']),
    );
  }
}

class RoleAssignment {
  const RoleAssignment({
    required this.model,
    this.calls = 0,
    this.successRate = 100.0,
  });

  final String model;
  final int calls;
  final double successRate;

  Map<String, dynamic> toJson() {
    return {
      'model': model,
      'calls': calls,
      'success_rate': successRate,
    };
  }

  factory RoleAssignment.fromJson(Map<String, dynamic> json) {
    return RoleAssignment(
      model: json['model'] as String? ?? '',
      calls: (json['calls'] as num?)?.toInt() ?? 0,
      successRate: (json['success_rate'] as num?)?.toDouble() ?? 100.0,
    );
  }
}

class ModelContext {
  const ModelContext({
    this.schemaVersion = '1',
    this.configVersion = '',
    this.roles = const <String, String>{},
    this.currentModel,
    this.currentAgent,
    this.assignments = const <String, RoleAssignment>{},
    this.fallbackHistory = const <Map<String, dynamic>>[],
    this.updatedAt,
  });

  final String schemaVersion;
  final String configVersion;
  final Map<String, String> roles;
  final String? currentModel;
  final String? currentAgent;
  final Map<String, RoleAssignment> assignments;
  final List<Map<String, dynamic>> fallbackHistory;
  final DateTime? updatedAt;

  Map<String, dynamic> toJson() {
    return {
      'schema_version': schemaVersion,
      'config_version': configVersion,
      'roles': roles,
      'current_model': currentModel,
      'current_agent': currentAgent,
      'assignments': assignments.map((key, value) => MapEntry(key, value.toJson())),
      'fallback_history': fallbackHistory,
      'updated_at': updatedAt?.toIso8601String(),
    };
  }

  factory ModelContext.fromJson(Map<String, dynamic> json) {
    final rawAssignments = json['assignments'];
    final assignments = <String, RoleAssignment>{};
    if (rawAssignments is Map) {
      rawAssignments.forEach((key, value) {
        if (value is Map<String, dynamic>) {
          assignments[key.toString()] = RoleAssignment.fromJson(value);
        } else if (value is Map) {
          assignments[key.toString()] = RoleAssignment.fromJson(
            Map<String, dynamic>.from(value),
          );
        }
      });
    }

    final rawRoles = json['roles'];
    final roles = <String, String>{};
    if (rawRoles is Map) {
      rawRoles.forEach((key, value) {
        roles[key.toString()] = value?.toString() ?? '';
      });
    }

    final rawHistory = json['fallback_history'];
    final history = <Map<String, dynamic>>[];
    if (rawHistory is List) {
      for (final item in rawHistory) {
        if (item is Map<String, dynamic>) {
          history.add(item);
        } else if (item is Map) {
          history.add(Map<String, dynamic>.from(item));
        } else if (item is String) {
          history.add({'to_model': item});
        }
      }
    }

    return ModelContext(
      schemaVersion: json['schema_version']?.toString() ?? '1',
      configVersion: json['config_version']?.toString() ?? '',
      roles: roles,
      currentModel: json['current_model'] as String?,
      currentAgent: json['current_agent'] as String?,
      assignments: assignments,
      fallbackHistory: history,
      updatedAt: _parseDate(json['updated_at']),
    );
  }
}

DateTime? _parseDate(Object? value) {
  if (value is String && value.isNotEmpty) {
    return DateTime.tryParse(value);
  }
  return null;
}

Map<String, dynamic> _asStringKeyedMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  return <String, dynamic>{};
}
