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
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
};

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
  private readonly queuedResolvers = new Map<string, QueuedResult>();

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

  async streamAgentPrompt(
    request: Record<string, unknown>,
    onEvent: (event: AgentStreamEvent) => void | Promise<void>,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await this.request("/api/v1/ai-agent/orchestrate/stream", {
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
        return new Promise(async (resolve, reject) => {
          const queued = { result, resolve, reject };
          if (this.resultStore) {
            try {
              await this.resultStore.enqueue(result);
              this.queuedResolvers.set(result.event_id, queued);
            } catch (enqueueError) {
              reject(enqueueError);
            }
            return;
          }
          this.queuedResults.push(queued);
        });
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
        queued.resolve(response);
        flushed += 1;
      } catch (error) {
        if (this.isNetworkError(error)) {
          break;
        }
        this.queuedResults.shift();
        queued.reject(error);
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
        this.queuedResolvers.get(record.result.event_id)?.resolve(response);
        this.queuedResolvers.delete(record.result.event_id);
        flushed += 1;
      } catch (error) {
        if (this.isNetworkError(error)) break;
        await this.resultStore!.acknowledge(record.result.event_id);
        this.queuedResolvers.get(record.result.event_id)?.reject(error);
        this.queuedResolvers.delete(record.result.event_id);
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
}
