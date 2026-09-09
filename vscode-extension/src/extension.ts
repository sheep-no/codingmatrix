import * as vscode from "vscode";
import { spawn } from "node:child_process";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { AgentHostSession } from "./agent-host.js";
import { AgentWorkbenchController, AGENT_WORKBENCH_COMMAND, AGENT_WORKBENCH_VIEW_TYPE } from "./agent-workbench.js";
import { AgentHostRuntime } from "./agent-host-runtime.js";
import { ApprovalBridge } from "./approval-bridge.js";
import { ToolDispatcher } from "./tool-dispatcher.js";
import { ValidationRunner } from "./validation-runner.js";
import { WorkspaceAuthorization } from "./workspace-authorization.js";
import { CloudConnection } from "./connection.js";
import { discoverWorkspaceSkills, WorkspaceSkillRoot } from "./skill-discovery.js";
import { ResultStore, ResultStorage } from "./result-store.js";

declare const process: { env: Record<string, string | undefined> };

let runtime: AgentHostRuntime | undefined;
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let connectionStartId = 0;
let cloudConnection: CloudConnection | undefined;
let agentConversationId = `vscode-agent-${Date.now()}`;
let hostSession: AgentHostSession | undefined;
let connectionFolders: WorkspaceSkillRoot[] = [];
let connectionWorkspaceId = "";
let extensionContext: vscode.ExtensionContext | undefined;
let resultStore: ResultStore | undefined;
let connectionDisposables: vscode.Disposable[] = [];
let skillSyncTimer: ReturnType<typeof setTimeout> | undefined;
let promptAbortController: AbortController | undefined;
let extensionLifecycleId = 0;
const controller = new AgentWorkbenchController({
  onMessage: async (message) => {
    if (runtime) await runtime.process(message);
  },
  onPrompt: async (prompt) => {
    if (!cloudConnection) {
      await controller.publishWorkbenchEvent({ type: "error", data: { error: "云端 Agent 尚未连接" } });
      return;
    }
    promptAbortController?.abort();
    const requestController = new AbortController();
    promptAbortController = requestController;
    try {
      await cloudConnection.streamAgentPrompt(
        { requirement: prompt, session_id: agentConversationId },
        (event) => controller.publishWorkbenchEvent(event),
        requestController.signal,
      );
    } catch (error) {
      if (requestController.signal.aborted) return;
      await controller.publishWorkbenchEvent({
        type: "error",
        data: { error: error instanceof Error ? error.message : "Agent 请求失败" },
      });
    } finally {
      if (promptAbortController === requestController) promptAbortController = undefined;
    }
  },
  onControl: async (action) => {
    if (!cloudConnection) {
      await controller.publishWorkbenchEvent({ type: "error", data: { error: "云端 Agent 尚未连接" } });
      return;
    }
    try {
      if (action === "cancel") {
        promptAbortController?.abort();
        runtime?.cancelActiveActions();
      }
      const result = await cloudConnection.controlSession(action);
      await vscode.commands.executeCommand("setContext", "codingmatrix.agentSessionStatus", result.status);
      await controller.publishWorkbenchEvent({ type: "progress", data: { message: `会话状态：${result.status}` } });
    } catch (error) {
      await controller.publishWorkbenchEvent({ type: "error", data: { error: error instanceof Error ? error.message : "会话控制失败" } });
    }
  },
});

