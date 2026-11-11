import {
  LocalValidationResult,
  PendingAction,
  parseLocalValidationResult,
  parsePendingAction,
  ProtocolError,
} from "./protocol.js";
import { AgentHostEnvelope, AgentHostSession, HostHandshake, HostHelloPayload, parseAgentHostEnvelope } from "./agent-host.js";
import { ResultStore } from "./result-store.js";
import { nodeFetch } from "./node-fetch.js";

export interface HttpResponseLike {
  readonly ok: boolean;
  readonly status: number;
  readonly body?: { getReader(): { read(): Promise<{ done: boolean; value?: Uint8Array }> } } | null;
  json(): Promise<unknown>;
  text(): Promise<string>;
}

export type AgentStreamEvent = { type: string; data?: unknown };

export type FetchLike = (
  input: string,
  init?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    signal?: AbortSignal;
  },
) => Promise<HttpResponseLike>;

export interface CloudConnectionOptions {
  baseUrl: string;
  accessToken: string;
  fetchImpl?: FetchLike;
  maxRetries?: number;
  retryDelayMs?: number;
  requestTimeoutMs?: number;
  streamIdleTimeoutMs?: number;
  actionsPath?: string;
  resultsPath?: string;
  handshakePath?: string;
  resultStore?: ResultStore;
}

export class CloudConnectionError extends Error {
  constructor(
    public readonly code:
      | "authentication_failed"
      | "request_failed"
      | "network_unavailable",
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "CloudConnectionError";
  }
}

// A 401 or 410 means the session id/token pair is unusable, so the caller must
// re-handshake instead of polling with dead credentials. Throttle the attempt
// so a backend that keeps rejecting does not spin a re-handshake every second.
export const SESSION_RECOVERY_THROTTLE_MS = 30_000;

export function shouldRecoverSession(
  error: unknown,
  lastRecoveryAt: number,
  now: number = Date.now(),
): boolean {
  return (
    error instanceof CloudConnectionError &&
    (error.status === 401 || error.status === 410) &&
    now - lastRecoveryAt > SESSION_RECOVERY_THROTTLE_MS
  );
}

type QueuedResult = {
  result: LocalValidationResult;
  context?: ResultSubmissionContext;
};

export type ResultSubmissionContext = {
  messageId?: string;
  capability?: string;
  policyVersion?: number;
};

export type QueuedResultResponse = {
  status: "queued";
  event_id: string;
};

// Shapes returned by the user-scoped v1 read APIs the workbench panels use.
// They are normalized so the webview never has to guard against missing fields.
export interface ConversationSummary {
  conversation_id: number;
  title: string;
  prompt: string;
  created_at: string | null;
  message_count: number;
}

export interface ConversationMessage {
  id: number | null;
  conversation_id: number | null;
  prompt: string;
  response: string;
  thinking: string;
  title: string;
  created_at: string | null;
}

export interface AgentModelConfig {
  version: number | null;
  roles: Record<string, unknown>;
  models: unknown[];
  fallback_chain: unknown[];
}

export interface TokenUsage {
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_messages: number;
  today_tokens: number;
  this_month_tokens: number;
  by_model: Record<string, unknown>;
}

export interface SnapshotInfo {
  tag: string;
  commit: string;
  message: string;
  timestamp: string | null;
}

export interface PerformanceSnapshot {
  metrics: Record<string, unknown>;
  thresholds: Record<string, unknown>;
  trends: Record<string, unknown>;
}

export interface LearningErrorPattern {
  error_type: string;
  error_message: string;
  frequency: number;
  success_rate: number;
  fix_description: string;
}

export interface LearningStats {
  learned_patterns: number;
  total_fixes_recorded: number;
  total_sessions: number;
  overall_success_rate: number;
  top_errors: LearningErrorPattern[];
}

