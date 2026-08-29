import assert from "node:assert/strict";
import test from "node:test";
import {
  AgentHostSession,
  ProtocolError,
  createHostHello,
  parseAgentHostEnvelope,
  parseHostHello,
} from "../dist/agent-host.js";

const policy = {
  local_execution_enabled: true,
  validation_operations: { unit_test: true, build: false },
  auto_approve: false,
  require_confirmation_on_failure: true,
};

test("creates and parses a host hello envelope", () => {
  const hello = createHostHello({
    messageId: "message-1",
    sessionId: "session-1",
    workspaceId: "workspace-1",
    extensionVersion: "0.1.0",
    capabilities: ["workspace", "file", "workspace"],
  });

  assert.deepEqual(parseHostHello(hello).payload.capabilities, ["workspace", "file"]);
  assert.equal(hello.kind, "host_hello");
  assert.deepEqual(hello.payload.protocol_versions, [1]);
});

test("rejects unsupported envelope versions and capabilities", () => {
  assert.throws(
    () => parseAgentHostEnvelope({ message_id: "m", session_id: "s", schema_version: 2, kind: "tool_action", payload: {} }),
    (error) => error instanceof ProtocolError && error.code === "unsupported_contract",
  );
  assert.throws(
    () => parseAgentHostEnvelope({ message_id: "m", session_id: "s", schema_version: 1, kind: "tool_action", capability: "network", payload: {} }),
    (error) => error instanceof ProtocolError && error.code === "invalid_payload",
  );
});

test("accepts handshake and applies only newer policy versions", () => {
  const session = new AgentHostSession();
  const accepted = session.acceptHandshake({
    session_id: "session-1",
    workspace_id: "workspace-1",
    extension_version: "0.1.0",
    protocol_version: 1,
    capabilities: ["workspace", "validation"],
    policy_version: 3,
    policy,
    pending_actions: [],
  });

  assert.equal(accepted.policy_version, 3);
  assert.equal(session.applyPolicyUpdate({ policy_version: 4, policy: { ...policy, auto_approve: true } }).auto_approve, true);
  assert.throws(
    () => session.applyPolicyUpdate({ policy_version: 4, policy }),
    (error) => error instanceof ProtocolError && error.code === "invalid_payload",
  );
});

test("requires handshake before applying policy updates", () => {
  assert.throws(
    () => new AgentHostSession().applyPolicyUpdate({ policy_version: 1, policy }),
    (error) => error instanceof ProtocolError && error.code === "invalid_payload",
  );
});