export function activate(context: vscode.ExtensionContext): void {
  const lifecycleId = ++extensionLifecycleId;
  resultStore = new ResultStore(new VscodeResultStorage(context.globalState));
  const workspaceFolders = vscode.workspace.workspaceFolders ?? [];
  const workspace = workspaceFolders[0];
  if (workspaceFolders.length > 0) {
    const workspaceSlug = workspace.name.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 80) || "workspace";
    agentConversationId = `vscode-agent-${workspaceSlug}-${Date.now()}`;
    const authorization = new WorkspaceAuthorization();
    const session = new AgentHostSession();
    const policy = {
      local_execution_enabled: true,
      validation_operations: {},
      auto_approve: false,
      require_confirmation_on_failure: true,
    };
    void Promise.all(workspaceFolders.map((folder) => authorization.grant(folder.name, folder.uri.fsPath))).then(() => {
      if (lifecycleId !== extensionLifecycleId) return;
      session.acceptHandshake({
        session_id: "vscode-local-session",
        workspace_id: workspace.name,
        extension_version: "0.1.0",
        protocol_version: 1,
        capabilities: ["workspace", "file", "terminal", "diagnostics", "validation", "skill_runtime"],
        policy_version: 1,
        policy,
        pending_actions: [],
      });
      const runner = new ValidationRunner({ spawn });
      const dispatcher = new ToolDispatcher({
        authorization,
        validationRunner: runner,
        diagnostics: async (workspaceId) => serializeWorkspaceDiagnostics(workspaceId, authorization),
        policy,
      });
      const approval = new ApprovalBridge({ onRequest: (event) => controller.publish(event) });
      const settings = vscode.workspace.getConfiguration("codingmatrix.agent");
      const apiUrl = settings.get<string>("apiUrl")?.trim() || process.env.CODINGMATRIX_E2E_API_URL;
      const accessToken = settings.get<string>("accessToken")?.trim() || process.env.CODINGMATRIX_E2E_ACCESS_TOKEN;
      const connection = apiUrl && accessToken
        ? new CloudConnection({ baseUrl: apiUrl, accessToken, resultStore })
        : undefined;
      cloudConnection = connection;
      runtime = new AgentHostRuntime({
        session,
        dispatcher,
        connection,
        approvalBridge: approval,
        onEvent: (event) => controller.publish(event),
        onSessionControl: async (action) => {
          await vscode.commands.executeCommand("setContext", "codingmatrix.agentSessionStatus", action === "cancel" ? "cancelled" : action === "pause" ? "paused" : "active");
        },
        onSkillSync: async (skills) => {
          await vscode.commands.executeCommand("setContext", "codingmatrix.agentSkills", Object.keys(skills));
        },
        onSkillRevoke: async (skillName) => {
          await vscode.commands.executeCommand("setContext", "codingmatrix.agentSkillRevoked", skillName);
        },
      });
      hostSession = session;
      connectionFolders = workspaceFolders.map((folder) => ({ name: folder.name, path: folder.uri.fsPath }));
      connectionWorkspaceId = workspace.name;
      extensionContext = context;
      if (connection) {
        void startCloudConnection(connection, runtime, session, connectionFolders, workspace.name, settings.get<number>("pollIntervalMs", 1000) ?? 1000, context)
          .catch(async () => {
            await vscode.commands.executeCommand("setContext", "codingmatrix.agentConnectionStatus", "offline");
          });
      }
    }).catch(async (error) => {
      if (lifecycleId !== extensionLifecycleId) return;
      await vscode.commands.executeCommand("setContext", "codingmatrix.agentConnectionStatus", "offline");
      await controller.publishWorkbenchEvent({
        type: "error",
        data: { error: error instanceof Error ? error.message : "工作区授权初始化失败" },
      });
    });
  }
  context.subscriptions.push(vscode.commands.registerCommand(AGENT_WORKBENCH_COMMAND, () => controller.open(() => vscode.window.createWebviewPanel(AGENT_WORKBENCH_VIEW_TYPE, "CodingMatrix Agent", vscode.ViewColumn.One, { enableScripts: true }))));
  for (const [command, action] of [
    ["codingmatrix.pauseAgentSession", "pause"],
    ["codingmatrix.resumeAgentSession", "resume"],
    ["codingmatrix.cancelAgentSession", "cancel"],
  ] as const) {
    context.subscriptions.push(vscode.commands.registerCommand(command, async () => {
      if (!cloudConnection) {
        await controller.publishWorkbenchEvent({ type: "error", data: { error: "云端 Agent 尚未连接" } });
        return;
      }
      try {
        if (action === "cancel") {
          promptAbortController?.abort();
          runtime?.cancelActiveActions();
        }
        const result = await cloudConnection.controlSession(action);
        await vscode.commands.executeCommand("setContext", "codingmatrix.agentSessionStatus", result.status);
        await controller.publishWorkbenchEvent({ type: "progress", data: { message: `会话状态：${result.status}` } });
      } catch (error) {
        await controller.publishWorkbenchEvent({ type: "error", data: { error: error instanceof Error ? error.message : "会话控制失败" } });
      }
    }));
  }
  context.subscriptions.push(vscode.commands.registerCommand("codingmatrix.reconnectAgentSession", () => reconnectConfiguredSession()));
}

export function deactivate(): void {
  extensionLifecycleId += 1;
  disposeConnectionResources();
  runtime?.cancelActiveActions();
  promptAbortController?.abort();
  promptAbortController = undefined;
  cloudConnection = undefined;
  runtime = undefined;
  hostSession = undefined;
  extensionContext = undefined;
  resultStore = undefined;
}

async function reconnectConfiguredSession(): Promise<void> {
  if (!runtime || !hostSession || !extensionContext || !connectionWorkspaceId) return;
  const settings = vscode.workspace.getConfiguration("codingmatrix.agent");
  const apiUrl = settings.get<string>("apiUrl")?.trim() || process.env.CODINGMATRIX_E2E_API_URL;
  const accessToken = settings.get<string>("accessToken")?.trim() || process.env.CODINGMATRIX_E2E_ACCESS_TOKEN;
  if (!apiUrl || !accessToken) return;
  const connection = new CloudConnection({
    baseUrl: apiUrl,
    accessToken,
    resultStore,
  });
  cloudConnection = connection;
  runtime.setConnection(connection);
  await startCloudConnection(connection, runtime, hostSession, connectionFolders, connectionWorkspaceId, settings.get<number>("pollIntervalMs", 1000) ?? 1000, extensionContext);
}

