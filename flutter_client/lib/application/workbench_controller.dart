import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_controller.dart';
import '../infrastructure/agent/agent_stream_client.dart';
import '../domain/models/unified_models.dart';
import '../infrastructure/sse/sse_parser.dart';

class WorkbenchState {
  const WorkbenchState({
    this.agent,
    this.session,
    this.task,
    this.modelContext,
    this.events = const <SseEvent>[],
    this.artifacts = const <Artifact>[],
  });

  final Agent? agent;
  final Session? session;
  final Task? task;
  final ModelContext? modelContext;
  final List<SseEvent> events;
  final List<Artifact> artifacts;

  WorkbenchState copyWith({
    Agent? agent,
    Session? session,
    Task? task,
    ModelContext? modelContext,
    List<SseEvent>? events,
    List<Artifact>? artifacts,
  }) {
    return WorkbenchState(
      agent: agent ?? this.agent,
      session: session ?? this.session,
      task: task ?? this.task,
      modelContext: modelContext ?? this.modelContext,
      events: events ?? this.events,
      artifacts: artifacts ?? this.artifacts,
    );
  }
}

class WorkbenchController extends StateNotifier<WorkbenchState> {
  WorkbenchController({SseParser? parser, AgentStreamClient? streamClient})
    : _parser = parser ?? SseParser(),
      _streamClient = streamClient,
      super(
        WorkbenchState(
          agent: const Agent(
            id: 'desktop-agent',
            name: 'CodingMatrix Agent',
            status: 'idle',
          ),
        ),
      );

  final SseParser _parser;
  final AgentStreamClient? _streamClient;
  StreamSubscription<String>? _streamSubscription;

  List<SseEvent> ingestSseChunk(String chunk) {
    final parsed = _parser.push(chunk);
    if (parsed.isEmpty) {
      return parsed;
    }

    var task = state.task;
    final artifacts = List<Artifact>.from(state.artifacts);
    for (final event in parsed) {
      task = _applyEvent(task, event);
      final artifactPayload = event.data?['artifact'];
      if (artifactPayload is Map<String, dynamic>) {
        artifacts.add(Artifact.fromJson(artifactPayload));
      } else if (artifactPayload is Map) {
        artifacts.add(
          Artifact.fromJson(Map<String, dynamic>.from(artifactPayload)),
        );
      }
    }

    state = state.copyWith(
      events: [...state.events, ...parsed],
      task: task,
      artifacts: artifacts,
    );
    return parsed;
  }

  void bindSession(Session session) {
    state = state.copyWith(session: session);
  }

  void bindTask(Task task) {
    state = state.copyWith(task: task);
  }

  void bindModelContext(ModelContext context) {
    state = state.copyWith(
      modelContext: context,
      agent:
          (state.agent ??
                  const Agent(id: 'desktop-agent', name: 'CodingMatrix Agent'))
              .copyWithStatus(currentModel: context.currentModel),
    );
  }

  Future<void> startGeneration({
    required String accessTokenRef,
    required String requirement,
    String? projectName,
  }) async {
    final client = _streamClient;
    if (client == null) {
      throw StateError('Agent stream client is not configured');
    }
    await stopGeneration(markCancelled: false);
    resetStream();
    final taskId = 'local-${DateTime.now().millisecondsSinceEpoch}';
    state = state.copyWith(
      task: Task(taskId: taskId, status: 'running', stage: 'connecting'),
    );
    _streamSubscription = client
        .generate(
          accessTokenRef: accessTokenRef,
          requirement: requirement,
          projectName: projectName,
        )
        .listen(
          ingestSseChunk,
          onError: (Object error) {
            state = state.copyWith(
              task: state.task?.copyWith(
                status: 'failed',
                errorJson: <String, dynamic>{'error': error.toString()},
              ),
            );
          },
          onDone: () {
            if (state.task?.status == 'running') {
              state = state.copyWith(
                task: state.task?.copyWith(
                  status: 'failed',
                  errorJson: const <String, dynamic>{'error': 'Agent 事件流提前结束'},
                ),
              );
            }
          },
        );
  }

  Future<void> stopGeneration({bool markCancelled = true}) async {
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    if (markCancelled && state.task?.status == 'running') {
      state = state.copyWith(task: state.task?.copyWith(status: 'cancelled'));
    }
  }

  void resetStream() {
    _parser.reset();
    state = state.copyWith(events: const <SseEvent>[]);
  }

  @override
  void dispose() {
    final subscription = _streamSubscription;
    _streamSubscription = null;
    if (subscription != null) {
      unawaited(subscription.cancel());
    }
    super.dispose();
  }

  Task? _applyEvent(Task? task, SseEvent event) {
    if (task == null) {
      return task;
    }
    switch (event.type) {
      case 'progress':
        return task.copyWith(
          status: 'running',
          progress: (event.data?['progress'] as num?)?.toInt() ?? task.progress,
          stage: event.data?['stage'] as String? ?? task.stage,
        );
      case 'done':
        return task.copyWith(
          status: 'success',
          progress: 100,
          resultJson: event.data ?? task.resultJson,
        );
      case 'error':
        return task.copyWith(
          status: 'failed',
          errorJson: event.data ?? task.errorJson,
        );
      case 'cancelled':
        return task.copyWith(status: 'cancelled');
      default:
        return task;
    }
  }
}

extension on Agent {
  Agent copyWithStatus({String? status, String? currentModel}) {
    return Agent(
      id: id,
      name: name,
      status: status ?? this.status,
      currentModel: currentModel ?? this.currentModel,
    );
  }
}

final workbenchControllerProvider =
    StateNotifierProvider<WorkbenchController, WorkbenchState>((ref) {
      return WorkbenchController(
        streamClient: AgentStreamClient(
          baseUrl: ref.watch(apiBaseUrlProvider),
          httpClient: ref.watch(httpClientProvider),
          credentialStore: ref.watch(credentialStoreProvider),
        ),
      );
    });
