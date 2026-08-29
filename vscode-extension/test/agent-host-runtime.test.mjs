import assert from "node:assert/strict";
import test from "node:test";
import { AgentHostRuntime, AgentHostRuntimeError } from "../dist/agent-host-runtime.js";
import { AgentHostSession } from "../dist/agent-host.js";
import { ApprovalBridge } from "../dist/approval-bridge.js";

const policy = {
  local_execution_enabled: true,
  validation_operations: { unit_test: true },
  auto_approve: true,
  require_confirmation_on_failure: false,
};

function createSession() {
  const session = new AgentHostSession();
  session.acceptHandshake({
    session_id: "session-1",
    workspace_id: "workspace-1",
    extension_version: "0.1.0",
    protocol_version: 1,
    capabilities: ["workspace", "validation"],
    policy_version: 2,
    policy,
    pending_actions: [],
  });
  return session;
}

function createDispatcher() {
  return {
    dispatch: async () => ({ value: "done" }),
  };
}

test("emits tool results with session and policy context", async () => {
  const events = [];
  const runtime = new AgentHostRuntime({ session: createSession(), dispatcher: createDispatcher(), onEvent: async (event) => events.push(event) });
  const result = await runtime.process({
    message_id: "message-1",
    schema_version: 1,
    session_id: "session-1",
    task_id: "task-1",
    revision: 4,
    kind: "tool_action",
    capability: "workspace",
    policy_version: 2,
    payload: { operation: "inspect" },
  });
  assert.deepEqual(result, { value: "done" });
  assert.equal(events[0].kind, "tool_result");
  assert.equal(events[0].policy_version, 2);
});

test("rejects actions from another session or stale policy", async () => {
  const runtime = new AgentHostRuntime({ session: createSession(), dispatcher: createDispatcher() });
  await assert.rejects(runtime.process({ message_id: "m", schema_version: 1, session_id: "other", kind: "tool_action", payload: {} }), (error) => error instanceof AgentHostRuntimeError && error.code === "session_mismatch");
  await assert.rejects(runtime.process({ message_id: "m", schema_version: 1, session_id: "session-1", kind: "tool_action", policy_version: 1, payload: {} }), (error) => error instanceof AgentHostRuntimeError && error.code === "policy_mismatch");
});

test("waits for and honors a local approval decision", async () => {
  const session = createSession();
  session.applyPolicyUpdate({ policy_version: 3, policy: { ...policy, auto_approve: false } });
  const requests = [];
  const approval = new ApprovalBridge({ onRequest: async (request) => requests.push(request) });
  const runtime = new AgentHostRuntime({ session, dispatcher: createDispatcher(), approvalBridge: approval });
  const action = { message_id: "message-approval", schema_version: 1, session_id: "session-1", kind: "tool_action", capability: "terminal", policy_version: 3, payload: {} };
  const pending = runtime.process(action);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requests[0].kind, "approval_request");
  assert.equal(approval.decide(requests[0].message_id, true), true);
  assert.deepEqual(await pending, { value: "done" });
});
