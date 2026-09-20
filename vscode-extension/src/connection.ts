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

type QueuedResult = {
  result: LocalValidationResult;
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

const DEFAULT_ACTIONS_PATH = "/api/v1/agent/local-validation/actions";
const DEFAULT_RESULTS_PATH = "/api/v1/agent/local-validation/results";
const DEFAULT_HANDSHAKE_PATH = "/api/v1/agent/host/handshake";

export class CloudConnection {
  private readonly baseUrl: string;
  private readonly accessToken: string;
  private readonly fetchImpl: FetchLike;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;
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
    this.actionsPath = options.actionsPath ?? DEFAULT_ACTIONS_PATH;
    this.resultsPath = options.resultsPath ?? DEFAULT_RESULTS_PATH;
    this.handshakePath = options.handshakePath ?? DEFAULT_HANDSHAKE_PATH;
    this.resultStore = options.resultStore;
  }

  get pendingResultCount(): number {
    return this.queuedResults.length;
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

  async streamAgentPrompt(
    request: Record<string, unknown>,
    onEvent: (event: AgentStreamEvent) => void | Promise<void>,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await this.request("/api/v1/agent/orchestrate/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
    if (!response.body) throw new CloudConnectionError("request_failed", "agent stream response has no body");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const data = frame.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
        if (!data) continue;
        await onEvent(JSON.parse(data) as AgentStreamEvent);
      }
      if (chunk.done) break;
    }
    const finalData = buffer.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
    if (finalData) await onEvent(JSON.parse(finalData) as AgentStreamEvent);
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

  async submitResult(resultInput: unknown): Promise<unknown> {
    const result = parseLocalValidationResult(resultInput);
    try {
      return await this.submitParsedResult(result);
    } catch (error) {
      if (this.isNetworkError(error)) {
        if (this.resultStore) await this.resultStore.enqueue(result);
        else this.queuedResults.push({ result });
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
        const response = await this.submitParsedResult(queued.result);
        this.queuedResults.shift();
        flushed += 1;
      } catch (error) {
        if (this.isNetworkError(error)) {
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
        const response = await this.submitParsedResult(record.result);
        await this.resultStore!.acknowledge(record.result.event_id);
        flushed += 1;
      } catch (error) {
        if (this.isNetworkError(error)) break;
        await this.resultStore!.acknowledge(record.result.event_id);
      }
    }
    return flushed;
  }

  private async submitParsedResult(result: LocalValidationResult): Promise<unknown> {
    const response = await this.request(this.resultsPath, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(result),
    });
    return this.readJson(response);
  }

  private async request(
    path: string,
    init: { method: string; headers?: Record<string, string>; body?: string; signal?: AbortSignal },
  ): Promise<HttpResponseLike> {
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      try {
        const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
          ...init,
          headers: {
            authorization: `Bearer ${this.accessToken}`,
            accept: "application/json",
            ...init.headers,
          },
        });
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
            `cloud request failed with status ${response.status}`,
            response.status,
          );
          if (!this.isRetryableStatus(response.status) || attempt === this.maxRetries) {
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
        if (!this.isNetworkError(error) || attempt === this.maxRetries) {
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

  private async readJson(response: HttpResponseLike): Promise<unknown> {
    try {
      return await response.json();
    } catch {
      throw new CloudConnectionError("request_failed", "cloud response is not valid JSON", response.status);
    }
  }

  private isRetryableStatus(status: number): boolean {
    return status === 408 || status === 429 || status >= 500;
  }

  private isNetworkError(error: unknown): boolean {
    return error instanceof CloudConnectionError
      ? error.code === "network_unavailable"
      : error instanceof TypeError;
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