export interface CacheStats {
  total_requests: number;
  cache_hits: number;
  cache_misses: number;
  hit_rate: number;
  cached_entries: number;
  cache_size_mb: number;
  vector_index_size: number;
  tech_index_groups: number;
}

export interface CacheClearResult {
  clearedCount: number;
  mode: string;
}

export interface DecisionSubmitResult {
  status: string;
  sessionId: string;
}

const DEFAULT_ACTIONS_PATH = "/api/v1/agent/local-validation/actions";
const DEFAULT_RESULTS_PATH = "/api/v1/agent/local-validation/results";
const DEFAULT_HANDSHAKE_PATH = "/api/v1/agent/host/handshake";
const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;
const DEFAULT_STREAM_IDLE_TIMEOUT_MS = 30_000;
const NETWORK_ERROR_CODES = new Set([
  "ECONNRESET",
  "ECONNREFUSED",
  "ECONNABORTED",
  "ETIMEDOUT",
  "EPIPE",
  "ENOTFOUND",
  "EAI_AGAIN",
  "EHOSTUNREACH",
  "ENETUNREACH",
]);

export class CloudConnection {
  private readonly baseUrl: string;
  private readonly accessToken: string;
  private readonly fetchImpl: FetchLike;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;
  private readonly requestTimeoutMs: number;
  private readonly streamIdleTimeoutMs: number;
  private readonly actionsPath: string;
  private readonly resultsPath: string;
  private readonly handshakePath: string;
  private readonly resultStore?: ResultStore;
  private sessionId?: string;
  private readonly queuedResults: QueuedResult[] = [];

  constructor(options: CloudConnectionOptions) {
    if (!options.baseUrl.trim()) {
      throw new Error("baseUrl is required");
    }
    if (!options.accessToken.trim()) {
      throw new Error("accessToken is required");
    }
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.accessToken = options.accessToken;
    this.fetchImpl = options.fetchImpl ?? nodeFetch;
    this.maxRetries = options.maxRetries ?? 2;
    this.retryDelayMs = options.retryDelayMs ?? 250;
    this.requestTimeoutMs = options.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    this.streamIdleTimeoutMs = options.streamIdleTimeoutMs ?? DEFAULT_STREAM_IDLE_TIMEOUT_MS;
    this.actionsPath = options.actionsPath ?? DEFAULT_ACTIONS_PATH;
    this.resultsPath = options.resultsPath ?? DEFAULT_RESULTS_PATH;
    this.handshakePath = options.handshakePath ?? DEFAULT_HANDSHAKE_PATH;
    this.resultStore = options.resultStore;
  }

  get pendingResultCount(): number {
    return this.queuedResults.length;
  }

  get hostSessionId(): string | undefined {
    return this.sessionId;
  }

