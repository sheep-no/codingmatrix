import assert from "node:assert/strict";
import test from "node:test";
import {
  ProtocolError,
  parseLocalValidationResult,
  parsePendingAction,
} from "../dist/protocol.js";

const action = {
  action_id: "action-1",
  event_id: "event-1",
  schema_version: 1,
  session_id: "session-1",
  task_id: "task-1",
  revision: 2,
  workspace_id: "workspace-1",
  validation_scope: "local_runtime",
  operation: "unit_test",
  command: ["python3", "-m", "pytest"],
  working_directory: ".",
  timeout_seconds: 60,
  requested_by: "cloud",
};

test("parses a valid pending action", () => {
  assert.deepEqual(parsePendingAction(action), action);
});

test("rejects cloud validation scope for local actions", () => {
  assert.throws(
    () => parsePendingAction({ ...action, validation_scope: "cloud_syntax" }),
    (error) => error instanceof ProtocolError && error.code === "invalid_payload",
  );
});

test("rejects unsupported schema versions", () => {
  assert.throws(
    () => parsePendingAction({ ...action, schema_version: 2 }),
    (error) => error instanceof ProtocolError && error.code === "unsupported_contract",
  );
});

test("rejects workspace escaping paths", () => {
  assert.throws(() => parsePendingAction({ ...action, working_directory: "../other" }));
});

test("round trips a local validation result", () => {
  const result = {
    event_id: "result-1",
    schema_version: 1,
    session_id: "session-1",
    task_id: "task-1",
    revision: 2,
    source: "local",
    validation_scope: "local_e2e",
    status: "passed",
    started_at: "2026-08-29T00:00:00Z",
    finished_at: "2026-08-29T00:01:00Z",
    exit_code: 0,
    summary: {
      command_name: "playwright",
      tests_total: 4,
      tests_passed: 4,
      tests_failed: 0,
      diagnostics: [],
    },
  };
  assert.deepEqual(parseLocalValidationResult(JSON.parse(JSON.stringify(result))), result);
});

test("rejects results from cloud source", () => {
  assert.throws(() =>
    parseLocalValidationResult({
      event_id: "result-1",
      schema_version: 1,
      session_id: "session-1",
      task_id: "task-1",
      revision: 2,
      source: "cloud",
      validation_scope: "local_runtime",
      status: "passed",
      started_at: "2026-08-29T00:00:00Z",
      finished_at: "2026-08-29T00:01:00Z",
      summary: { command_name: "pytest", diagnostics: [] },
    }),
  );
});