class VscodeResultStorage implements ResultStorage {
  constructor(private readonly state: vscode.Memento) {}

  get<T>(key: string, fallback: T): Promise<T> {
    return Promise.resolve(this.state.get(key, fallback));
  }

  async update<T>(key: string, value: T): Promise<void> {
    await this.state.update(key, value);
  }
}

async function serializeWorkspaceDiagnostics(
  workspaceId: string,
  authorization: WorkspaceAuthorization,
): Promise<Array<Record<string, unknown>>> {
  const workspace = authorization.listAuthorized().find((item) => item.workspace_id === workspaceId);
  if (!workspace) return [];
  const root = resolve(workspace.root);
  const serialized: Array<Record<string, unknown>> = [];
  for (const [uri, diagnostics] of vscode.languages.getDiagnostics()) {
    const filePath = resolve(uri.fsPath);
    const fileRelativePath = relative(root, filePath);
    if (fileRelativePath === ".." || fileRelativePath.startsWith(`..${sep}`) || isAbsolute(fileRelativePath) || fileRelativePath === "") continue;
    for (const diagnostic of diagnostics) {
      serialized.push({
        file: fileRelativePath,
        message: diagnostic.message,
        severity: diagnostic.severity,
        source: diagnostic.source,
        code: typeof diagnostic.code === "object" && diagnostic.code !== null
          ? diagnostic.code.value
          : diagnostic.code,
        range: {
          start: { line: diagnostic.range.start.line, character: diagnostic.range.start.character },
          end: { line: diagnostic.range.end.line, character: diagnostic.range.end.character },
        },
      });
    }
  }
  return serialized;
}

async function startCloudConnection(
  connection: CloudConnection,
  hostRuntime: AgentHostRuntime,
  session: AgentHostSession,
  workspaceFolders: WorkspaceSkillRoot[],
  workspaceId: string,
  pollIntervalMs: number,
  context: vscode.ExtensionContext,
): Promise<void> {
  disposeConnectionResources();
  const startId = ++connectionStartId;
  const handshake = await connection.handshake({
    workspace_id: workspaceId,
    extension_version: "0.1.0",
    protocol_versions: [1],
    capabilities: ["workspace", "file", "terminal", "diagnostics", "validation", "skill_runtime"],
  });
  if (startId !== connectionStartId) return;
  session.acceptHandshake(handshake);
  hostRuntime.resetForHandshake();
  const syncSkills = async (): Promise<void> => {
    const skills = await discoverWorkspaceSkills(workspaceFolders);
    await connection.syncSkills(skills);
  };
  await syncSkills();
  if (startId !== connectionStartId) return;
  const watchers = workspaceFolders.flatMap((folder) => [
    vscode.workspace.createFileSystemWatcher(`${folder.path}/.claude/skills/**`),
    vscode.workspace.createFileSystemWatcher(`${folder.path}/skills/**`),
    vscode.workspace.createFileSystemWatcher(`${folder.path}/data/custom_skills/**/*.md`),
  ]);
  const scheduleSync = (): void => {
    if (skillSyncTimer) clearTimeout(skillSyncTimer);
    skillSyncTimer = setTimeout(() => {
      void syncSkills().catch(async () => {
        await vscode.commands.executeCommand("setContext", "codingmatrix.agentConnectionStatus", "offline");
      });
    }, 200);
  };
  for (const watcher of watchers) {
    connectionDisposables.push(watcher, watcher.onDidCreate(scheduleSync), watcher.onDidChange(scheduleSync), watcher.onDidDelete(scheduleSync));
  }
  context.subscriptions.push(...connectionDisposables);
  const interval = Math.max(250, pollIntervalMs);
  const poll = async (): Promise<void> => {
    try {
      await hostRuntime.poll();
      if (startId === connectionStartId) {
        await vscode.commands.executeCommand("setContext", "codingmatrix.agentConnectionStatus", "online");
      }
    } catch {
      if (startId === connectionStartId) {
        await vscode.commands.executeCommand("setContext", "codingmatrix.agentConnectionStatus", "offline");
      }
    } finally {
      if (startId === connectionStartId) {
        pollTimer = setTimeout(() => { void poll(); }, interval);
      }
    }
  };
  await poll();
}

function disposeConnectionResources(): void {
  connectionStartId += 1;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = undefined;
  if (skillSyncTimer) clearTimeout(skillSyncTimer);
  skillSyncTimer = undefined;
  for (const disposable of connectionDisposables) disposable.dispose();
  connectionDisposables = [];
}
