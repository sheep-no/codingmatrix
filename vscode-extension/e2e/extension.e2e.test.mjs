import assert from "node:assert/strict";
import * as vscode from "vscode";

suite("CodingMatrix Local Validation extension", () => {
  test("activates inside a real VS Code workspace", async () => {
    assert.ok(vscode.workspace.workspaceFolders?.length, "workspace folder should be open");
    assert.equal(vscode.workspace.workspaceFolders[0].name, "fixtures");

    const extension = vscode.extensions.getExtension("codingmatrix.codingmatrix-local-validation");
    assert.ok(extension, "extension should be discovered from package.json");
    await extension.activate();
    assert.equal(extension.isActive, true);
  });

  test("registers and opens the Agent workbench command", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes("codingmatrix.openAgentWorkbench"));
    await vscode.commands.executeCommand("codingmatrix.openAgentWorkbench");
  });

});
