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

test("applies newer policy updates to the session and dispatcher", async () => {
  const session = createSession();
  const policies = [];
  const dispatcher = { ...createDispatcher(), setPolicy: (value) => policies.push(value) };
  const runtime = new AgentHostRuntime({ session, dispatcher });
  const nextPolicy = { ...policy, auto_approve: false };
  const result = await runtime.process({
    message_id: "policy-1",
    schema_version: 1,
    session_id: "session-1",
    kind: "policy_update",
    policy_version: 3,
    payload: { policy: nextPolicy },
  });
  assert.equal(result.auto_approve, false);
  assert.equal(session.snapshot().policy_version, 3);
  assert.equal(policies.length, 1);
  await assert.rejects(runtime.process({
    message_id: "policy-old",
    schema_version: 1,
    session_id: "session-1",
    kind: "policy_update",
    policy_version: 2,
    payload: { policy: nextPolicy },
  }));
});

test("polls cloud validation actions and submits local results", async () => {
  const submitted = [];
  const action = {
    action_id: "action-poll",
    event_id: "event-poll",
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
  };
  const result = {
    event_id: "result-poll",
    schema_version: 1,
    session_id: "session-1",
    task_id: "task-1",
    revision: 0,
    source: "local",
    validation_scope: "local_runtime",
    status: "passed",
    started_at: "2026-08-29T00:00:00Z",
    finished_at: "2026-08-29T00:00:01Z",
    summary: { command_name: "node", diagnostics: [] },
  };
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: { dispatch: async () => result },
    connection: {
      fetchPendingActions: async () => [action],
      submitResult: async (value) => { submitted.push(value); },
    },
  });
  assert.equal(await runtime.poll(), 1);
  assert.deepEqual(submitted, [result]);
});

test("deduplicates concurrent tool actions by session and message id", async () => {
  let dispatches = 0;
  let finish;
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: {
      dispatch: async () => {
        dispatches += 1;
        return new Promise((resolve) => { finish = resolve; });
      },
    },
  });
  const action = {
    message_id: "deduplicated-action",
    schema_version: 1,
    session_id: "session-1",
    kind: "tool_action",
    capability: "workspace",
    policy_version: 2,
    payload: { operation: "inspect" },
  };
  const first = runtime.process(action);
  const second = runtime.process(action);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(dispatches, 1);
  finish({ value: "done" });
  assert.deepEqual(await Promise.all([first, second]), [{ value: "done" }, { value: "done" }]);
});

test("retries a tool action after a failed execution", async () => {
  let dispatches = 0;
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: {
      dispatch: async () => {
        dispatches += 1;
        if (dispatches === 1) throw new Error("temporary failure");
        return { value: "recovered" };
      },
    },
  });
  const action = {
    message_id: "retry-action",
    schema_version: 1,
    session_id: "session-1",
    kind: "tool_action",
    capability: "workspace",
    policy_version: 2,
    payload: { operation: "inspect" },
  };
  await assert.rejects(runtime.process(action), /temporary failure/);
  assert.deepEqual(await runtime.process(action), { value: "recovered" });
  assert.equal(dispatches, 2);
});

test("keeps active actions deduplicated while trimming completed action history", async () => {
  let activeDispatches = 0;
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: {
      dispatch: async (action, options) => {
        if (action.message_id === "active-action") {
          activeDispatches += 1;
          return new Promise((resolve) => {
            options.signal.addEventListener("abort", () => resolve({ status: "cancelled" }), { once: true });
          });
        }
        return { value: action.message_id };
      },
    },
  });
  const activeAction = {
    message_id: "active-action",
    schema_version: 1,
    session_id: "session-1",
    kind: "tool_action",
    capability: "workspace",
    policy_version: 2,
    payload: { operation: "inspect" },
  };
  const active = runtime.process(activeAction);
  await new Promise((resolve) => setImmediate(resolve));
  for (let index = 0; index < 1001; index += 1) {
    await runtime.process({ ...activeAction, message_id: `completed-${index}` });
  }
  const duplicate = runtime.process(activeAction);
  assert.equal(activeDispatches, 1);
  runtime.cancelActiveActions();
  assert.deepEqual(await Promise.all([active, duplicate]), [{ status: "cancelled" }, { status: "cancelled" }]);
});

