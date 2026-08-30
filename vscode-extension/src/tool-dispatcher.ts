import { createHash } from "node:crypto";
import { readFile, stat, writeFile } from "node:fs/promises";
import { AgentHostEnvelope, AgentHostPolicy } from "./agent-host.js";
import { parsePendingAction } from "./protocol.js";
import { ValidationRunner } from "./validation-runner.js";
import { WorkspaceAuthorization } from "./workspace-authorization.js";

export interface FileReadPayload {
  workspace_id: string;
  path: string;
  max_bytes?: number;
}

export interface FileWritePayload {
  workspace_id: string;
  path: string;
  content: string;
  expected_hash?: string;
}

export interface DiagnosticsPayload {
  workspace_id: string;
}

export interface FileToolResult {
  workspace_id: string;
  path: string;
  content: string;
  hash: string;
  size_bytes: number;
}

export interface FileWriteResult {
  workspace_id: string;
  path: string;
  hash: string;
  size_bytes: number;
}

export interface ToolDispatcherOptions {
  authorization: WorkspaceAuthorization;
  validationRunner: ValidationRunner;
  diagnostics?: (workspaceId: string) => Promise<Array<Record<string, unknown>>>;
  policy?: AgentHostPolicy;
}

export class ToolDispatcherError extends Error {
  constructor(
    public readonly code:
      | "unsupported_capability"
      | "execution_disabled"
      | "invalid_action"
      | "workspace_required"
      | "file_conflict",
    message: string,
  ) {
    super(message);
    this.name = "ToolDispatcherError";
  }
}

const DEFAULT_MAX_BYTES = 256 * 1024;

export class ToolDispatcher {
  private readonly authorization: WorkspaceAuthorization;
  private readonly validationRunner: ValidationRunner;
  private readonly diagnostics: (workspaceId: string) => Promise<Array<Record<string, unknown>>>;
  private policy?: AgentHostPolicy;

  constructor(options: ToolDispatcherOptions) {
    this.authorization = options.authorization;
    this.validationRunner = options.validationRunner;
    this.diagnostics = options.diagnostics ?? (async () => []);
    this.policy = options.policy;
  }

  setPolicy(policy: AgentHostPolicy): void {
    this.policy = {
      ...policy,
      validation_operations: { ...policy.validation_operations },
    };
  }

  async dispatch(envelope: AgentHostEnvelope): Promise<unknown> {
    if (!envelope.capability) {
      throw new ToolDispatcherError("unsupported_capability", "tool action capability is required");
    }
    if (this.policy && !this.policy.local_execution_enabled) {
      throw new ToolDispatcherError("execution_disabled", "local execution is disabled by policy");
    }
    switch (envelope.capability) {
      case "file":
        return this.dispatchFile(envelope);
      case "validation":
        return this.dispatchValidation(envelope);
      case "terminal":
        return this.dispatchTerminal(envelope);
      case "diagnostics":
        return this.dispatchDiagnostics(envelope);
      case "workspace":
        return this.dispatchWorkspace(envelope);
      case "skill_runtime":
        throw new ToolDispatcherError("unsupported_capability", `${envelope.capability} dispatch is not implemented`);
    }
  }

