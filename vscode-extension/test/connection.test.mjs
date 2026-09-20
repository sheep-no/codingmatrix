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

test("controls the negotiated agent host session", async () => {
  const calls = [];
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/handshake")) {
        return response({
          session_id: "session-1",
          workspace_id: "workspace-1",
          extension_version: "0.1.0",
          protocol_version: 1,
          capabilities: ["workspace"],
          policy_version: 1,
          policy: { local_execution_enabled: true, validation_operations: {}, auto_approve: false, require_confirmation_on_failure: true },
          pending_actions: [],
        });
      }
      return response({ status: "paused" });
    },
    retryDelayMs: 0,
  });
  await connection.handshake({ workspace_id: "workspace-1", extension_version: "0.1.0", protocol_versions: [1], capabilities: ["workspace"] });
  assert.deepEqual(await connection.controlSession("pause"), { status: "paused" });
  assert.equal(calls[1].url, "https://codingmatrix.example/api/v1/agent/host/sessions/session-1/control");
  assert.equal(JSON.parse(calls[1].init.body).action, "pause");
});

test("streams Agent events with bearer authentication", async () => {
  const calls = [];
  const chunks = [
    new TextEncoder().encode('data: {"type":"progress","data":{"message":"开始"}}\n\n'),
    new TextEncoder().encode('data: {"type":"done","data":{"success":true}}\n\n'),
  ];
  const connection = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      let index = 0;
      return {
        ...response({}, 200),
        body: { getReader: () => ({ read: async () => index < chunks.length ? { done: false, value: chunks[index++] } : { done: true } }) },
      };
    },
  });
  const events = [];

  await connection.streamAgentPrompt({ requirement: "检查项目" }, (event) => events.push(event));

  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/agent/orchestrate/stream");
  assert.equal(calls[0].init.headers.authorization, "Bearer access-token");
  assert.deepEqual(JSON.parse(calls[0].init.body), { requirement: "检查项目" });
  assert.deepEqual(events, [
    { type: "progress", data: { message: "开始" } },
    { type: "done", data: { success: true } },
  ]);
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

  const pending = await connection.submitResult(result);
  assert.deepEqual(pending, { status: "queued", event_id: "result-1" });
  assert.equal(connection.pendingResultCount, 1);

  online = true;
  assert.equal(await connection.flushPendingResults(), 1);
  assert.deepEqual(submitted, [result]);
});

test("flushes persisted results after a successful handshake", async () => {
  const storage = new MemoryResultStorage();
  const resultStore = new ResultStore(storage);
  let online = false;
  const first = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    maxRetries: 0,
    retryDelayMs: 0,
    resultStore,
    fetchImpl: async () => { throw new TypeError("offline"); },
  });
  assert.deepEqual(await first.submitResult(result), { status: "queued", event_id: "result-1" });

  online = true;
  const calls = [];
  const reconnected = new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    maxRetries: 0,
    retryDelayMs: 0,
    resultStore: new ResultStore(storage),
    fetchImpl: async (url, init) => {
      calls.push(url);
      if (url.endsWith("/handshake")) {
        return response({ session_id: "session-1", workspace_id: "workspace-1", extension_version: "0.1.0", protocol_version: 1, capabilities: ["workspace"], policy_version: 1, policy: { local_execution_enabled: true, validation_operations: {}, auto_approve: false, require_confirmation_on_failure: true }, pending_actions: [] });
      }
      return response({ accepted: true });
    },
  });
  await reconnected.handshake({ workspace_id: "workspace-1", extension_version: "0.1.0", protocol_versions: [1], capabilities: ["workspace"] });
  assert.deepEqual(calls, ["https://codingmatrix.example/api/v1/agent/host/handshake", "https://codingmatrix.example/api/v1/agent/local-validation/results"]);
  assert.deepEqual(await resultStore.listPending(), []);
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

  assert.deepEqual(await first.submitResult(result), { status: "queued", event_id: "result-1" });
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

function connected(fetchImpl) {
  return new CloudConnection({
    baseUrl: "https://codingmatrix.example",
    accessToken: "access-token",
    maxRetries: 0,
    retryDelayMs: 0,
    fetchImpl,
  });
}

test("normalizes the conversation list", async () => {
  const calls = [];
  const connection = connected(async (url, init) => {
    calls.push({ url, init });
    return response({
      items: [
        { conversation_id: 12, title: "重构登录", prompt: "帮我把登录拆开", created_at: "2026-09-20T00:00:00Z", message_count: 4 },
        { title: "缺少会话 ID" },
      ],
      total: 1,
    });
  });

  assert.deepEqual(await connection.listConversations({ limit: 10, offset: 5 }), [
    {
      conversation_id: 12,
      title: "重构登录",
      prompt: "帮我把登录拆开",
      created_at: "2026-09-20T00:00:00Z",
      message_count: 4,
    },
  ]);
  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/history");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { limit: 10, offset: 5 });
});

test("requires an items array from the conversation list", async () => {
  const connection = connected(async () => response({ total: 0 }));
  await assert.rejects(() => connection.listConversations(), { name: "ProtocolError" });
});

