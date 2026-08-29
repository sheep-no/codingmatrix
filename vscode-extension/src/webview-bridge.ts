import { AgentHostEnvelope, parseAgentHostEnvelope } from "./agent-host.js";

export interface WebviewMessage {
  type: "agent_host_message" | "agent_host_request" | "agent_host_response";
  request_id?: string;
  message?: unknown;
  error?: string;
}

export interface WebviewTransport {
  postMessage(message: WebviewMessage): void | Promise<void>;
  onMessage(listener: (message: WebviewMessage) => void): void;
}

export class WebviewBridgeError extends Error {
  constructor(public readonly code: "invalid_message" | "request_failed" | "request_timeout", message: string) {
    super(message);
    this.name = "WebviewBridgeError";
  }
}

export class WebviewBridge {
  private readonly transport: WebviewTransport;
  private readonly pending = new Map<string, { resolve: (value: AgentHostEnvelope) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  private readonly subscribers = new Set<(message: AgentHostEnvelope) => void>();

  constructor(transport: WebviewTransport) {
    this.transport = transport;
    transport.onMessage((message) => this.receive(message));
  }

  subscribe(listener: (message: AgentHostEnvelope) => void): () => void {
    this.subscribers.add(listener);
    return () => this.subscribers.delete(listener);
  }

  async send(message: AgentHostEnvelope): Promise<void> {
    parseAgentHostEnvelope(message);
    await this.transport.postMessage({ type: "agent_host_message", message });
  }

  request(message: AgentHostEnvelope, timeoutMs = 10_000): Promise<AgentHostEnvelope> {
    parseAgentHostEnvelope(message);
    if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
      return Promise.reject(new WebviewBridgeError("request_timeout", "request timeout must be positive"));
    }
    const requestId = message.message_id;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new WebviewBridgeError("request_timeout", `webview request ${requestId} timed out`));
      }, timeoutMs);
      this.pending.set(requestId, { resolve, reject, timer });
      void Promise.resolve(this.transport.postMessage({ type: "agent_host_request", request_id: requestId, message }))
        .catch((error: unknown) => {
          clearTimeout(timer);
          this.pending.delete(requestId);
          reject(error instanceof Error ? error : new WebviewBridgeError("request_failed", "webview request failed"));
        });
    });
  }

  dispose(): void {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(new WebviewBridgeError("request_failed", "webview bridge disposed"));
    }
    this.pending.clear();
    this.subscribers.clear();
  }

  private receive(message: WebviewMessage): void {
    if (message.type === "agent_host_response") {
      const requestId = message.request_id;
      const pending = requestId ? this.pending.get(requestId) : undefined;
      if (!pending) return;
      clearTimeout(pending.timer);
      this.pending.delete(requestId!);
      if (message.error) {
        pending.reject(new WebviewBridgeError("request_failed", message.error));
        return;
      }
      try {
        pending.resolve(parseAgentHostEnvelope(message.message));
      } catch (error) {
        pending.reject(error instanceof Error ? error : new WebviewBridgeError("invalid_message", "invalid webview response"));
      }
      return;
    }
    if (message.type !== "agent_host_message") return;
    try {
      const envelope = parseAgentHostEnvelope(message.message);
      for (const subscriber of this.subscribers) subscriber(envelope);
    } catch {
      // Invalid messages are isolated from the bridge event loop.
    }
  }
}
