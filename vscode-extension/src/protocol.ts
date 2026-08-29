export const SUPPORTED_SCHEMA_VERSION = 1 as const;

export const LOCAL_VALIDATION_SCOPES = [
  "local_runtime",
  "local_e2e",
] as const;

export type ValidationScope = (typeof LOCAL_VALIDATION_SCOPES)[number];

export const VALIDATION_OPERATIONS = [
  "syntax_check",
  "dependency_check",
  "build",
  "unit_test",
  "e2e_test",
  "service_check",
] as const;

export type ValidationOperation = (typeof VALIDATION_OPERATIONS)[number];

export const VALIDATION_RESULT_STATUSES = [
  "passed",
  "failed",
  "timeout",
  "rejected",
  "waiting_for_confirmation",
  "cancelled",
] as const;

export type ValidationResultStatus =
  (typeof VALIDATION_RESULT_STATUSES)[number];

export interface PendingAction {
  action_id: string;
  event_id: string;
  schema_version: typeof SUPPORTED_SCHEMA_VERSION;
  session_id: string;
  task_id: string;
  revision: number;
  workspace_id: string;
  validation_scope: ValidationScope;
  operation: ValidationOperation;
  command: string[];
  working_directory: string;
  timeout_seconds: number;
  requested_by: "cloud";
}

export interface ValidationSummary {
  command_name: string;
  tests_total?: number;
  tests_passed?: number;
  tests_failed?: number;
  diagnostics: Array<Record<string, unknown>>;
}

export interface LocalValidationResult {
  event_id: string;
  schema_version: typeof SUPPORTED_SCHEMA_VERSION;
  session_id: string;
  task_id: string;
  revision: number;
  source: "local";
  validation_scope: ValidationScope;
  status: ValidationResultStatus;
  started_at: string;
  finished_at: string;
  exit_code?: number;
  summary: ValidationSummary;
}

export class ProtocolError extends Error {
  constructor(
    public readonly code: "invalid_payload" | "unsupported_contract",
    message: string,
  ) {
    super(message);
    this.name = "ProtocolError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(
  payload: Record<string, unknown>,
  field: string,
): string {
  const value = payload[field];
  if (typeof value !== "string" || value.length === 0) {
    throw new ProtocolError("invalid_payload", `${field} must be a non-empty string`);
  }
  return value;
}

function nonNegativeInteger(
  payload: Record<string, unknown>,
  field: string,
): number {
  const value = payload[field];
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new ProtocolError("invalid_payload", `${field} must be a non-negative integer`);
  }
  return value;
}

function schemaVersion(payload: Record<string, unknown>): typeof SUPPORTED_SCHEMA_VERSION {
  if (payload.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new ProtocolError(
      "unsupported_contract",
      `schema_version ${String(payload.schema_version)} is not supported`,
    );
  }
  return SUPPORTED_SCHEMA_VERSION;
}

function localScope(value: unknown): ValidationScope {
  if (!LOCAL_VALIDATION_SCOPES.includes(value as ValidationScope)) {
    throw new ProtocolError(
      "invalid_payload",
      "validation_scope must be local_runtime or local_e2e",
    );
  }
  return value as ValidationScope;
}

function operation(value: unknown): ValidationOperation {
  if (!VALIDATION_OPERATIONS.includes(value as ValidationOperation)) {
    throw new ProtocolError("invalid_payload", "operation is not supported");
  }
  return value as ValidationOperation;
}

function safeWorkingDirectory(value: string): string {
  if (value.startsWith("/") || /^[A-Za-z]:[\\/]/.test(value)) {
    throw new ProtocolError("invalid_payload", "working_directory must be relative");
  }
  const segments = value.replaceAll("\\", "/").split("/");
  if (segments.includes("..")) {
    throw new ProtocolError(
      "invalid_payload",
      "working_directory cannot escape the workspace",
    );
  }
  return value;
}

export function parsePendingAction(input: unknown): PendingAction {
  if (!isRecord(input)) {
    throw new ProtocolError("invalid_payload", "pending action must be an object");
  }
  const command = input.command;
  if (
    !Array.isArray(command) ||
    command.length === 0 ||
    command.some((part) => typeof part !== "string" || part.length === 0)
  ) {
    throw new ProtocolError("invalid_payload", "command must be a non-empty string array");
  }
  const requestedBy = input.requested_by;
  if (requestedBy !== "cloud") {
    throw new ProtocolError("invalid_payload", "requested_by must be cloud");
  }
  const timeout = input.timeout_seconds;
  if (typeof timeout !== "number" || !Number.isInteger(timeout) || timeout <= 0) {
    throw new ProtocolError("invalid_payload", "timeout_seconds must be a positive integer");
  }
  return {
    action_id: requiredString(input, "action_id"),
    event_id: requiredString(input, "event_id"),
    schema_version: schemaVersion(input),
    session_id: requiredString(input, "session_id"),
    task_id: requiredString(input, "task_id"),
    revision: nonNegativeInteger(input, "revision"),
    workspace_id: requiredString(input, "workspace_id"),
    validation_scope: localScope(input.validation_scope),
    operation: operation(input.operation),
    command: [...command] as string[],
    working_directory: safeWorkingDirectory(requiredString(input, "working_directory")),
    timeout_seconds: timeout,
    requested_by: "cloud",
  };
}

export function parseLocalValidationResult(input: unknown): LocalValidationResult {
  if (!isRecord(input)) {
    throw new ProtocolError("invalid_payload", "validation result must be an object");
  }
  const status = input.status;
  if (!VALIDATION_RESULT_STATUSES.includes(status as ValidationResultStatus)) {
    throw new ProtocolError("invalid_payload", "status is not supported");
  }
  if (input.source !== "local") {
    throw new ProtocolError("invalid_payload", "source must be local");
  }
  const summary = input.summary;
  if (!isRecord(summary) || typeof summary.command_name !== "string") {
    throw new ProtocolError("invalid_payload", "summary.command_name is required");
  }
  const diagnostics = summary.diagnostics ?? [];
  if (!Array.isArray(diagnostics) || diagnostics.some((item) => !isRecord(item))) {
    throw new ProtocolError("invalid_payload", "summary.diagnostics must be an object array");
  }
  const exitCode = input.exit_code;
  if (exitCode !== undefined && (typeof exitCode !== "number" || !Number.isInteger(exitCode))) {
    throw new ProtocolError("invalid_payload", "exit_code must be an integer");
  }
  return {
    event_id: requiredString(input, "event_id"),
    schema_version: schemaVersion(input),
    session_id: requiredString(input, "session_id"),
    task_id: requiredString(input, "task_id"),
    revision: nonNegativeInteger(input, "revision"),
    source: "local",
    validation_scope: localScope(input.validation_scope),
    status: status as ValidationResultStatus,
    started_at: requiredString(input, "started_at"),
    finished_at: requiredString(input, "finished_at"),
    ...(exitCode === undefined ? {} : { exit_code: exitCode }),
    summary: {
      command_name: summary.command_name,
      ...(typeof summary.tests_total === "number" ? { tests_total: summary.tests_total } : {}),
      ...(typeof summary.tests_passed === "number" ? { tests_passed: summary.tests_passed } : {}),
      ...(typeof summary.tests_failed === "number" ? { tests_failed: summary.tests_failed } : {}),
      diagnostics: [...diagnostics] as Array<Record<string, unknown>>,
    },
  };
}
