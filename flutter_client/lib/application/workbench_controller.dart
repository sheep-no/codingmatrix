import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_controller.dart';
import '../infrastructure/agent/agent_stream_client.dart';
import '../domain/models/unified_models.dart';
import '../infrastructure/sse/sse_parser.dart';
import '../domain/models/provider_key.dart';
import '../domain/models/agent_decision.dart';
import '../infrastructure/agent/agent_project_client.dart';

class WorkbenchState {
  const WorkbenchState({
    this.agent,
    this.session,
    this.task,
    this.modelContext,
    this.events = const <SseEvent>[],
    this.artifacts = const <Artifact>[],
    this.decisions = const [],
    this.decisionBusy = false,
    this.actionError,
  });

  final Agent? agent;
  final Session? session;
  final Task? task;
  final ModelContext? modelContext;
  final List<SseEvent> events;
  final List<Artifact> artifacts;
  final List<AgentDecision> decisions;
  final bool decisionBusy;
  final String? actionError;
  bool get active => const {
    'running',
    'awaitingDecision',
    'stopping',
    'disconnected',
  }.contains(task?.status);
  String? get projectPath => task?.resultJson['project_path'] as String?;

  WorkbenchState copyWith({
    Agent? agent,
    Session? session,
    Task? task,
    ModelContext? modelContext,
    List<SseEvent>? events,
    List<Artifact>? artifacts,
    List<AgentDecision>? decisions,
    bool? decisionBusy,
    String? actionError,
    bool clearActionError = false,
  }) {
    return WorkbenchState(
      agent: agent ?? this.agent,
      session: session ?? this.session,
      task: task ?? this.task,
      modelContext: modelContext ?? this.modelContext,
      events: events ?? this.events,
      artifacts: artifacts ?? this.artifacts,
      decisions: decisions ?? this.decisions,
      decisionBusy: decisionBusy ?? this.decisionBusy,
      actionError: clearActionError ? null : actionError ?? this.actionError,
    );
  }
}

class WorkbenchController extends StateNotifier<WorkbenchState> {
  WorkbenchController({
    SseParser? parser,
    AgentStreamClient? streamClient,
    AgentProjectClient? projectClient,
  }) : _parser = parser ?? SseParser(),
       _streamClient = streamClient,
       _projectClient = projectClient,
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
  final AgentProjectClient? _projectClient;
  int _generation = 0;
  int _decisionVersion = 0;
  StreamSubscription<String>? _streamSubscription;
  String? _activeAccessTokenRef;

  List<SseEvent> ingestSseChunk(String chunk) {
    if (!mounted) return [];
    final parsed = _parser.push(chunk);
    if (parsed.isEmpty) {
      return parsed;
    }

    var task = state.task;
    var decisions = state.decisions;
    final artifacts = List<Artifact>.from(state.artifacts);
    for (final event in parsed) {
      if (const {'success', 'failed', 'cancelled'}.contains(task?.status)) {
        continue;
      }
      if (event.type == 'critical_decisions') {
        final questions = event.data?['decisions'];
        if (questions is List) {
          decisions = questions
              .map(
                (value) => AgentDecision.fromJson(
                  Map<String, dynamic>.from(value as Map),
                ),
              )
              .toList();
          _decisionVersion++;
        }
      } else if (const {'done', 'error', 'cancelled'}.contains(event.type) ||
          (event.type == 'progress' &&
              event.data?['stage'] != 'awaiting_user_decision')) {
        decisions = [];
      }
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
      decisions: decisions,
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
    ProviderKeySummary? providerKey,
    String? resumeSessionId,
  }) async {
    final client = _streamClient;
    if (client == null) {
      throw StateError('Agent stream client is not configured');
    }
    final generation = _generation + 1;
    await disconnect();
    if (!mounted || generation != _generation) return;
    resetStream();
    final taskId = 'local-${DateTime.now().millisecondsSinceEpoch}';
    final sessionId =
        resumeSessionId ?? 'desktop-${DateTime.now().millisecondsSinceEpoch}';
    _activeAccessTokenRef = accessTokenRef;
    state = state.copyWith(
      task: Task(
        taskId: taskId,
        sessionId: sessionId,
        status: 'running',
        stage: 'connecting',
      ),
    );
    _streamSubscription = client
        .generate(
          accessTokenRef: accessTokenRef,
          requirement: requirement,
          projectName: projectName,
          sessionId: sessionId,
          isResume: resumeSessionId != null,
          apiKeyToken: providerKey?.isUsable == true
              ? providerKey!.token
              : null,
          providerId: providerKey?.isUsable == true
              ? providerKey!.provider
              : null,
        )
        .listen(
          (chunk) {
            if (mounted && generation == _generation) ingestSseChunk(chunk);
          },
          onError: (Object error) {
            if (!mounted || generation != _generation || !state.active) return;
            state = state.copyWith(
              task: state.task?.copyWith(
                status: 'disconnected',
                errorJson: const <String, dynamic>{'error': '连接中断，服务端任务状态待确认'},
              ),
            );
          },
          onDone: () {
            if (mounted &&
                generation == _generation &&
                state.active &&
                state.task?.status != 'stopping') {
              state = state.copyWith(
                task: state.task?.copyWith(
                  status: 'disconnected',
                  errorJson: const <String, dynamic>{
                    'error': '事件流已断开，请从会话历史刷新状态后手动重连',
                  },
                ),
              );
            }
          },
        );
  }

