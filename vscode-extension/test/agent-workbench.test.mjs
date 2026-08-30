import assert from "node:assert/strict";
import test from "node:test";
import { AgentWorkbenchController, createAgentWorkbenchHtml } from "../dist/agent-workbench.js";

function createPanel() {
  const listeners = [];
  return {
    webview: {
      html: "",
      onDidReceiveMessage(callback) {
        listeners.push(callback);
        return { dispose() {} };
      },
      async postMessage(message) {
        this.lastMessage = message;
        return true;
      },
      lastMessage: undefined,
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

test("forwards workbench prompts to the cloud handler", async () => {
  const prompts = [];
  const controller = new AgentWorkbenchController({ onPrompt: (prompt) => prompts.push(prompt) });
  const panel = createPanel();
  controller.open(() => panel);
  panel.receive({ type: "workbench_prompt", prompt: "  分析当前项目  " });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(prompts, ["分析当前项目"]);
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
