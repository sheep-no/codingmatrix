import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { ToolDispatcher, ToolDispatcherError } from "../dist/tool-dispatcher.js";
import { WorkspaceAuthorization } from "../dist/workspace-authorization.js";

const envelope = (capability, payload) => ({
  message_id: "message-1",
  schema_version: 1,
  session_id: "session-1",
  kind: "tool_action",
  capability,
  payload,
});

async function createDispatcher() {
  const root = await mkdtemp(join(tmpdir(), "codingmatrix-agent-host-"));
  const authorization = new WorkspaceAuthorization();
  await authorization.grant("workspace-1", root);
  const validationRunner = { run: async (action) => ({ action_id: action.action_id, status: "passed" }) };
  const dispatcher = new ToolDispatcher({
    authorization,
    validationRunner,
    diagnostics: async () => [{
      file: "src/example.ts",
      message: "unused variable",
      severity: 1,
      source: "typescript",
      code: 6133,
      range: { start: { line: 2, character: 4 }, end: { line: 2, character: 10 } },
    }],
  });
  return { root, dispatcher };
}

test("reads and writes only authorized workspace files with hashes", async () => {
  const { root, dispatcher } = await createDispatcher();
  try {
    await writeFile(join(root, "README.md"), "before", "utf8");
    const read = await dispatcher.dispatch(envelope("file", {
      workspace_id: "workspace-1",
      path: "README.md",
    }));
    assert.equal(read.content, "before");
    assert.match(read.hash, /^[a-f0-9]{64}$/);

    const written = await dispatcher.dispatch(envelope("file", {
      workspace_id: "workspace-1",
      path: "README.md",
      content: "after",
      expected_hash: read.hash,
    }));
    assert.equal(written.size_bytes, 5);
    assert.equal(await readFile(join(root, "README.md"), "utf8"), "after");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects stale file writes and workspace escapes", async () => {
  const { root, dispatcher } = await createDispatcher();
  try {
    await writeFile(join(root, "README.md"), "before", "utf8");
    await assert.rejects(
      dispatcher.dispatch(envelope("file", { workspace_id: "workspace-1", path: "README.md", content: "after", expected_hash: "stale" })),
      (error) => error instanceof ToolDispatcherError && error.code === "file_conflict",
    );
    await assert.rejects(
      dispatcher.dispatch(envelope("file", { workspace_id: "workspace-1", path: "../outside", content: "x" })),
      /escapes the workspace/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("dispatches diagnostics and validation through injected adapters", async () => {
  const { root, dispatcher } = await createDispatcher();
  try {
    const diagnostics = await dispatcher.dispatch(envelope("diagnostics", { workspace_id: "workspace-1" }));
    assert.deepEqual(diagnostics[0], {
      file: "src/example.ts",
      message: "unused variable",
      severity: 1,
      source: "typescript",
      code: 6133,
      range: { start: { line: 2, character: 4 }, end: { line: 2, character: 10 } },
    });
    assert.equal(diagnostics[0].source, "typescript");
    const result = await dispatcher.dispatch(envelope("validation", {
      action_id: "action-1",
      event_id: "event-1",
      schema_version: 1,
      session_id: "session-1",
      task_id: "task-1",
      revision: 0,
      workspace_id: "workspace-1",
      validation_scope: "local_runtime",
      operation: "unit_test",
      command: ["node", "--version"],
      working_directory: ".",
      timeout_seconds: 10,
      requested_by: "cloud",
    }));
    assert.equal(result.status, "passed");
    const terminal = await dispatcher.dispatch(envelope("terminal", {
      action_id: "action-terminal",
      event_id: "event-terminal",
      schema_version: 1,
      session_id: "session-1",
      task_id: "task-1",
      revision: 0,
      workspace_id: "workspace-1",
      validation_scope: "local_runtime",
      operation: "service_check",
      command: ["node", "--version"],
      working_directory: ".",
      timeout_seconds: 10,
      requested_by: "cloud",
    }));
    assert.equal(terminal.status, "passed");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("dispatches workspace root inspection through authorization", async () => {
  const { root } = await createDispatcher();
  const secondRoot = await mkdtemp(join(tmpdir(), "codingmatrix-agent-host-second-"));
  try {
    const authorization = new WorkspaceAuthorization();
    await authorization.grant("workspace-1", root);
    await authorization.grant("workspace-2", secondRoot);
    const dispatcher = new ToolDispatcher({
      authorization,
      validationRunner: { run: async () => ({ status: "passed" }) },
    });

    assert.deepEqual(
      await dispatcher.dispatch(envelope("workspace", { operation: "list_roots" })),
      [
        { workspace_id: "workspace-1", root },
        { workspace_id: "workspace-2", root: secondRoot },
      ],
    );
    await assert.rejects(
      dispatcher.dispatch(envelope("workspace", { operation: "unknown" })),
      (error) => error instanceof ToolDispatcherError && error.code === "invalid_action",
    );
  } finally {
    await rm(secondRoot, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
  }
});

test("honors local execution and operation policy", async () => {
  const { root, dispatcher } = await createDispatcher();
  try {
    dispatcher.setPolicy({
      local_execution_enabled: false,
      validation_operations: { unit_test: true },
      auto_approve: false,
      require_confirmation_on_failure: true,
    });
    await assert.rejects(
      dispatcher.dispatch(envelope("diagnostics", { workspace_id: "workspace-1" })),
      (error) => error instanceof ToolDispatcherError && error.code === "execution_disabled",
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
