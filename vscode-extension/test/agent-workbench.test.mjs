import assert from "node:assert/strict";
import test from "node:test";
import { AgentWorkbenchController, createAgentWorkbenchHtml } from "../dist/agent-workbench.js";

function createPanel() {
  let listener;
  return {
    webview: {
      html: "",
      onDidReceiveMessage(callback) {
        listener = callback;
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
    receive(message) { listener(message); },
  };
}

test("renders a CSP-protected approval workbench", () => {
  const html = createAgentWorkbenchHtml();
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /approval_request/);
  assert.match(html, /approval_decision/);
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
