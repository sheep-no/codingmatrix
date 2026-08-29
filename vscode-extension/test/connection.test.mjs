import assert from "node:assert/strict";
import test from "node:test";
import {
  CloudConnection,
  CloudConnectionError,
} from "../dist/connection.js";
import { MemoryResultStorage, ResultStore } from "../dist/result-store.js";

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

test("performs authenticated agent host handshake", async () => {
  const calls = [];
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return response({
        session_id: "session-1",
        workspace_id: "workspace-1",
        extension_version: "0.1.0",
        protocol_version: 1,
        capabilities: ["workspace", "validation"],
        policy_version: 1,
        policy: {
          local_execution_enabled: true,
          validation_operations: {},
          auto_approve: false,
          require_confirmation_on_failure: true,
        },
        pending_actions: [],
      });
    },
    retryDelayMs: 0,
  });

  const handshake = await connection.handshake({
    workspace_id: "workspace-1",
    extension_version: "0.1.0",
    protocol_versions: [1],
    capabilities: ["workspace", "validation"],
  });

  assert.equal(handshake.session_id, "session-1");
  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/agent/host/handshake");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    workspace_id: "workspace-1",
    extension_version: "0.1.0",
    protocol_versions: [1],
    capabilities: ["workspace", "validation"],
  });
});

test("uses the negotiated session for agent host actions and events", async () => {
  const calls = [];
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/handshake")) {
        return response({
          session_id: "session-2",
          workspace_id: "workspace-1",
          extension_version: "0.1.0",
          protocol_version: 1,
          capabilities: ["workspace"],
          policy_version: 1,
          policy: {
            local_execution_enabled: true,
            validation_operations: {},
            auto_approve: false,
            require_confirmation_on_failure: true,
          },
          pending_actions: [],
        });
      }
      if (url.endsWith("/actions")) {
        return response({ actions: [{
          message_id: "action-1",
          schema_version: 1,
          session_id: "session-2",
          kind: "progress_event",
          payload: { message: "run" },
        }] });
      }
      return response({ accepted: true });
    },
    retryDelayMs: 0,
  });

  await connection.handshake({
    workspace_id: "workspace-1",
    extension_version: "0.1.0",
    protocol_versions: [1],
    capabilities: ["workspace"],
  });
  const actions = await connection.fetchAgentHostActions();
  await connection.submitEvent(actions[0]);

  assert.equal(actions[0].session_id, "session-2");
  assert.equal(calls[1].url, "https://codingmatrix.example/api/v1/agent/host/sessions/session-2/actions");
  assert.equal(calls[2].url, "https://codingmatrix.example/api/v1/agent/host/sessions/session-2/events");
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

test("restores persisted results after a connection instance restarts", async () => {
  const storage = new MemoryResultStorage();
  const resultStore = new ResultStore(storage);
  let online = false;
  const first = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    maxRetries: 0,
    retryDelayMs: 0,
    resultStore,
    fetchImpl: async (_url, init) => {
      if (!online) throw new TypeError("offline");
      return response({ accepted: JSON.parse(init.body).event_id });
    },
  });

  void first.submitResult(result);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal((await resultStore.listPending()).length, 1);

  online = true;
  const restarted = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    maxRetries: 0,
    retryDelayMs: 0,
    resultStore: new ResultStore(storage),
    fetchImpl: async (_url, init) => response({ accepted: JSON.parse(init.body).event_id }),
  });

  assert.equal(await restarted.flushPendingResults(), 1);
  assert.deepEqual(await resultStore.listPending(), []);
});
