import { ProtocolError, SUPPORTED_SCHEMA_VERSION } from "./protocol.js";

export { ProtocolError } from "./protocol.js";

export const AGENT_HOST_KINDS = [
  "host_hello",
  "tool_action",
  "approval_request",
  "approval_decision",
  "progress_event",
  "diagnostic_event",
  "tool_result",
  "policy_update",
  "skill_revoke",
  "session_control",
] as const;

export type AgentHostKind = (typeof AGENT_HOST_KINDS)[number];

export const AGENT_HOST_CAPABILITIES = [
  "workspace",
  "file",
  "terminal",
  "diagnostics",
  "validation",
  "skill_runtime",
] as const;

// The protocol exposes this legacy capability name; its supported contract is metadata sync only.
export const SKILL_RUNTIME_OPERATIONS = ["sync", "sync_user"] as const;

export type AgentHostCapability = (typeof AGENT_HOST_CAPABILITIES)[number];

export interface AgentHostEnvelope<TPayload = unknown> {
  message_id: string;
  schema_version: typeof SUPPORTED_SCHEMA_VERSION;
  session_id: string;
  task_id?: string;
  revision?: number;
  kind: AgentHostKind;
  capability?: AgentHostCapability;
  policy_version?: number;
  payload: TPayload;
}

export interface HostHelloPayload {
  workspace_id: string;
  extension_version: string;
  protocol_versions: number[];
  capabilities: AgentHostCapability[];
}

export interface AgentHostPolicy {
  local_execution_enabled: boolean;
  validation_operations: Record<string, boolean>;
  auto_approve: boolean;
  require_confirmation_on_failure: boolean;
}

export interface HostHandshake {
  session_id: string;
  workspace_id: string;
  extension_version: string;
  protocol_version: typeof SUPPORTED_SCHEMA_VERSION;
  capabilities: AgentHostCapability[];
  policy_version: number;
  policy: AgentHostPolicy;
  pending_actions: AgentHostEnvelope[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(payload: Record<string, unknown>, field: string): string {
  const value = payload[field];
  if (typeof value !== "string" || value.length === 0) {
    throw new ProtocolError("invalid_payload", `${field} must be a non-empty string`);
  }
  return value;
}

function nonNegativeInteger(payload: Record<string, unknown>, field: string): number {
  const value = payload[field];
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new ProtocolError("invalid_payload", `${field} must be a non-negative integer`);
  }
  return value;
}

function parseCapabilities(value: unknown, field = "capabilities"): AgentHostCapability[] {
  if (!Array.isArray(value) || value.some((item) => !AGENT_HOST_CAPABILITIES.includes(item as AgentHostCapability))) {
    throw new ProtocolError("invalid_payload", `${field} must contain supported capabilities`);
  }
  return [...new Set(value)] as AgentHostCapability[];
}

function parsePolicy(value: unknown): AgentHostPolicy {
  if (!isRecord(value)) {
    throw new ProtocolError("invalid_payload", "policy must be an object");
  }
  const operations = value.validation_operations;
  if (!isRecord(operations) || Object.values(operations).some((item) => typeof item !== "boolean")) {
    throw new ProtocolError("invalid_payload", "policy.validation_operations must be boolean flags");
  }
  for (const field of ["local_execution_enabled", "auto_approve", "require_confirmation_on_failure"]) {
    if (typeof value[field] !== "boolean") {
      throw new ProtocolError("invalid_payload", `policy.${field} must be boolean`);
    }
  }
  return {
    local_execution_enabled: value.local_execution_enabled as boolean,
    validation_operations: { ...operations } as Record<string, boolean>,
    auto_approve: value.auto_approve as boolean,
    require_confirmation_on_failure: value.require_confirmation_on_failure as boolean,
  };
}

export function parseAgentHostEnvelope(input: unknown): AgentHostEnvelope {
  if (!isRecord(input)) {
    throw new ProtocolError("invalid_payload", "agent host envelope must be an object");
  }
  if (input.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new ProtocolError("unsupported_contract", "agent host schema version is not supported");
  }
  const kind = input.kind;
  if (!AGENT_HOST_KINDS.includes(kind as AgentHostKind)) {
    throw new ProtocolError("invalid_payload", "agent host kind is not supported");
  }
  const capability = input.capability;
  if (capability !== undefined && !AGENT_HOST_CAPABILITIES.includes(capability as AgentHostCapability)) {
    throw new ProtocolError("invalid_payload", "agent host capability is not supported");
  }
  for (const field of ["task_id", "revision", "policy_version"]) {
    if (input[field] !== undefined && (field === "revision" || field === "policy_version")) {
      nonNegativeInteger(input, field);
    }
  }
  return {
    message_id: requiredString(input, "message_id"),
    schema_version: SUPPORTED_SCHEMA_VERSION,
    session_id: requiredString(input, "session_id"),
    ...(input.task_id === undefined ? {} : { task_id: requiredString(input, "task_id") }),
    ...(input.revision === undefined ? {} : { revision: input.revision as number }),
    kind: kind as AgentHostKind,
    ...(capability === undefined ? {} : { capability: capability as AgentHostCapability }),
    ...(input.policy_version === undefined ? {} : { policy_version: input.policy_version as number }),
    payload: input.payload,
  };
}

export function parseHostHello(input: unknown): AgentHostEnvelope<HostHelloPayload> {
  const envelope = parseAgentHostEnvelope(input);
  if (envelope.kind !== "host_hello" || !isRecord(envelope.payload)) {
    throw new ProtocolError("invalid_payload", "host hello envelope is invalid");
  }
  const payload = envelope.payload;
  const protocolVersions = payload.protocol_versions;
  if (!Array.isArray(protocolVersions) || protocolVersions.some((item) => !Number.isInteger(item))) {
    throw new ProtocolError("invalid_payload", "protocol_versions must be an integer array");
  }
  return {
    ...envelope,
    payload: {
      workspace_id: requiredString(payload, "workspace_id"),
      extension_version: requiredString(payload, "extension_version"),
      protocol_versions: [...protocolVersions] as number[],
      capabilities: parseCapabilities(payload.capabilities),
    },
  };
}

export function createHostHello(options: {
  messageId: string;
  sessionId: string;
  workspaceId: string;
  extensionVersion: string;
  capabilities: AgentHostCapability[];
}): AgentHostEnvelope<HostHelloPayload> {
  return {
    message_id: options.messageId,
    schema_version: SUPPORTED_SCHEMA_VERSION,
    session_id: options.sessionId,
    kind: "host_hello",
    capability: "workspace",
    payload: {
      workspace_id: options.workspaceId,
      extension_version: options.extensionVersion,
      protocol_versions: [SUPPORTED_SCHEMA_VERSION],
      capabilities: parseCapabilities(options.capabilities),
    },
  };
}

export class AgentHostSession {
  private handshake?: HostHandshake;