  private async dispatchFile(envelope: AgentHostEnvelope): Promise<FileToolResult | FileWriteResult> {
    if (envelope.kind !== "tool_action" || !isRecord(envelope.payload)) {
      throw new ToolDispatcherError("invalid_action", "file actions must be tool_action envelopes");
    }
    const payload = envelope.payload;
    const workspaceId = requiredString(payload, "workspace_id");
    const path = requiredString(payload, "path");
    const resolvedPath = await this.authorization.resolve(workspaceId, path);
    if (typeof payload.content === "string") {
      const expectedHash = payload.expected_hash;
      if (expectedHash !== undefined && typeof expectedHash !== "string") {
        throw new ToolDispatcherError("invalid_action", "expected_hash must be a string");
      }
      const currentHash = await hashFileIfPresent(resolvedPath);
      if (expectedHash !== undefined && currentHash !== expectedHash) {
        throw new ToolDispatcherError("file_conflict", "file changed since the expected hash was captured");
      }
      const content = payload.content;
      await writeFile(resolvedPath, content, "utf8");
      return { workspace_id: workspaceId, path, hash: hash(content), size_bytes: Buffer.byteLength(content, "utf8") };
    }
    const maxBytes = payload.max_bytes === undefined ? DEFAULT_MAX_BYTES : payload.max_bytes;
    if (typeof maxBytes !== "number" || !Number.isInteger(maxBytes) || maxBytes <= 0 || maxBytes > DEFAULT_MAX_BYTES) {
      throw new ToolDispatcherError("invalid_action", `max_bytes must be between 1 and ${DEFAULT_MAX_BYTES}`);
    }
    const content = await readFile(resolvedPath, "utf8");
    const encoded = Buffer.from(content, "utf8");
    const visible = encoded.subarray(0, maxBytes).toString("utf8");
    return { workspace_id: workspaceId, path, content: visible, hash: hash(content), size_bytes: encoded.byteLength };
  }

  private async dispatchValidation(envelope: AgentHostEnvelope): Promise<unknown> {
    if (envelope.kind !== "tool_action") {
      throw new ToolDispatcherError("invalid_action", "validation actions must be tool_action envelopes");
    }
    const action = parsePendingAction(envelope.payload);
    const enabled = this.policy?.validation_operations[action.operation];
    if (enabled === false) {
      throw new ToolDispatcherError("execution_disabled", `${action.operation} is disabled by policy`);
    }
    return this.validationRunner.run(action);
  }

  private async dispatchTerminal(envelope: AgentHostEnvelope): Promise<unknown> {
    if (envelope.kind !== "tool_action") {
      throw new ToolDispatcherError("invalid_action", "terminal actions must be tool_action envelopes");
    }
    // Terminal actions use the same constrained command contract as validation.
    return this.dispatchValidation(envelope);
  }

  private async dispatchDiagnostics(envelope: AgentHostEnvelope): Promise<Array<Record<string, unknown>>> {
    if (envelope.kind !== "tool_action" || !isRecord(envelope.payload)) {
      throw new ToolDispatcherError("invalid_action", "diagnostic actions must be tool_action envelopes");
    }
    const workspaceId = requiredString(envelope.payload, "workspace_id");
    if (!this.authorization.isAuthorized(workspaceId)) {
      throw new ToolDispatcherError("workspace_required", "workspace authorization is required");
    }
    return this.diagnostics(workspaceId);
  }

  private dispatchWorkspace(envelope: AgentHostEnvelope): Array<{ workspace_id: string; root: string }> {
    if (envelope.kind !== "tool_action" || !isRecord(envelope.payload)) {
      throw new ToolDispatcherError("invalid_action", "workspace actions must be tool_action envelopes");
    }
    const operation = envelope.payload.operation;
    if (operation !== "inspect" && operation !== "list_roots") {
      throw new ToolDispatcherError("invalid_action", "workspace operation must be inspect or list_roots");
    }
    return this.authorization.listAuthorized();
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(payload: Record<string, unknown>, field: string): string {
  const value = payload[field];
  if (typeof value !== "string" || value.length === 0) {
    throw new ToolDispatcherError("invalid_action", `${field} must be a non-empty string`);
  }
  return value;
}

function hash(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function hashFileIfPresent(path: string): Promise<string | undefined> {
  try {
    const [content, fileStat] = await Promise.all([readFile(path, "utf8"), stat(path)]);
    if (!fileStat.isFile()) return undefined;
    return hash(content);
  } catch (error) {
    if (isFileMissing(error)) return undefined;
    throw error;
  }
}

function isFileMissing(error: unknown): boolean {
  return isRecord(error) && error.code === "ENOENT";
}