test("cancels an active local action when the session is cancelled", async () => {
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: {
      dispatch: async (_action, options) => new Promise((resolve) => {
        options.signal.addEventListener("abort", () => resolve({
          event_id: "cancelled-result",
          schema_version: 1,
          session_id: "session-1",
          task_id: "task-1",
          revision: 0,
          source: "local",
          validation_scope: "local_runtime",
          status: "cancelled",
          started_at: "2026-08-29T00:00:00Z",
          finished_at: "2026-08-29T00:00:01Z",
          summary: { command_name: "node", diagnostics: [] },
        }), { once: true });
      }),
    },
  });
  const running = runtime.process({
    message_id: "running-action",
    schema_version: 1,
    session_id: "session-1",
    task_id: "task-1",
    revision: 0,
    kind: "tool_action",
    capability: "validation",
    policy_version: 2,
    payload: {},
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(await runtime.process({
    message_id: "cancel-session",
    schema_version: 1,
    session_id: "session-1",
    kind: "session_control",
    payload: { action: "cancel" },
  }), "cancelled");
  assert.equal((await running).status, "cancelled");
});

test("coalesces overlapping polls", async () => {
  let fetches = 0;
  let finish;
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: createDispatcher(),
    connection: {
      fetchPendingActions: async () => {
        fetches += 1;
        return new Promise((resolve) => { finish = resolve; });
      },
      submitResult: async () => undefined,
    },
  });
  const first = runtime.poll();
  const second = runtime.poll();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fetches, 1);
  finish([]);
  assert.deepEqual(await Promise.all([first, second]), [0, 0]);
});

test("isolates an in-flight poll when the connection changes", async () => {
  let finishOldPoll;
  let oldDispatches = 0;
  let newFetches = 0;
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: { dispatch: async () => { oldDispatches += 1; return {}; } },
    connection: {
      fetchAgentHostActions: async () => new Promise((resolve) => { finishOldPoll = resolve; }),
      fetchPendingActions: async () => [],
      submitResult: async () => undefined,
    },
  });
  const oldPoll = runtime.poll();
  await new Promise((resolve) => setImmediate(resolve));
  runtime.setConnection({
    fetchAgentHostActions: async () => { newFetches += 1; return []; },
    fetchPendingActions: async () => [],
    submitResult: async () => undefined,
  });
  assert.equal(await runtime.poll(), 0);
  finishOldPoll([{
    message_id: "stale-action",
    schema_version: 1,
    session_id: "session-1",
    kind: "tool_action",
    capability: "workspace",
    policy_version: 2,
    payload: { operation: "inspect" },
  }]);
  assert.equal(await oldPoll, 0);
  assert.equal(newFetches, 1);
  assert.equal(oldDispatches, 0);
});

test("limits skill_runtime to metadata synchronization", async () => {
  const synced = [];
  const runtime = new AgentHostRuntime({
    session: createSession(),
    dispatcher: createDispatcher(),
    onSkillSync: async (skills) => synced.push(skills),
  });
  await runtime.process({
    message_id: "skill-sync",
    schema_version: 1,
    session_id: "session-1",
    kind: "tool_action",
    capability: "skill_runtime",
    payload: { operation: "sync", skills: { lint: { description: "Lint" } } },
  });
  assert.deepEqual(synced, [{ lint: { description: "Lint" } }]);
  await assert.rejects(runtime.process({
    message_id: "skill-execute",
    schema_version: 1,
    session_id: "session-1",
    kind: "tool_action",
    capability: "skill_runtime",
    payload: { operation: "execute", skill_name: "lint" },
  }), /skill sync requires a skills object/);
});
