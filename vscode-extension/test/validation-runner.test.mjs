import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import {
  ValidationRunner,
  ValidationRunnerError,
} from "../dist/validation-runner.js";

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
  timeout_seconds: 1,
  requested_by: "cloud",
};

function fakeProcess({ code = 0, stdout = "", stderr = "", close = true } = {}) {
  const process = new EventEmitter();
  process.stdout = new EventEmitter();
  process.stderr = new EventEmitter();
  process.killed = [];
  process.kill = (signal) => {
    process.killed.push(signal);
    if (!close) {
      process.emit("close", null);
    }
    return true;
  };
  setImmediate(() => {
    if (stdout) process.stdout.emit("data", stdout);
    if (stderr) process.stderr.emit("data", stderr);
    if (close) process.emit("close", code);
  });
  return process;
}

test("runs command with arguments and shell disabled", async () => {
  let invocation;
  const runner = new ValidationRunner({
    spawn: (command, args, options) => {
      invocation = { command, args, options };
      return fakeProcess({ stdout: "42 passed" });
    },
    now: (() => {
      const values = ["start", "finish"];
      return () => values.shift();
    })(),
    createEventId: () => "result-1",
  });

  const result = await runner.run(action);
  assert.deepEqual(invocation, {
    command: "python3",
    args: ["-m", "pytest"],
    options: { cwd: "/projects/demo", shell: false },
  });
  assert.equal(result.status, "passed");
  assert.equal(result.exit_code, 0);
  assert.equal(result.event_id, "result-1");
  assert.match(result.summary.diagnostics[0].output, /42 passed/);
});

test("maps non-zero process exits to failed", async () => {
  const runner = new ValidationRunner({
    spawn: () => fakeProcess({ code: 3, stderr: "test failed" }),
    retryDelayMs: 0,
  });

  const result = await runner.run(action);
  assert.equal(result.status, "failed");
  assert.equal(result.exit_code, 3);
});

test("times out and terminates the process", async () => {
  let process;
  const runner = new ValidationRunner({
    spawn: () => {
      process = fakeProcess({ close: false });
      return process;
    },
    now: () => "timestamp",
  });

  const result = await runner.run({ ...action, timeout_seconds: 1 });
  assert.equal(result.status, "timeout");
  assert.deepEqual(process.killed, ["SIGTERM"]);
});

test("cancels before the process starts", async () => {
  let spawned = false;
  const runner = new ValidationRunner({
    spawn: () => {
      spawned = true;
      return fakeProcess();
    },
  });
  const signal = { aborted: true, addEventListener() {} };

  const result = await runner.run(action, { signal });
  assert.equal(result.status, "cancelled");
  assert.equal(spawned, false);
});

test("cancels a running process", async () => {
  let process;
  const listeners = [];
  const runner = new ValidationRunner({
    spawn: () => {
      process = fakeProcess({ close: false });
      return process;
    },
  });
  const signal = {
    aborted: false,
    addEventListener(_event, listener) {
      listeners.push(listener);
    },
    removeEventListener() {},
  };
  const pending = runner.run(action, { signal });
  await new Promise((resolve) => setImmediate(resolve));
  listeners[0]();

  const result = await pending;
  assert.equal(result.status, "cancelled");
  assert.deepEqual(process.killed, ["SIGTERM"]);
});

test("caps captured output", async () => {
  const runner = new ValidationRunner({
    spawn: () => fakeProcess({ stdout: "1234567890" }),
    outputLimitBytes: 5,
  });

  const result = await runner.run(action);
  assert.equal(result.summary.diagnostics[0].truncated, true);
  assert.match(result.summary.diagnostics[0].output, /12345/);
});

test("rejects an invalid operation before spawning", () => {
  const runner = new ValidationRunner({ spawn: () => fakeProcess() });
  assert.throws(
    () => runner.run({ ...action, operation: "shell" }),
    (error) => error instanceof ValidationRunnerError && error.code === "invalid_action",
  );
});
