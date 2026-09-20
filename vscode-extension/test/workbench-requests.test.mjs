import assert from "node:assert/strict";
import test from "node:test";
import { dispatchWorkbenchRequest } from "../dist/workbench-requests.js";

function stubConnection(handlers) {
  const calls = [];
  const record = (name) => (...args) => {
    calls.push({ name, args });
    return handlers[name]?.(...args);
  };
  return {
    calls,
    listConversations: record("listConversations"),
    fetchConversationHistory: record("fetchConversationHistory"),
    deleteConversation: record("deleteConversation"),
    fetchAgentModelConfig: record("fetchAgentModelConfig"),
    fetchTokenUsage: record("fetchTokenUsage"),
    listSnapshots: record("listSnapshots"),
    rollbackToSnapshot: record("rollbackToSnapshot"),
    fetchSnapshotDiff: record("fetchSnapshotDiff"),
    fetchPerformance: record("fetchPerformance"),
  };
}

function request(resource, params = {}) {
  return { request_id: "req-1", resource, params };
}

test("dispatches every supported resource to the matching connection method", async () => {
  const connection = stubConnection({
    listConversations: (options) => ["list", options],
    fetchConversationHistory: (id, options) => ["messages", id, options],
    deleteConversation: (id) => ["delete", id],
    fetchAgentModelConfig: () => ["model"],
    fetchTokenUsage: () => ["usage"],
    listSnapshots: (sessionId) => ["snapshots", sessionId],
    rollbackToSnapshot: (sessionId, tag) => ["rollback", sessionId, tag],
    fetchSnapshotDiff: (sessionId, from, to) => ["diff", sessionId, from, to],
    fetchPerformance: () => ["performance"],
  });

  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("history_list", { limit: 10, offset: 20 })), ["list", { limit: 10, offset: 20 }]);
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("history_messages", { conversation_id: 7 })), ["messages", 7, { limit: 50 }]);
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("history_delete", { conversation_id: 7 })), ["delete", 7]);
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("model_config")), ["model"]);
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("token_usage")), ["usage"]);
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("snapshot_list", { session_id: "s-1" })), ["snapshots", "s-1"]);
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("snapshot_rollback", { session_id: "s-1", target_tag: "v1" })), ["rollback", "s-1", "v1"]);
  assert.deepEqual(
    await dispatchWorkbenchRequest(connection, request("snapshot_diff", { session_id: "s-1", from_tag: "v1", to_tag: "v2" })),
    ["diff", "s-1", "v1", "v2"],
  );
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("performance")), ["performance"]);
});

test("omits paging options the webview did not send", async () => {
  const connection = stubConnection({ listConversations: (options) => options });
  assert.deepEqual(await dispatchWorkbenchRequest(connection, request("history_list")), {});
});

test("rejects invalid or missing parameters before reaching the connection", async () => {
  const connection = stubConnection({});
  await assert.rejects(() => dispatchWorkbenchRequest(connection, request("history_messages", {})), /缺少参数：conversation_id/);
  await assert.rejects(() => dispatchWorkbenchRequest(connection, request("history_messages", { conversation_id: 0 })), /conversation_id 必须为正整数/);
  await assert.rejects(() => dispatchWorkbenchRequest(connection, request("history_list", { limit: 0 })), /参数 limit 无效/);
  await assert.rejects(() => dispatchWorkbenchRequest(connection, request("snapshot_list", { session_id: "   " })), /缺少参数：session_id/);
  await assert.rejects(() => dispatchWorkbenchRequest(connection, request("snapshot_rollback", { session_id: "s-1" })), /缺少参数：target_tag/);
  assert.deepEqual(connection.calls, []);
});