  Future<void> stopGeneration({bool markCancelled = true}) async {
    if (!state.active || state.task?.status == 'stopping') return;
    final activeTask = state.task;
    final accessTokenRef = _activeAccessTokenRef;
    final sessionId = activeTask?.sessionId;
    final generation = ++_generation;
    state = state.copyWith(
      task: activeTask?.copyWith(status: 'stopping'),
      clearActionError: true,
    );
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    try {
      if (activeTask != null &&
          accessTokenRef != null &&
          sessionId != null &&
          _streamClient != null) {
        await _streamClient.stop(
          accessTokenRef: accessTokenRef,
          sessionId: sessionId,
        );
      }
      if (mounted && generation == _generation && markCancelled) {
        state = state.copyWith(
          task: state.task?.copyWith(status: 'cancelled'),
          decisions: [],
          artifacts: [],
        );
      }
    } catch (_) {
      if (mounted && generation == _generation) {
        state = state.copyWith(
          task: state.task?.copyWith(status: 'disconnected'),
          actionError: '停止结果未确认，请重试或检查服务端任务',
        );
      }
    }
  }

  Future<void> submitDecisions(Map<String, String> choices) async {
    final sessionId = state.task?.sessionId;
    if (sessionId == null ||
        _projectClient == null ||
        state.decisionBusy ||
        state.decisions.isEmpty) {
      return;
    }
    if (state.decisions.any(
      (question) => !question.options.any(
        (option) => option['label'] == choices[question.id],
      ),
    )) {
      state = state.copyWith(actionError: '请为每个决策选择有效选项');
      return;
    }
    final generation = _generation;
    final version = _decisionVersion;
    state = state.copyWith(decisionBusy: true, clearActionError: true);
    try {
      await _projectClient.decide(sessionId, choices);
      if (mounted &&
          generation == _generation &&
          version == _decisionVersion &&
          state.decisions.isNotEmpty) {
        state = state.copyWith(
          decisions: [],
          task: state.task?.copyWith(status: 'running'),
        );
      }
    } catch (_) {
      if (mounted && generation == _generation) {
        state = state.copyWith(actionError: '决策未被确认，等待可能已超时；请查看任务进度');
      }
    } finally {
      if (mounted && generation == _generation) {
        state = state.copyWith(decisionBusy: false);
      }
    }
  }

  Future<void> disconnect() async {
    _generation++;
    final subscription = _streamSubscription;
    _streamSubscription = null;
    _activeAccessTokenRef = null;
    await subscription?.cancel();
  }

  void resetStream() {
    _parser.reset();
    _decisionVersion++;
    state = WorkbenchState(
      agent: state.agent,
      modelContext: state.modelContext,
    );
  }

  @override
  void dispose() {
    _generation++;
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
      case 'critical_decisions':
        return task.copyWith(
          status: 'awaitingDecision',
          sessionId: event.data?['session_id'] as String? ?? task.sessionId,
        );
      case 'progress':
        return task.copyWith(
          sessionId: event.data?['session_id'] as String? ?? task.sessionId,
          status: event.data?['stage'] == 'awaiting_user_decision'
              ? 'awaitingDecision'
              : 'running',
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
      ref.watch(
        authControllerProvider.select((auth) => auth.session?.accessTokenRef),
      );
      return WorkbenchController(
        projectClient: AgentProjectClient(
          ref.watch(authenticatedClientProvider),
        ),
        streamClient: AgentStreamClient(
          baseUrl: ref.watch(cloudAuthClientProvider).baseUrl,
          httpClient: ref.watch(authenticatedClientProvider),
          credentialStore: ref.watch(credentialStoreProvider),
        ),
      );
    });
