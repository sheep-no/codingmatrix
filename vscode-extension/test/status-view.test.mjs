import assert from "node:assert/strict";
import test from "node:test";
import { ValidationStatusView } from "../dist/status-view.js";

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
  working_directory: "/projects/demo",
  timeout_seconds: 60,
  requested_by: "cloud",
};

const result = {
  event_id: "result-1",
  schema_version: 1,
  session_id: "session-1",
  task_id: "task-1",
  revision: 2,
  source: "local",
  validation_scope: "local_runtime",
  status: "failed",
  started_at: "2026-08-29T00:00:00.000Z",
  finished_at: "2026-08-29T00:00:05.000Z",
  exit_code: 1,
  summary: { command_name: "pytest", diagnostics: [{ message: "test failed", file: "tests/test_demo.py" }] },
};

test("shows authorization wait with workspace diagnostic", () => {
  const view = new ValidationStatusView();
  const display = view.showAction(action, false);

  assert.equal(display.status, "waiting_for_confirmation");
  assert.equal(display.can_cancel, false);
  assert.equal(display.diagnostics[0].severity, "warning");
  assert.match(display.notification, /confirmation/);
});

test("tracks progress and invokes cancellation", () => {
  let cancelled = false;
  const view = new ValidationStatusView({ now: () => Date.parse("2026-08-29T00:00:10.000Z") });
  const running = view.start(action, () => { cancelled = true; });
  const stopped = view.cancel(action.action_id);

  assert.equal(running.status, "running");
  assert.equal(running.can_cancel, true);
  assert.equal(cancelled, true);
  assert.equal(stopped.status, "cancelled");
  assert.equal(stopped.can_cancel, false);
});

test("renders failed result diagnostics and elapsed time", () => {
  const view = new ValidationStatusView();
  view.start(action, () => {});
  const display = view.complete(result);

  assert.equal(display.status, "failed");
  assert.equal(display.elapsed_seconds, 5);
  assert.equal(display.diagnostics[0].location, "tests/test_demo.py");
  assert.equal(display.diagnostics[0].severity, "error");
  assert.match(display.notification, /failed/);
});

test("matches a result to its session, revision, and validation scope", () => {
  const view = new ValidationStatusView();
  view.start(action, () => {});
  view.showAction({
    ...action,
    action_id: "action-2",
    validation_scope: "local_e2e",
  }, true);

  const display = view.complete({
    ...result,
    validation_scope: "local_e2e",
    status: "passed",
    summary: { ...result.summary, diagnostics: [] },
  });

  assert.equal(display.action_id, "action-2");
  assert.equal(view.get("action-1").status, "running");
});