test("loads one conversation and forwards the paging cursor", async () => {
  const calls = [];
  const connection = connected(async (url, init) => {
    calls.push({ url, init });
    return response({
      conversation_id: 12,
      items: [
        { id: 9, conversation_id: 12, prompt: "你好", response: "在的", thinking: "内部推理", title: "寒暄" },
      ],
    });
  });

  assert.deepEqual(await connection.fetchConversationHistory(12, { lastHistoryId: 30, limit: 20 }), [
    { id: 9, conversation_id: 12, prompt: "你好", response: "在的", thinking: "内部推理", title: "寒暄", created_at: null },
  ]);
  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/conversation/history");
  assert.deepEqual(JSON.parse(calls[0].init.body), { conversation_id: 12, limit: 20, last_history_id: 30 });
});

test("rejects a non-positive conversation id", async () => {
  const connection = connected(async () => response({ items: [] }));
  await assert.rejects(() => connection.fetchConversationHistory(0), /conversation id must be a positive integer/);
  await assert.rejects(() => connection.deleteConversation(0), /conversation id must be a positive integer/);
});

test("deletes a conversation and reports the deleted count", async () => {
  const calls = [];
  const connection = connected(async (url, init) => {
    calls.push({ url, init });
    return response({ status: "deleted", count: 3 });
  });

  assert.equal(await connection.deleteConversation(12), 3);
  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/code/history?all=false&conversation_ids=12");
  assert.equal(calls[0].init.method, "DELETE");
});

test("normalizes the agent model config and token usage", async () => {
  const calls = [];
  const connection = connected(async (url) => {
    calls.push(url);
    if (url.endsWith("/api/v1/models/agent-config")) {
      return response({ version: 4, roles: { coder: { model: "claude" } }, models: ["claude"], fallback_chain: ["gpt"] });
    }
    return response({
      total_tokens: 1200,
      prompt_tokens: 700,
      completion_tokens: 500,
      total_messages: 8,
      today_tokens: "300",
      this_month_tokens: 900,
      by_model: { claude: { tokens: 1200 } },
    });
  });

  assert.deepEqual(await connection.fetchAgentModelConfig(), {
    version: 4,
    roles: { coder: { model: "claude" } },
    models: ["claude"],
    fallback_chain: ["gpt"],
  });
  assert.deepEqual(await connection.fetchTokenUsage(), {
    total_tokens: 1200,
    prompt_tokens: 700,
    completion_tokens: 500,
    total_messages: 8,
    today_tokens: 300,
    this_month_tokens: 900,
    by_model: { claude: { tokens: 1200 } },
  });
  assert.deepEqual(calls, [
    "https://codingmatrix.example/api/v1/models/agent-config",
    "https://codingmatrix.example/api/v1/agent/token-usage",
  ]);
});

test("lists snapshots, rolls back and diffs against the encoded session id", async () => {
  const calls = [];
  const connection = connected(async (url, init) => {
    calls.push({ url, init });
    if (url.includes("/snapshots/")) {
      return response({ session_id: "s/1", snapshots: [{ tag: "v2", commit: "abc", message: "第二版" }, { commit: "缺少 tag" }] });
    }
    if (url.includes("/rollback/")) {
      return response({ success: true, previous_tag: "v2", current_tag: "v1", files_restored: 3 });
    }
    return response({ session_id: "s/1", from: "v1", to: "v2", diff: "--- a\n+++ b" });
  });

  assert.deepEqual(await connection.listSnapshots("s/1"), [
    { tag: "v2", commit: "abc", message: "第二版", timestamp: null },
  ]);
  assert.deepEqual(await connection.rollbackToSnapshot("s/1", "v1"), {
    previousTag: "v2",
    currentTag: "v1",
    filesRestored: 3,
  });
  assert.equal(await connection.fetchSnapshotDiff("s/1", "v1", "v2"), "--- a\n+++ b");
  assert.equal(calls[0].url, "https://codingmatrix.example/api/v1/agent/snapshots/s%2F1");
  assert.equal(calls[1].url, "https://codingmatrix.example/api/v1/agent/rollback/s%2F1?target_tag=v1");
  assert.equal(calls[1].init.method, "POST");
  assert.equal(
    calls[2].url,
    "https://codingmatrix.example/api/v1/agent/snapshot/diff?session_id=s%2F1&from_tag=v1&to_tag=v2",
  );
});

test("combines the performance metrics and trends endpoints", async () => {
  const calls = [];
  const connection = connected(async (url) => {
    calls.push(url);
    if (url.endsWith("/trends")) return response({ success: true, trends: { planner: { avg_time_ms: 12 } } });
    return response({ success: true, metrics: { total_requests: 5 }, thresholds: { slow_ms: 1000 } });
  });

  assert.deepEqual(await connection.fetchPerformance(), {
    metrics: { total_requests: 5 },
    thresholds: { slow_ms: 1000 },
    trends: { planner: { avg_time_ms: 12 } },
  });
  assert.deepEqual(calls.sort(), [
    "https://codingmatrix.example/api/v1/agent/performance",
    "https://codingmatrix.example/api/v1/agent/performance/trends",
  ]);
});
