import assert from "node:assert/strict";
import test from "node:test";
import { AgentWorkbenchController, createAgentWorkbenchHtml } from "../dist/agent-workbench.js";

function createPanel() {
  const listeners = [];
  const posted = [];
  return {
    webview: {
      html: "",
      onDidReceiveMessage(callback) {
        listeners.push(callback);
        return { dispose() {} };
      },
      async postMessage(message) {
        this.lastMessage = message;
        posted.push(message);
        return true;
      },
      lastMessage: undefined,
      posted,
    },
    onDidDispose() { return { dispose() {} }; },
    reveal() { this.revealed = true; },
    dispose() {},
    receive(message) { for (const listener of listeners) listener(message); },
  };
}

test("renders a CSP-protected approval workbench", () => {
  const html = createAgentWorkbenchHtml();
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /workbench_prompt/);
  assert.match(html, /messages/);
  assert.match(html, /approval_request/);
  assert.match(html, /approval_decision/);
});

test("renders the history, model, version, performance, learning and settings panels", () => {
  const html = createAgentWorkbenchHtml();
  assert.match(html, /workbench_request/);
  assert.match(html, /workbench_response/);
  assert.match(html, /id="tab-history"/);
  assert.match(html, /id="tab-models"/);
  assert.match(html, /id="tab-versions"/);
  assert.match(html, /id="tab-performance"/);
  assert.match(html, /id="tab-learning"/);
  assert.match(html, /id="tab-settings"/);
  assert.match(html, /history_list/);
  assert.match(html, /snapshot_rollback/);
  assert.match(html, /performance/);
  assert.match(html, /learning/);
  assert.match(html, /cache_clear/);
  assert.match(html, /concurrent_limits/);
  assert.match(html, /id="project-name"/);
  assert.match(html, /id="incremental"/);
  assert.match(html, /data-flag="enable_skills"/);
  assert.match(html, /data-flag="dependency_graph"/);
  assert.match(html, /id="decisions"/);
  assert.match(html, /critical_decisions/);
  assert.match(html, /decision_submit/);
});

test("routes a workbench request and posts the response", async () => {
  const requests = [];
  const controller = new AgentWorkbenchController({
    onRequest: (request) => {
      requests.push(request);
      return { items: [] };
    },
  });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({
    type: "workbench_request",
    request_id: "req-1",
    resource: "history_list",
    params: { limit: 20, offset: 0 },
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(requests.length, 1);
  assert.equal(requests[0].resource, "history_list");
  assert.deepEqual(requests[0].params, { limit: 20, offset: 0 });
  assert.deepEqual(panel.webview.posted, [
    { type: "workbench_response", request_id: "req-1", ok: true, data: { items: [] } },
  ]);
});

test("defaults missing request params to an empty object", async () => {
  const requests = [];
  const controller = new AgentWorkbenchController({ onRequest: (request) => requests.push(request) });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_request", request_id: "req-1", resource: "performance" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(requests[0].params, {});
});

test("reports a failed workbench request instead of throwing", async () => {
  const controller = new AgentWorkbenchController({
    onRequest: () => {
      throw new Error("云端 Agent 尚未连接");
    },
  });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_request", request_id: "req-2", resource: "token_usage" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(panel.webview.posted, [
    { type: "workbench_response", request_id: "req-2", ok: false, error: "云端 Agent 尚未连接" },
  ]);
});

test("rejects an unknown resource or a malformed request", async () => {
  let calls = 0;
  const controller = new AgentWorkbenchController({ onRequest: () => { calls += 1; } });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_request", request_id: "req-3", resource: "delete_everything" });
  panel.receive({ type: "workbench_request", resource: "performance" });
  panel.receive({ type: "workbench_request", request_id: "req-4", resource: "performance", params: [] });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 0);
  assert.deepEqual(panel.webview.posted, []);
});

test("reports the missing data channel when no handler is registered", async () => {
  const controller = new AgentWorkbenchController();
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_request", request_id: "req-5", resource: "model_config" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(panel.webview.posted, [
    { type: "workbench_response", request_id: "req-5", ok: false, error: "工作台数据通道尚未连接" },
  ]);
});

test("forwards workbench prompts to the cloud handler", async () => {
  const prompts = [];
  const controller = new AgentWorkbenchController({ onPrompt: (prompt) => prompts.push(prompt) });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_prompt", prompt: "  分析当前项目  " });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(prompts, ["分析当前项目"]);
});

test("forwards the prompt options with the generation flags", async () => {
  const received = [];
  const controller = new AgentWorkbenchController({
    onPrompt: (prompt, options) => received.push({ prompt, options }),
  });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({
    type: "workbench_prompt",
    prompt: "  增加登录页  ",
    project_name: "  my-app  ",
    incremental: true,
    flags: { enable_review: false, spec_first: false },
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(received, [{
    prompt: "增加登录页",
    options: {
      projectName: "my-app",
      incremental: true,
      flags: {
        enable_review: false,
        enable_validation: true,
        enable_error_recovery: true,
        enable_memory: true,
        enable_skills: true,
        spec_first: false,
        dependency_graph: true,
      },
    },
  }]);
});

test("ignores non-boolean flags and an empty project name", async () => {
  const received = [];
  const controller = new AgentWorkbenchController({
    onPrompt: (prompt, options) => received.push(options),
  });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({
    type: "workbench_prompt",
    prompt: "全新生成",
    project_name: "   ",
    incremental: "yes",
    flags: { enable_review: "false", spec_first: 0 },
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(received.length, 1);
  assert.equal(received[0].projectName, undefined);
  assert.equal(received[0].incremental, false);
  assert.equal(received[0].flags.enable_review, true);
  assert.equal(received[0].flags.spec_first, true);
});

test("forwards validated webview host messages to the controller", async () => {
  const messages = [];
  const controller = new AgentWorkbenchController({ onMessage: (message) => messages.push(message) });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({
    type: "agent_host_message",
    message: {
      message_id: "decision-1",
      schema_version: 1,
      session_id: "session-1",
      kind: "approval_decision",
      payload: { request_id: "approval-1", approved: true },
    },
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(messages[0].kind, "approval_decision");
  assert.equal(messages[0].payload.approved, true);
});

test("forwards workbench session controls", async () => {
  const controls = [];
  const controller = new AgentWorkbenchController({ onControl: (action) => controls.push(action) });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_control", action: "pause" });
  panel.receive({ type: "workbench_control", action: "resume" });
  panel.receive({ type: "workbench_control", action: "cancel" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(controls, ["pause", "resume", "cancel"]);
});

test("routes the workbench connect button to the ready handler", async () => {
  let ready = 0;
  const controller = new AgentWorkbenchController({ onReady: () => { ready += 1; } });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_ready" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(ready, 1);
});
