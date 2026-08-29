import { AgentHostEnvelope } from "./agent-host.js";
import { WebviewBridge, WebviewMessage, WebviewTransport } from "./webview-bridge.js";

export const AGENT_WORKBENCH_VIEW_TYPE = "codingmatrix.agentWorkbench";
export const AGENT_WORKBENCH_COMMAND = "codingmatrix.openAgentWorkbench";

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

export function createAgentWorkbenchHtml(): string {
  return `<!doctype html>
<html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-codingmatrix-agent-host';"><style>
body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background);padding:20px;max-width:900px;margin:auto}h1{font-size:22px}button{color:var(--vscode-button-foreground);background:var(--vscode-button-background);border:0;padding:8px 14px;border-radius:3px}#status{color:var(--vscode-descriptionForeground);margin:12px 0}.panel{border:1px solid var(--vscode-panel-border);padding:14px;margin-top:16px;border-radius:5px}
</style></head><body><h1>CodingMatrix Agent</h1><div id="status">VS Code Agent 工作台已连接</div><div class="panel"><p>当前工作台共享 Web Agent 会话，可在这里继续对话、审批本地动作和查看验证结果。</p><button id="hello">连接本地 Agent Host</button></div><script nonce="codingmatrix-agent-host">
const vscode=acquireVsCodeApi(); document.getElementById('hello').addEventListener('click',()=>{vscode.postMessage({type:'workbench_ready'});document.getElementById('status').textContent='已发送工作台连接请求'}); window.addEventListener('message',event=>{if(event.data?.type==='agent_host_message') document.getElementById('status').textContent='已收到 Agent Host 事件'});
</script></body></html>`;
}

export class AgentWorkbenchController {
  private panel?: WebviewPanelLike;
  private bridge?: WebviewBridge;

  open(createPanel: () => WebviewPanelLike): WebviewPanelLike {
    if (this.panel) {
      this.panel.reveal();
      return this.panel;
    }
    const panel = createPanel();
    panel.webview.html = createAgentWorkbenchHtml();
    this.bridge = new WebviewBridge(this.transportFor(panel));
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

  private transportFor(panel: WebviewPanelLike): WebviewTransport {
    return {
      postMessage: async (message: WebviewMessage) => { await panel.webview.postMessage(message); },
      onMessage: (listener) => panel.webview.onDidReceiveMessage((message) => listener(message as WebviewMessage)),
    };
  }
}
