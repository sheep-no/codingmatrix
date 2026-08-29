import assert from "node:assert/strict";
import test from "node:test";
import { WebviewBridge, WebviewBridgeError } from "../dist/webview-bridge.js";

function createTransport() {
  let listener;
  const sent = [];
  return {
    sent,
    postMessage(message) {
      sent.push(message);
    },
    onMessage(callback) {
      listener = callback;
    },
    receive(message) {
      listener(message);
    },
  };
}

const message = (id = "message-1") => ({
  message_id: id,
  schema_version: 1,
  session_id: "session-1",
  kind: "progress_event",
  capability: "workspace",
  payload: { progress: 50 },
});

test("sends validated messages and publishes host events", async () => {
  const transport = createTransport();
  const bridge = new WebviewBridge(transport);
  const received = [];
  bridge.subscribe((event) => received.push(event));

  await bridge.send(message());
  transport.receive({ type: "agent_host_message", message: message("event-1") });

  assert.equal(transport.sent[0].type, "agent_host_message");
  assert.equal(received[0].message_id, "event-1");
});

test("correlates request responses and propagates response errors", async () => {
  const transport = createTransport();
  const bridge = new WebviewBridge(transport);
  const pending = bridge.request(message("request-1"));
  transport.receive({ type: "agent_host_response", request_id: "request-1", message: message("response-1") });
  assert.equal((await pending).message_id, "response-1");

  const failed = bridge.request(message("request-2"));
  transport.receive({ type: "agent_host_response", request_id: "request-2", error: "approval denied" });
  await assert.rejects(failed, (error) => error instanceof WebviewBridgeError && error.code === "request_failed");
});

test("times out and rejects requests after disposal", async () => {
  const timeoutTransport = createTransport();
  const timeoutBridge = new WebviewBridge(timeoutTransport);
  await assert.rejects(timeoutBridge.request(message("request-timeout"), 1), (error) => error.code === "request_timeout");

  const disposedTransport = createTransport();
  const disposedBridge = new WebviewBridge(disposedTransport);
  const pending = disposedBridge.request(message("request-disposed"));
  disposedBridge.dispose();
  await assert.rejects(pending, (error) => error instanceof WebviewBridgeError && error.code === "request_failed");
});