  async handshake(hello: HostHelloPayload): Promise<HostHandshake> {
    const response = await this.request(this.handshakePath, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(hello),
    });
    const session = new AgentHostSession();
    const handshake = session.acceptHandshake(await this.readJson(response));
    this.sessionId = handshake.session_id;
    await this.flushPendingResults();
    return handshake;
  }

  async fetchAgentHostActions(): Promise<AgentHostEnvelope[]> {
    if (!this.sessionId) throw new CloudConnectionError("request_failed", "agent host handshake is required");
    const response = await this.request(`/api/v1/agent/host/sessions/${encodeURIComponent(this.sessionId)}/actions`, { method: "GET" });
    const body = await this.readJson(response);
    const actions = this.isRecord(body) && Array.isArray(body.actions) ? body.actions : null;
    if (!actions) throw new ProtocolError("invalid_payload", "agent host actions response must contain an array");
    return actions.map(parseAgentHostEnvelope);
  }

  async submitEvent(event: AgentHostEnvelope): Promise<unknown> {
    if (!this.sessionId) throw new CloudConnectionError("request_failed", "agent host handshake is required");
    if (event.session_id !== this.sessionId) throw new ProtocolError("invalid_payload", "event session does not match handshake");
    const response = await this.request(`/api/v1/agent/host/sessions/${encodeURIComponent(this.sessionId)}/events`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(event),
    });
    return this.readJson(response);
  }

  async controlSession(action: "pause" | "resume" | "cancel"): Promise<{ status: string }> {
    if (!this.sessionId) throw new CloudConnectionError("request_failed", "agent host handshake is required");
    const response = await this.request(`/api/v1/agent/host/sessions/${encodeURIComponent(this.sessionId)}/control`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action }),
    });
    const body = await this.readJson(response);
    if (!this.isRecord(body) || typeof body.status !== "string") {
      throw new ProtocolError("invalid_payload", "session control response must contain a status");
    }
    return { status: body.status };
  }

  async syncSkills(skills: Record<string, unknown>): Promise<unknown> {
    if (!this.sessionId) throw new CloudConnectionError("request_failed", "agent host handshake is required");
    const response = await this.request(`/api/v1/agent/host/sessions/${encodeURIComponent(this.sessionId)}/skills`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ skills }),
    });
    return this.readJson(response);
  }

  async listConversations(options: { limit?: number; offset?: number } = {}): Promise<ConversationSummary[]> {
    const response = await this.request("/api/v1/history", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ limit: options.limit ?? 20, offset: options.offset ?? 0 }),
    });
    const body = await this.readJson(response);
    const items = this.requiredArray(body, "items", "history response must contain an items array");
    return items.flatMap((item) => {
      if (!this.isRecord(item)) return [];
      const conversationId = this.optionalNumber(item.conversation_id);
      if (conversationId === null) return [];
      return [{
        conversation_id: conversationId,
        title: this.optionalString(item.title) ?? "",
        prompt: this.optionalString(item.prompt) ?? "",
        created_at: this.optionalString(item.created_at),
        message_count: this.optionalNumber(item.message_count) ?? 0,
      }];
    });
  }

  async fetchConversationHistory(
    conversationId: number,
    options: { lastHistoryId?: number | null; limit?: number } = {},
  ): Promise<ConversationMessage[]> {
    if (!Number.isInteger(conversationId) || conversationId <= 0) {
      throw new CloudConnectionError("request_failed", "conversation id must be a positive integer");
    }
    const payload: Record<string, unknown> = {
      conversation_id: conversationId,
      limit: options.limit ?? 50,
    };
    if (options.lastHistoryId !== undefined && options.lastHistoryId !== null) {
      payload.last_history_id = options.lastHistoryId;
    }
    const response = await this.request("/api/v1/conversation/history", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await this.readJson(response);
    const items = this.requiredArray(body, "items", "conversation history response must contain an items array");
    return items.flatMap((item) => {
      if (!this.isRecord(item)) return [];
      return [{
        id: this.optionalNumber(item.id),
        conversation_id: this.optionalNumber(item.conversation_id),
        prompt: this.optionalString(item.prompt) ?? "",
        response: this.optionalString(item.response) ?? "",
        thinking: this.optionalString(item.thinking) ?? "",
        title: this.optionalString(item.title) ?? "",
        created_at: this.optionalString(item.created_at),
      }];
    });
  }

  async deleteConversation(conversationId: number): Promise<number> {
    if (!Number.isInteger(conversationId) || conversationId <= 0) {
      throw new CloudConnectionError("request_failed", "conversation id must be a positive integer");
    }
    const response = await this.request(
      `/api/v1/code/history?all=false&conversation_ids=${conversationId}`,
      { method: "DELETE" },
    );
    const body = await this.readJson(response);
    return this.isRecord(body) ? this.optionalNumber(body.count) ?? 0 : 0;
  }

  async fetchAgentModelConfig(): Promise<AgentModelConfig> {
    const response = await this.request("/api/v1/models/agent-config", { method: "GET" });
    const body = await this.readJson(response);
    if (!this.isRecord(body)) {
      throw new ProtocolError("invalid_payload", "agent model config response must be an object");
    }
    return {
      version: this.optionalNumber(body.version),
      roles: this.isRecord(body.roles) ? { ...body.roles } : {},
      models: Array.isArray(body.models) ? [...body.models] : [],
      fallback_chain: Array.isArray(body.fallback_chain) ? [...body.fallback_chain] : [],
    };
  }

  async fetchTokenUsage(): Promise<TokenUsage> {
    const response = await this.request("/api/v1/agent/token-usage", { method: "GET" });
    const body = await this.readJson(response);
    if (!this.isRecord(body)) {
      throw new ProtocolError("invalid_payload", "token usage response must be an object");
    }
    return {
      total_tokens: this.optionalNumber(body.total_tokens) ?? 0,
      prompt_tokens: this.optionalNumber(body.prompt_tokens) ?? 0,
      completion_tokens: this.optionalNumber(body.completion_tokens) ?? 0,
      total_messages: this.optionalNumber(body.total_messages) ?? 0,
      today_tokens: this.optionalNumber(body.today_tokens) ?? 0,
      this_month_tokens: this.optionalNumber(body.this_month_tokens) ?? 0,
      by_model: this.isRecord(body.by_model) ? { ...body.by_model } : {},
    };
  }

  async listSnapshots(sessionId: string): Promise<SnapshotInfo[]> {
    const response = await this.request(`/api/v1/agent/snapshots/${encodeURIComponent(sessionId)}`, { method: "GET" });
    const body = await this.readJson(response);
    const items = this.requiredArray(body, "snapshots", "snapshot response must contain a snapshots array");
    return items.flatMap((item) => {
      if (!this.isRecord(item)) return [];
      const tag = this.optionalString(item.tag);
      if (!tag) return [];
      return [{
        tag,
        commit: this.optionalString(item.commit) ?? "",
        message: this.optionalString(item.message) ?? "",
        timestamp: this.optionalString(item.timestamp),
      }];
    });
  }

  async rollbackToSnapshot(
    sessionId: string,
    targetTag: string,
  ): Promise<{ previousTag: string; currentTag: string; filesRestored: number }> {
    const response = await this.request(
      `/api/v1/agent/rollback/${encodeURIComponent(sessionId)}?target_tag=${encodeURIComponent(targetTag)}`,
      { method: "POST" },
    );
    const body = await this.readJson(response);
    if (!this.isRecord(body)) {
      throw new ProtocolError("invalid_payload", "rollback response must be an object");
    }
    return {
      previousTag: this.optionalString(body.previous_tag) ?? "",
      currentTag: this.optionalString(body.current_tag) ?? "",
      filesRestored: this.optionalNumber(body.files_restored) ?? 0,
    };
  }

  async fetchSnapshotDiff(sessionId: string, fromTag: string, toTag: string): Promise<string> {
    const query = `session_id=${encodeURIComponent(sessionId)}&from_tag=${encodeURIComponent(fromTag)}&to_tag=${encodeURIComponent(toTag)}`;
    const response = await this.request(`/api/v1/agent/snapshot/diff?${query}`, { method: "GET" });
    const body = await this.readJson(response);
    return this.isRecord(body) ? this.optionalString(body.diff) ?? "" : "";
  }

  async fetchPerformance(): Promise<PerformanceSnapshot> {
    const [metricsResponse, trendsResponse] = await Promise.all([
      this.request("/api/v1/agent/performance", { method: "GET" }),
      this.request("/api/v1/agent/performance/trends", { method: "GET" }),
    ]);
    const metricsBody = await this.readJson(metricsResponse);
    const trendsBody = await this.readJson(trendsResponse);
    return {
      metrics: this.isRecord(metricsBody) && this.isRecord(metricsBody.metrics) ? { ...metricsBody.metrics } : {},
      thresholds: this.isRecord(metricsBody) && this.isRecord(metricsBody.thresholds) ? { ...metricsBody.thresholds } : {},
      trends: this.isRecord(trendsBody) && this.isRecord(trendsBody.trends) ? { ...trendsBody.trends } : {},
    };
  }

  async fetchLearningStats(): Promise<LearningStats> {
    const response = await this.request("/api/v1/agent/learning/stats", { method: "GET" });
    const body = await this.readJson(response);
    const patterns = this.requiredArray(body, "top_errors", "learning stats response must contain a top_errors array");
    const stats = this.isRecord(body) ? body : {};
    return {
      learned_patterns: this.optionalNumber(stats.learned_patterns) ?? 0,
      total_fixes_recorded: this.optionalNumber(stats.total_fixes_recorded) ?? 0,
      total_sessions: this.optionalNumber(stats.total_sessions) ?? 0,
      overall_success_rate: this.optionalNumber(stats.overall_success_rate) ?? 0,
      top_errors: patterns.flatMap((item) => {
        if (!this.isRecord(item)) return [];
        return [{
          error_type: this.optionalString(item.error_type) ?? "",
          error_message: this.optionalString(item.error_message) ?? "",
          frequency: this.optionalNumber(item.frequency) ?? 0,
          success_rate: this.optionalNumber(item.success_rate) ?? 0,
          fix_description: this.optionalString(item.fix_description) ?? "",
        }];
      }),
    };
  }

  async fetchConcurrentLimits(): Promise<Record<string, unknown>> {
    const response = await this.request("/api/v1/agent/concurrent-limits/recommended", { method: "GET" });
    const body = await this.readJson(response);
    return this.isRecord(body) && this.isRecord(body.recommendations) ? { ...body.recommendations } : {};
  }

  async fetchCacheStats(): Promise<CacheStats> {
    const response = await this.request("/api/v1/agent/cache/stats", { method: "GET" });
    const body = await this.readJson(response);
    if (!this.isRecord(body)) {
      throw new ProtocolError("invalid_payload", "cache stats response must be an object");
    }
    return {
      total_requests: this.optionalNumber(body.total_requests) ?? 0,
      cache_hits: this.optionalNumber(body.cache_hits) ?? 0,
      cache_misses: this.optionalNumber(body.cache_misses) ?? 0,
      hit_rate: this.optionalNumber(body.hit_rate) ?? 0,
      cached_entries: this.optionalNumber(body.cached_entries) ?? 0,
      cache_size_mb: this.optionalNumber(body.cache_size_mb) ?? 0,
      vector_index_size: this.optionalNumber(body.vector_index_size) ?? 0,
      tech_index_groups: this.optionalNumber(body.tech_index_groups) ?? 0,
    };
  }

  async clearAgentCache(mode: "expired" | "all"): Promise<CacheClearResult> {
    const response = await this.request(`/api/v1/agent/cache/clear?mode=${mode}`, { method: "POST" });
    const body = await this.readJson(response);
    if (!this.isRecord(body)) {
      throw new ProtocolError("invalid_payload", "cache clear response must be an object");
    }
    return {
      clearedCount: this.optionalNumber(body.cleared_count) ?? 0,
      mode: this.optionalString(body.mode) ?? mode,
    };
  }

  async submitDecisions(sessionId: string, decisions: Record<string, string>): Promise<DecisionSubmitResult> {
    const response = await this.request(
      `/api/v1/agent/session/${encodeURIComponent(sessionId)}/decision`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(decisions) },
    );
    const body = await this.readJson(response);
    if (!this.isRecord(body)) {
      throw new ProtocolError("invalid_payload", "decision response must be an object");
    }
    return {
      status: this.optionalString(body.status) ?? "",
      sessionId: this.optionalString(body.session_id) ?? sessionId,
    };
  }

  async streamAgentPrompt(
    request: Record<string, unknown>,
    onEvent: (event: AgentStreamEvent) => void | Promise<void>,
    signal?: AbortSignal,
  ): Promise<void> {
    // The stream gets its own controller so an idle read can tear down the
    // socket, and so the caller's abort still propagates to the fetch.
    const controller = new AbortController();
    const forwardAbort = (): void => controller.abort();
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener("abort", forwardAbort, { once: true });
    }
    try {
      const response = await this.request("/api/v1/agent/orchestrate/stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
        timeoutMs: this.streamIdleTimeoutMs,
      });
      if (!response.body) throw new CloudConnectionError("request_failed", "agent stream response has no body");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const chunk = await this.readStreamChunk(reader, controller);
        buffer += decoder.decode(chunk.value, { stream: !chunk.done });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const data = frame.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
          if (!data) continue;
          await onEvent(this.parseStreamEvent(data));
        }
        if (chunk.done) break;
      }
      const finalData = buffer.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
      if (finalData) await onEvent(this.parseStreamEvent(finalData));
    } finally {
      signal?.removeEventListener("abort", forwardAbort);
    }
  }

  async fetchPendingActions(): Promise<PendingAction[]> {
    const response = await this.request(this.actionsPath, { method: "GET" });
    const body = await this.readJson(response);
    const actions = Array.isArray(body)
      ? body
      : this.isRecord(body) && Array.isArray(body.actions)
        ? body.actions
        : null;
    if (!actions) {
      throw new ProtocolError("invalid_payload", "actions response must contain an array");
    }
    return actions.map(parsePendingAction);
  }

  async submitResult(
    resultInput: unknown,
    context: ResultSubmissionContext = {},
  ): Promise<unknown> {
    const result = parseLocalValidationResult(resultInput);
    try {
      return await this.submitParsedResult(result, context);
    } catch (error) {
      if (this.shouldRetainResult(error)) {
        if (this.resultStore) await this.resultStore.enqueue(result, context);
        else this.queuedResults.push({ result, context });
        return { status: "queued", event_id: result.event_id } satisfies QueuedResultResponse;
      }
      throw error;
    }
  }

  async flushPendingResults(): Promise<number> {
    if (this.resultStore) {
      return this.flushStoredResults();
    }
    let flushed = 0;
    while (this.queuedResults.length > 0) {
      const queued = this.queuedResults[0];
      try {
        await this.submitParsedResult(queued.result, queued.context);
        this.queuedResults.shift();
        flushed += 1;
      } catch (error) {
        if (this.shouldRetainResult(error)) {
          break;
        }
        this.queuedResults.shift();
      }
    }
    return flushed;
  }

  private async flushStoredResults(): Promise<number> {
    let flushed = 0;
    const pending = await this.resultStore!.listPending();
    for (const record of pending) {
      try {
        await this.submitParsedResult(record.result, record.context);
        await this.resultStore!.acknowledge(record.result.event_id);
        flushed += 1;
      } catch (error) {
        if (this.shouldRetainResult(error)) break;
        await this.resultStore!.acknowledge(record.result.event_id);
      }
    }
    return flushed;
  }

  private async submitParsedResult(
    result: LocalValidationResult,
    context: ResultSubmissionContext = {},
  ): Promise<unknown> {
    // The Host event route is the live contract; the legacy results path is
    // only used before a Host session exists (custom deployments, tests). A
    // queued result can carry the session id from before a re-handshake, so
    // the envelope always follows the live session id.
    const hostSessionId = this.sessionId;
    const path = hostSessionId
      ? `/api/v1/agent/host/sessions/${encodeURIComponent(hostSessionId)}/events`
      : this.resultsPath;
    const payload = hostSessionId
      ? {
          message_id: `${context.messageId ?? result.event_id}:result`,
          schema_version: result.schema_version,
          session_id: hostSessionId,
          task_id: result.task_id,
          revision: result.revision,
          kind: "tool_result",
          ...(context.capability === undefined ? {} : { capability: context.capability }),
          ...(context.policyVersion === undefined ? {} : { policy_version: context.policyVersion }),
          payload: result,
        }
      : result;
    const response = await this.request(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    return this.readJson(response);
  }

  async acknowledgeAction(actionId: string): Promise<boolean> {
    if (!this.sessionId) return false;
    const response = await this.request(
      `/api/v1/agent/host/sessions/${encodeURIComponent(this.sessionId)}/actions/ack`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action_id: actionId }),
      },
    );
    const body = await this.readJson(response);
    return this.isRecord(body) && body.acknowledged === true;
  }

  private async request(
    path: string,
    init: {
      method: string;
      headers?: Record<string, string>;
      body?: string;
      signal?: AbortSignal;
      timeoutMs?: number;
    },
  ): Promise<HttpResponseLike> {
    const method = init.method.toUpperCase();
    // Only idempotent reads are safe to replay. A mutating request that times
    // out or returns a transient status may already have taken effect server
    // side, so it is surfaced instead of being sent twice.
    const retryableMethod = method === "GET" || method === "HEAD";
    const timeoutMs = init.timeoutMs ?? this.requestTimeoutMs;
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      try {
        const response = await this.fetchWithTimeout(
          `${this.baseUrl}${path}`,
          {
            method,
            headers: {
              authorization: `Bearer ${this.accessToken}`,
              accept: "application/json",
              ...init.headers,
            },
            ...(init.body === undefined ? {} : { body: init.body }),
            ...(init.signal === undefined ? {} : { signal: init.signal }),
          },
          timeoutMs,
          path,
        );
        if (response.status === 401 || response.status === 403) {
          throw new CloudConnectionError(
            "authentication_failed",
            "cloud authentication failed",
            response.status,
          );
        }
        if (!response.ok) {
          const error = new CloudConnectionError(
            "request_failed",
            await this.describeFailure(response),
            response.status,
          );
          if (
            !retryableMethod ||
            !this.isRetryableStatus(response.status) ||
            attempt === this.maxRetries
          ) {
            throw error;
          }
          lastError = error;
        } else {
          return response;
        }
      } catch (error) {
        if (error instanceof CloudConnectionError && error.code === "authentication_failed") {
          throw error;
        }
        if (!retryableMethod || !this.isNetworkError(error) || attempt === this.maxRetries) {
          if (error instanceof CloudConnectionError) {
            throw error;
          }
          throw new CloudConnectionError(
            "network_unavailable",
            `cloud network request failed for ${this.baseUrl}${path}${error instanceof Error && error.message ? `: ${error.message}` : ""}`,
          );
        }
        lastError = error;
      }
      await this.delay(this.retryDelayMs * 2 ** attempt);
    }
    throw lastError ?? new CloudConnectionError("network_unavailable", "cloud network request failed");
  }

  private async fetchWithTimeout(
    url: string,
    init: Parameters<FetchLike>[1],
    timeoutMs: number,
    path: string,
  ): Promise<HttpResponseLike> {
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      return this.fetchImpl(url, init);
    }
    const controller = new AbortController();
    const forwardAbort = (): void => controller.abort();
    if (init?.signal) {
      if (init.signal.aborted) controller.abort();
      else init.signal.addEventListener("abort", forwardAbort, { once: true });
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(
            new CloudConnectionError(
              "network_unavailable",
              `cloud request timed out after ${timeoutMs}ms for ${path}`,
            ),
          );
        }, timeoutMs);
      });
      return await Promise.race([
        this.fetchImpl(url, { ...init, signal: controller.signal }),
        timeout,
      ]);
    } finally {
      if (timer) clearTimeout(timer);
      init?.signal?.removeEventListener("abort", forwardAbort);
    }
  }

  private async readStreamChunk(
    reader: { read(): Promise<{ done: boolean; value?: Uint8Array }> },
    controller: AbortController,
  ): Promise<{ done: boolean; value?: Uint8Array }> {
    if (!Number.isFinite(this.streamIdleTimeoutMs) || this.streamIdleTimeoutMs <= 0) {
      return reader.read();
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(
            new CloudConnectionError(
              "network_unavailable",
              `agent stream was idle for ${this.streamIdleTimeoutMs}ms`,
            ),
          );
        }, this.streamIdleTimeoutMs);
      });
      return await Promise.race([reader.read(), timeout]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  private async readJson(response: HttpResponseLike): Promise<unknown> {
    try {
      return await this.withReadTimeout(response.json());
    } catch (error) {
      if (error instanceof CloudConnectionError) throw error;
      throw new CloudConnectionError("request_failed", "cloud response is not valid JSON", response.status);
    }
  }

  // Headers can arrive while the body stalls, which would otherwise hang the
  // caller forever just like a missing response.
  private async withReadTimeout<T>(operation: Promise<T>): Promise<T> {
    const timeoutMs = this.requestTimeoutMs;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return operation;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        operation,
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => {
            reject(
              new CloudConnectionError(
                "network_unavailable",
                `cloud response body timed out after ${timeoutMs}ms`,
              ),
            );
          }, timeoutMs);
        }),
      ]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  // Surface the backend's actionable message (for example the disk-space guard)
  // instead of an opaque status code, while tolerating non-JSON error bodies.
  private async describeFailure(response: HttpResponseLike): Promise<string> {
    const fallback = `cloud request failed with status ${response.status}`;
    try {
      const parsed: unknown = JSON.parse(await this.withReadTimeout(response.text()));
      if (this.isRecord(parsed)) {
        const detail = parsed.message ?? parsed.detail;
        if (typeof detail === "string" && detail.trim()) {
          return `${fallback}: ${detail.trim()}`;
        }
      }
    } catch {
      // Non-JSON or unreadable error body; keep the generic message.
    }
    return fallback;
  }

  // Thinking chunks repeat the whole accumulated buffer beside the incremental
  // message; the workbench renders only the message, and the repetition makes
  // the forwarded stream quadratic in the response length.
  private parseStreamEvent(payload: string): AgentStreamEvent {
    try {
      const event = JSON.parse(payload) as AgentStreamEvent & { accumulated?: unknown };
      if (event.type === "thinking") delete event.accumulated;
      return event;
    } catch {
      // One malformed frame must not end the whole stream. Surface it as a
      // diagnostic event so the terminal `done`/`error` frame still arrives.
      return {
        type: "stream_warning",
        data: { message: "无法解析的流式事件已跳过" },
      };
    }
  }

  private isRetryableStatus(status: number): boolean {
    return status === 408 || status === 429 || status >= 500;
  }

  private isNetworkError(error: unknown): boolean {
    if (error instanceof CloudConnectionError) return error.code === "network_unavailable";
    if (error instanceof TypeError) return true;
    // node:http surfaces connection failures as plain Error objects carrying a
    // syscall code; recognize those so transient outages are retried.
    if (error instanceof Error) {
      const code = (error as { code?: unknown }).code;
      return typeof code === "string" && NETWORK_ERROR_CODES.has(code);
    }
    return false;
  }

  // A 410 means the Host session expired before the result arrived. Keep the
  // result so the next handshake can replay it against the new session.
  private shouldRetainResult(error: unknown): boolean {
    return this.isNetworkError(error)
      || (error instanceof CloudConnectionError && error.status === 410);
  }

  private async delay(milliseconds: number): Promise<void> {
    if (milliseconds === 0) return;
    await new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  private isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  private requiredArray(body: unknown, field: string, message: string): unknown[] {
    if (this.isRecord(body) && Array.isArray(body[field])) return body[field] as unknown[];
    throw new ProtocolError("invalid_payload", message);
  }

  private optionalString(value: unknown): string | null {
    return typeof value === "string" ? value : null;
  }

  private optionalNumber(value: unknown): number | null {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
      return Number(value);
    }
    return null;
  }
}
