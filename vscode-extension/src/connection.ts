import {
  LocalValidationResult,
  PendingAction,
  parseLocalValidationResult,
  parsePendingAction,
  ProtocolError,
} from "./protocol.js";

export interface HttpResponseLike {
  readonly ok: boolean;
  readonly status: number;
  json(): Promise<unknown>;
  text(): Promise<string>;
}

export type FetchLike = (
  input: string,
  init?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
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

export class CloudConnection {
  private readonly baseUrl: string;
  private readonly accessToken: string;
  private readonly fetchImpl: FetchLike;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;
  private readonly actionsPath: string;
  private readonly resultsPath: string;
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
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.maxRetries = options.maxRetries ?? 2;
    this.retryDelayMs = options.retryDelayMs ?? 250;
    this.actionsPath = options.actionsPath ?? DEFAULT_ACTIONS_PATH;
    this.resultsPath = options.resultsPath ?? DEFAULT_RESULTS_PATH;
  }

  get pendingResultCount(): number {
    return this.queuedResults.length;
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
        return new Promise((resolve, reject) => {
          this.queuedResults.push({ result, resolve, reject });
        });
      }
      throw error;
    }
  }

  async flushPendingResults(): Promise<number> {
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
    init: { method: string; headers?: Record<string, string>; body?: string },
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
            "cloud network request failed",
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
