import * as vscode from "vscode";
import { spawn } from "node:child_process";
import { AgentHostSession } from "./agent-host.js";
import { AgentWorkbenchController, AGENT_WORKBENCH_COMMAND, AGENT_WORKBENCH_VIEW_TYPE } from "./agent-workbench.js";
import { AgentHostRuntime } from "./agent-host-runtime.js";
import { ApprovalBridge } from "./approval-bridge.js";
import { ToolDispatcher } from "./tool-dispatcher.js";
import { ValidationRunner } from "./validation-runner.js";
import { WorkspaceAuthorization } from "./workspace-authorization.js";

let runtime: AgentHostRuntime | undefined;
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
      runtime = new AgentHostRuntime({
        session,
        dispatcher,
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
    });
  }
  context.subscriptions.push(vscode.commands.registerCommand(AGENT_WORKBENCH_COMMAND, () => controller.open(() => vscode.window.createWebviewPanel(AGENT_WORKBENCH_VIEW_TYPE, "CodingMatrix Agent", vscode.ViewColumn.One, { enableScripts: true }))));
}

export function deactivate(): void {}
