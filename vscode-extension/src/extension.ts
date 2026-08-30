import * as vscode from "vscode";
import { spawn } from "node:child_process";
import { AgentHostSession } from "./agent-host.js";
import { AgentWorkbenchController, AGENT_WORKBENCH_COMMAND, AGENT_WORKBENCH_VIEW_TYPE } from "./agent-workbench.js";
import { AgentHostRuntime } from "./agent-host-runtime.js";
import { ApprovalBridge } from "./approval-bridge.js";
import { ToolDispatcher } from "./tool-dispatcher.js";
import { ValidationRunner } from "./validation-runner.js";
import { WorkspaceAuthorization } from "./workspace-authorization.js";
import { CloudConnection } from "./connection.js";
import { discoverWorkspaceSkills, WorkspaceSkillRoot } from "./skill-discovery.js";

let runtime: AgentHostRuntime | undefined;
let pollTimer: ReturnType<typeof setInterval> | undefined;
const controller = new AgentWorkbenchController({
  onMessage: async (message) => {
    if (runtime) await runtime.process(message);
  },
});

export function activate(context: vscode.ExtensionContext): void {
  const workspace = vscode.workspace.workspaceFolders?.[0];
  if (workspace) {
    const authorization = new WorkspaceAuthorization();
    const session = new AgentHostSession();
    const policy = {
      local_execution_enabled: true,
      validation_operations: {},
      auto_approve: false,
      require_confirmation_on_failure: true,
    };
    void authorization.grant(workspace.name, workspace.uri.fsPath).then(() => {
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
      const dispatcher = new ToolDispatcher({ authorization, validationRunner: runner, policy });
      const approval = new ApprovalBridge({ onRequest: (event) => controller.publish(event) });
      const settings = vscode.workspace.getConfiguration("codingmatrix.agent");
      const apiUrl = settings.get<string>("apiUrl")?.trim();
      const accessToken = settings.get<string>("accessToken")?.trim();
      const connection = apiUrl && accessToken
        ? new CloudConnection({ baseUrl: apiUrl, accessToken })
        : undefined;
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
      if (connection) {
        const folders: WorkspaceSkillRoot[] = (vscode.workspace.workspaceFolders ?? []).map((folder) => ({ name: folder.name, path: folder.uri.fsPath }));
        void startCloudConnection(connection, runtime, folders, workspace.name, settings.get<number>("pollIntervalMs", 1000) ?? 1000, context)
          .catch(async () => {
            await vscode.commands.executeCommand("setContext", "codingmatrix.agentConnectionStatus", "offline");
          });
      }
    });
  }
  context.subscriptions.push(vscode.commands.registerCommand(AGENT_WORKBENCH_COMMAND, () => controller.open(() => vscode.window.createWebviewPanel(AGENT_WORKBENCH_VIEW_TYPE, "CodingMatrix Agent", vscode.ViewColumn.One, { enableScripts: true }))));
}

export function deactivate(): void {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = undefined;
  runtime = undefined;
}

async function startCloudConnection(
  connection: CloudConnection,
  hostRuntime: AgentHostRuntime,
  workspaceFolders: WorkspaceSkillRoot[],
  workspaceId: string,
  pollIntervalMs: number,
  context: vscode.ExtensionContext,
): Promise<void> {
  await connection.handshake({
    workspace_id: workspaceId,
    extension_version: "0.1.0",
    protocol_versions: [1],
    capabilities: ["workspace", "file", "terminal", "diagnostics", "validation", "skill_runtime"],
  });
  const syncSkills = async (): Promise<void> => {
    const skills = await discoverWorkspaceSkills(workspaceFolders);
    await connection.syncSkills(skills);
  };
  await syncSkills();
  const watchers = workspaceFolders.flatMap((folder) => [
    vscode.workspace.createFileSystemWatcher(`${folder.path}/.claude/skills/**`),
    vscode.workspace.createFileSystemWatcher(`${folder.path}/skills/**`),
    vscode.workspace.createFileSystemWatcher(`${folder.path}/data/custom_skills/**/*.md`),
  ]);
  let syncTimer: ReturnType<typeof setTimeout> | undefined;
  const scheduleSync = (): void => {
    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(() => { void syncSkills(); }, 200);
  };
  for (const watcher of watchers) {
    context.subscriptions.push(watcher, watcher.onDidCreate(scheduleSync), watcher.onDidChange(scheduleSync), watcher.onDidDelete(scheduleSync));
  }
  await hostRuntime.poll();
  pollTimer = setInterval(() => { void hostRuntime.poll(); }, Math.max(250, pollIntervalMs));
}
