import * as vscode from "vscode";
import { AgentWorkbenchController, AGENT_WORKBENCH_COMMAND, AGENT_WORKBENCH_VIEW_TYPE } from "./agent-workbench.js";

const controller = new AgentWorkbenchController();

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(vscode.commands.registerCommand(AGENT_WORKBENCH_COMMAND, () => controller.open(() => vscode.window.createWebviewPanel(AGENT_WORKBENCH_VIEW_TYPE, "CodingMatrix Agent", vscode.ViewColumn.One, { enableScripts: true }))));
}

export function deactivate(): void {}