  acceptHandshake(input: unknown): HostHandshake {
    if (!isRecord(input)) {
      throw new ProtocolError("invalid_payload", "handshake must be an object");
    }
    const capabilities = parseCapabilities(input.capabilities);
    const protocolVersion = input.protocol_version;
    if (protocolVersion !== SUPPORTED_SCHEMA_VERSION) {
      throw new ProtocolError("unsupported_contract", "handshake protocol version is not supported");
    }
    const policyVersion = nonNegativeInteger(input, "policy_version");
    const handshake: HostHandshake = {
      session_id: requiredString(input, "session_id"),
      workspace_id: requiredString(input, "workspace_id"),
      extension_version: requiredString(input, "extension_version"),
      protocol_version: SUPPORTED_SCHEMA_VERSION,
      capabilities,
      policy_version: policyVersion,
      policy: parsePolicy(input.policy),
      pending_actions: Array.isArray(input.pending_actions)
        ? input.pending_actions.map(parseAgentHostEnvelope)
        : [],
    };
    this.handshake = handshake;
    return this.snapshot();
  }

  applyPolicyUpdate(input: unknown): AgentHostPolicy {
    if (!isRecord(input)) {
      throw new ProtocolError("invalid_payload", "policy update must be an object");
    }
    const version = nonNegativeInteger(input, "policy_version");
    if (!this.handshake) {
      throw new ProtocolError("invalid_payload", "handshake is required before policy updates");
    }
    if (version <= this.handshake.policy_version) {
      throw new ProtocolError("invalid_payload", "policy version must increase monotonically");
    }
    const policy = parsePolicy(input.policy);
    this.handshake = { ...this.handshake, policy_version: version, policy };
    return { ...policy, validation_operations: { ...policy.validation_operations } };
  }

  snapshot(): HostHandshake {
    if (!this.handshake) {
      throw new ProtocolError("invalid_payload", "handshake has not been accepted");
    }
    return {
      ...this.handshake,
      capabilities: [...this.handshake.capabilities],
      pending_actions: [...this.handshake.pending_actions],
      policy: { ...this.handshake.policy, validation_operations: { ...this.handshake.policy.validation_operations } },
    };
  }
}
