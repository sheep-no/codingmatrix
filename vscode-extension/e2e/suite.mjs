import assert from "node:assert/strict";
import * as vscode from "vscode";
import { EXTENSION_VERSION, assertCompatible } from "../dist/compatibility.js";

export async function run() {
  assert.ok(vscode.workspace.workspaceFolders?.length, "workspace folder should be open");
  assert.equal(vscode.workspace.workspaceFolders[0].name, "fixtures");

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
}
