import assert from "node:assert/strict";
import test from "node:test";
import {
  CloudConnection,
  CloudConnectionError,
} from "../dist/connection.js";

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

const result = {
  event_id: "result-1",
  schema_version: 1,
  session_id: "session-1",
  task_id: "task-1",
  revision: 2,
  source: "local",
  validation_scope: "local_runtime",
  status: "passed",
  started_at: "2026-08-29T00:00:00Z",
  finished_at: "2026-08-29T00:01:00Z",
  exit_code: 0,
  summary: { command_name: "pytest", diagnostics: [] },
};

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    },
  };
}

test("fetches actions with bearer authentication", async () => {
  const calls = [];
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example/",
    accessToken: "access-token",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return response({ actions: [action] });
    },
    retryDelayMs: 0,
  });

  assert.deepEqual(await connection.fetchPendingActions(), [action]);
  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/agent/local-validation/actions");
  assert.equal(calls[0].init.headers.authorization, "Bearer access-token");
});

test("classifies authentication failures without retrying", async () => {
  let attempts = 0;
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "expired-token",
    fetchImpl: async () => {
      attempts += 1;
      return response({ detail: "expired" }, 401);
    },
    retryDelayMs: 0,
  });

  await assert.rejects(
    connection.fetchPendingActions(),
    (error) => error instanceof CloudConnectionError && error.code === "authentication_failed",
  );
  assert.equal(attempts, 1);
});

test("retries transient failures", async () => {
  let attempts = 0;
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    fetchImpl: async () => {
      attempts += 1;
      return attempts === 1 ? response({}, 503) : response({ actions: [action] });
    },
    retryDelayMs: 0,
  });

  assert.deepEqual(await connection.fetchPendingActions(), [action]);
  assert.equal(attempts, 2);
});

test("queues result during network outage and flushes after reconnect", async () => {
  let online = false;
  const submitted = [];
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    maxRetries: 0,
    retryDelayMs: 0,
    fetchImpl: async (_url, init) => {
      if (!online) throw new TypeError("offline");
      submitted.push(JSON.parse(init.body));
      return response({ accepted: true });
    },
  });

  const pending = connection.submitResult(result);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(connection.pendingResultCount, 1);

  online = true;
  assert.equal(await connection.flushPendingResults(), 1);
  assert.deepEqual(await pending, { accepted: true });
  assert.deepEqual(submitted, [result]);
});
