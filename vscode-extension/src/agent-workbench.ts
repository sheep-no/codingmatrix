import { AgentHostEnvelope } from "./agent-host.js";
import { WebviewBridge, WebviewMessage, WebviewTransport } from "./webview-bridge.js";
import { createAgentWorkbenchHtml } from "./workbench-html.js";

export { createAgentWorkbenchHtml } from "./workbench-html.js";

export const AGENT_WORKBENCH_VIEW_TYPE = "codingmatrix.agentWorkbench";
export const AGENT_WORKBENCH_COMMAND = "codingmatrix.openAgentWorkbench";

// Every read the workbench panels perform is listed here so an unknown resource
// from the webview is rejected instead of reaching the cloud connection.
export const WORKBENCH_RESOURCES = [
  "history_list",
  "history_messages",
  "history_delete",
  "model_config",
  "token_usage",
  "snapshot_list",
  "snapshot_rollback",
  "snapshot_diff",
  "performance",
] as const;

export type WorkbenchResource = (typeof WORKBENCH_RESOURCES)[number];

export interface WorkbenchRequest {
  request_id: string;
  resource: WorkbenchResource;
  params: Record<string, unknown>;
}

export interface WorkbenchResponse {
  type: "workbench_response";
  request_id: string;
  ok: boolean;
  data?: unknown;
  error?: string;
}

export interface WebviewPanelLike {
  webview: {
    html: string;
    onDidReceiveMessage(listener: (message: unknown) => void): { dispose(): void };
    postMessage(message: unknown): PromiseLike<boolean>;
  };
  onDidDispose(listener: () => void): { dispose(): void };
  reveal(viewColumn?: unknown): void;
  dispose(): void;
}

export interface AgentWorkbenchControllerOptions {
  onMessage?: (message: AgentHostEnvelope) => void | Promise<void>;
  onPrompt?: (prompt: string) => void | Promise<void>;
  onControl?: (action: "pause" | "resume" | "cancel") => void | Promise<void>;
  onRequest?: (request: WorkbenchRequest) => unknown | Promise<unknown>;
}

export class AgentWorkbenchController {
  private panel?: WebviewPanelLike;
  private bridge?: WebviewBridge;
  private readonly onMessage?: (message: AgentHostEnvelope) => void | Promise<void>;
  private readonly onPrompt?: (prompt: string) => void | Promise<void>;
  private readonly onControl?: AgentWorkbenchControllerOptions["onControl"];
  private readonly onRequest?: AgentWorkbenchControllerOptions["onRequest"];

  constructor(options: AgentWorkbenchControllerOptions = {}) {
    this.onMessage = options.onMessage;
    this.onPrompt = options.onPrompt;
    this.onControl = options.onControl;
    this.onRequest = options.onRequest;
  }

  open(createPanel: () => WebviewPanelLike): WebviewPanelLike {
    if (this.panel) {
      this.panel.reveal();
      return this.panel;
    }
    const panel = createPanel();
    panel.webview.html = createAgentWorkbenchHtml();
    this.bridge = new WebviewBridge(this.transportFor(panel));
    this.bridge.subscribe((message) => { void this.onMessage?.(message); });
    panel.webview.onDidReceiveMessage((message) => {
      if (typeof message !== "object" || message === null) return;
      const value = message as { type?: unknown; prompt?: unknown; action?: unknown };
      if (value.type === "workbench_prompt" && typeof value.prompt === "string" && value.prompt.trim()) {
        void this.onPrompt?.(value.prompt.trim());
      }
      if (value.type === "workbench_control" && (value.action === "pause" || value.action === "resume" || value.action === "cancel")) {
        void this.onControl?.(value.action);
      }
      const request = this.parseRequest(message);
      if (request) void this.handleRequest(panel, request);
    });
    panel.onDidDispose(() => {
      this.bridge?.dispose();
      this.bridge = undefined;
      this.panel = undefined;
    });
    this.panel = panel;
    return panel;
  }

  async publish(event: AgentHostEnvelope): Promise<void> {
    await this.bridge?.send(event);
  }

  async publishWorkbenchEvent(event: unknown): Promise<void> {
    await this.panel?.webview.postMessage({ type: "workbench_event", event });
  }

  // The webview asks for cloud data through one generic channel; unknown
  // resources and handler failures come back as an error response instead of
  // tearing down the panel.
  private parseRequest(message: unknown): WorkbenchRequest | undefined {
    if (typeof message !== "object" || message === null) return undefined;
    const value = message as {
      type?: unknown;
      request_id?: unknown;
      resource?: unknown;
      params?: unknown;
    };
    if (value.type !== "workbench_request") return undefined;
    if (typeof value.request_id !== "string" || !value.request_id) return undefined;
    if (!WORKBENCH_RESOURCES.includes(value.resource as WorkbenchResource)) return undefined;
    const params = value.params === undefined ? {} : value.params;
    if (typeof params !== "object" || params === null || Array.isArray(params)) return undefined;
    return {
      request_id: value.request_id,
      resource: value.resource as WorkbenchResource,
      params: { ...(params as Record<string, unknown>) },
    };
  }

  private async handleRequest(panel: WebviewPanelLike, request: WorkbenchRequest): Promise<void> {
    const response: WorkbenchResponse = {
      type: "workbench_response",
      request_id: request.request_id,
      ok: true,
    };
    if (!this.onRequest) {
      response.ok = false;
      response.error = "工作台数据通道尚未连接";
    } else {
      try {
        response.data = await this.onRequest(request);
      } catch (error) {
        response.ok = false;
        response.error = error instanceof Error ? error.message : "请求失败";
      }
    }
    try {
      await panel.webview.postMessage(response);
    } catch {
      // A disposed panel cannot receive the response; the webview is gone.
    }
  }

  private transportFor(panel: WebviewPanelLike): WebviewTransport {
    return {
      postMessage: async (message: WebviewMessage) => { await panel.webview.postMessage(message); },
      onMessage: (listener) => panel.webview.onDidReceiveMessage((message) => listener(message as WebviewMessage)),
    };
  }
}
