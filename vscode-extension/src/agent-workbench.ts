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

export interface AgentWorkbenchControllerOptions {
  onMessage?: (message: AgentHostEnvelope) => void | Promise<void>;
  onPrompt?: (prompt: string) => void | Promise<void>;
  onControl?: (action: "pause" | "resume" | "cancel") => void | Promise<void>;
}

export function createAgentWorkbenchHtml(): string {
  return `<!doctype html>
<html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-codingmatrix-agent-host';"><style>
body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background);padding:20px;max-width:900px;margin:auto}h1{font-size:22px}button{color:var(--vscode-button-foreground);background:var(--vscode-button-background);border:0;padding:8px 14px;border-radius:3px;margin:4px 4px 4px 0}textarea{display:block;width:100%;min-height:90px;margin:10px 0;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border)}#status{color:var(--vscode-descriptionForeground);margin:12px 0}.panel{border:1px solid var(--vscode-panel-border);padding:14px;margin-top:16px;border-radius:5px}
</style></head><body><h1>CodingMatrix Agent</h1><div id="status">VS Code Agent 工作台已连接</div><div class="panel"><p>当前工作台共享 Web Agent 会话，可在这里继续对话、审批本地动作和查看验证结果。</p><textarea id="prompt" maxlength="5000" placeholder="输入 Agent 需求"></textarea><button id="send">发送需求</button><button id="hello">连接本地 Agent Host</button><button id="pause">暂停</button><button id="resume">恢复</button><button id="cancel">取消</button><button id="approve" hidden>批准当前动作</button><button id="reject" hidden>拒绝当前动作</button><div id="messages" aria-live="polite"></div></div><script nonce="codingmatrix-agent-host">
const vscode=acquireVsCodeApi();let approval;const prompt=document.getElementById('prompt'),send=document.getElementById('send'),messages=document.getElementById('messages'),status=document.getElementById('status'),approve=document.getElementById('approve'),reject=document.getElementById('reject');const append=(text,error=false)=>{const item=document.createElement('p');item.style.whiteSpace='pre-wrap';item.style.borderLeft='3px solid '+(error?'var(--vscode-errorForeground)':'var(--vscode-textLink-foreground)');item.style.padding='8px';item.textContent=text;messages.appendChild(item);messages.scrollTop=messages.scrollHeight;};const control=(action)=>{vscode.postMessage({type:'workbench_control',action});status.textContent=action==='pause'?'Agent 已暂停':action==='resume'?'Agent 正在恢复':'Agent 已取消';};document.getElementById('hello').addEventListener('click',()=>{vscode.postMessage({type:'workbench_ready'});status.textContent='已发送工作台连接请求'});send.addEventListener('click',()=>{const value=prompt.value.trim();if(!value)return;append('你：'+value);vscode.postMessage({type:'workbench_prompt',prompt:value});prompt.value='';send.disabled=true;status.textContent='Agent 正在处理'});document.getElementById('pause').addEventListener('click',()=>control('pause'));document.getElementById('resume').addEventListener('click',()=>control('resume'));document.getElementById('cancel').addEventListener('click',()=>control('cancel'));function decide(approved){if(!approval)return;vscode.postMessage({type:'agent_host_message',message:{...approval,kind:'approval_decision',message_id:approval.message_id+':decision',payload:{request_id:approval.message_id,approved}}});approval=undefined;approve.hidden=true;reject.hidden=true;}approve.addEventListener('click',()=>decide(true));reject.addEventListener('click',()=>decide(false));window.addEventListener('message',event=>{const data=event.data;if(data?.type==='workbench_event'){const value=data.event||{};const payload=value.data||{};if(value.type==='done'){status.textContent='Agent 已完成';send.disabled=false;}if(value.type==='error'){status.textContent='Agent 执行失败';send.disabled=false;}const text=typeof payload==='string'?payload:payload.message||payload.error||value.type;if(text)append(value.type+'：'+text,value.type==='error');return;}if(data?.type!=='agent_host_message')return;status.textContent='已收到 Agent Host 事件';if(data.message?.kind==='approval_request'){approval=data.message;approve.hidden=false;reject.hidden=false;append('等待审批：'+(data.message.payload?.reason||data.message.capability));}});
</script></body></html>`;
}

export class AgentWorkbenchController {
  private panel?: WebviewPanelLike;
  private bridge?: WebviewBridge;
  private readonly onMessage?: (message: AgentHostEnvelope) => void | Promise<void>;
  private readonly onPrompt?: (prompt: string) => void | Promise<void>;
  private readonly onControl?: AgentWorkbenchControllerOptions["onControl"];

  constructor(options: AgentWorkbenchControllerOptions = {}) {
    this.onMessage = options.onMessage;
    this.onPrompt = options.onPrompt;
    this.onControl = options.onControl;
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

  private transportFor(panel: WebviewPanelLike): WebviewTransport {
    return {
      postMessage: async (message: WebviewMessage) => { await panel.webview.postMessage(message); },
      onMessage: (listener) => panel.webview.onDidReceiveMessage((message) => listener(message as WebviewMessage)),
    };
  }
}
