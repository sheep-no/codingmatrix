import assert from "node:assert/strict";
import * as vscode from "vscode";
import { EXTENSION_VERSION, assertCompatible } from "../dist/compatibility.js";

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function readBackendSessions(apiUrl, accessToken) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await fetch(`${apiUrl}/api/v1/agent/host/sessions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (response.status === 429) {
      await sleep(1000);
      continue;
    }
    assert.equal(response.ok, true, `backend session query failed: ${response.status}`);
    return response.json();
  }
  assert.fail("backend session query remained rate limited");
}

async function waitForBackendSession(apiUrl, accessToken, workspaceId) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const sessions = await readBackendSessions(apiUrl, accessToken);
    const matching = sessions.filter((item) => item.workspace_id === workspaceId);
    const session = matching.sort((left, right) =>
      right.expires_at.localeCompare(left.expires_at),
    )[0];
    if (session) return session;
    await sleep(1000);
  }
  assert.fail(`extension did not create a backend session for ${workspaceId}`);
}

async function runRealBackendChecks() {
  const apiUrl = process.env.CODINGMATRIX_E2E_API_URL;
  const accessToken = process.env.CODINGMATRIX_E2E_ACCESS_TOKEN;
  if (!apiUrl || !accessToken) return;

  const settings = vscode.workspace.getConfiguration("codingmatrix.agent");
  await readBackendSessions(apiUrl, accessToken);
  await settings.update("apiUrl", apiUrl, vscode.ConfigurationTarget.Global);
  await settings.update("accessToken", accessToken, vscode.ConfigurationTarget.Global);
  await vscode.commands.executeCommand("codingmatrix.reconnectAgentSession");

  const initial = await waitForBackendSession(apiUrl, accessToken, "fixtures");
  assert.equal(initial.control_status, "active");

  await vscode.commands.executeCommand("codingmatrix.pauseAgentSession");
  await sleep(1000);
  assert.equal((await waitForBackendSession(apiUrl, accessToken, "fixtures")).control_status, "paused");

  await vscode.commands.executeCommand("codingmatrix.resumeAgentSession");
  await sleep(1000);
  assert.equal((await waitForBackendSession(apiUrl, accessToken, "fixtures")).control_status, "active");

  await vscode.commands.executeCommand("codingmatrix.cancelAgentSession");
  await sleep(1000);
  assert.equal((await waitForBackendSession(apiUrl, accessToken, "fixtures")).control_status, "cancelled");
}

export async function run() {
  assert.ok(vscode.workspace.workspaceFolders?.length, "workspace folder should be open");
  assert.equal(vscode.workspace.workspaceFolders[0].name, "fixtures");
  const apiUrl = process.env.CODINGMATRIX_E2E_API_URL;
  const accessToken = process.env.CODINGMATRIX_E2E_ACCESS_TOKEN;
  if (apiUrl && accessToken) {
    const settings = vscode.workspace.getConfiguration("codingmatrix.agent");
    await settings.update("apiUrl", apiUrl, vscode.ConfigurationTarget.Global);
    await settings.update("accessToken", accessToken, vscode.ConfigurationTarget.Global);
    await settings.update("pollIntervalMs", 10000, vscode.ConfigurationTarget.Global);
  }
  const extension = vscode.extensions.getExtension("codingmatrix.codingmatrix-local-validation");
  assert.ok(extension, "extension should be discovered from package.json");
  await extension.activate();
  assert.equal(extension.isActive, true);

  assert.doesNotThrow(() => assertCompatible({
    schema_versions: [1],
    plugin_version: { min: EXTENSION_VERSION, max: "0.1.0" },
  }));
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes("codingmatrix.openAgentWorkbench"), "Agent workbench command should be registered");
  await vscode.commands.executeCommand("codingmatrix.openAgentWorkbench");
  await runRealBackendChecks();
}
