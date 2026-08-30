import {
  LocalValidationResult,
  PendingAction,
  VALIDATION_OPERATIONS,
  ValidationResultStatus,
} from "./protocol.js";

export interface ProcessStreamLike {
  on(event: "data", listener: (chunk: string | Uint8Array) => void): void;
}

export interface ProcessHandleLike {
  stdout?: ProcessStreamLike;
  stderr?: ProcessStreamLike;
  once(event: "error" | "close", listener: (value?: unknown) => void): void;
  kill(signal?: string): boolean;
}

export interface SpawnOptionsLike {
  cwd: string;
  shell: false;
}

export type SpawnLike = (
  command: string,
  args: string[],
  options: SpawnOptionsLike,
) => ProcessHandleLike;

export interface AbortSignalLike {
  readonly aborted: boolean;
  addEventListener(event: "abort", listener: () => void, options?: { once?: boolean }): void;
  removeEventListener?(event: "abort", listener: () => void): void;
}

export interface ValidationRunnerOptions {
  spawn: SpawnLike;
  now?: () => string;
  createEventId?: () => string;
  outputLimitBytes?: number;
}

export interface RunOptions {
  signal?: AbortSignalLike;
}

export class ValidationRunnerError extends Error {
  constructor(public readonly code: "invalid_action" | "runner_failure", message: string) {
    super(message);
    this.name = "ValidationRunnerError";
  }
}

function isValidationOperation(value: string): boolean {
  return VALIDATION_OPERATIONS.includes(value as (typeof VALIDATION_OPERATIONS)[number]);
}

export class ValidationRunner {
  private readonly spawn: SpawnLike;
  private readonly now: () => string;
  private readonly createEventId: () => string;
  private readonly outputLimitBytes: number;

  constructor(options: ValidationRunnerOptions) {
    this.spawn = options.spawn;
    this.now = options.now ?? (() => new Date().toISOString());
    this.createEventId = options.createEventId ?? (() => `local-result-${Date.now()}`);
    this.outputLimitBytes = options.outputLimitBytes ?? 64 * 1024;
    if (!Number.isInteger(this.outputLimitBytes) || this.outputLimitBytes <= 0) {
      throw new Error("outputLimitBytes must be a positive integer");
    }
  }

  run(action: PendingAction, options: RunOptions = {}): Promise<LocalValidationResult> {
    this.validateAction(action);
    const startedAt = this.now();
    const output: string[] = [];
    let outputLength = 0;
    let outputTruncated = false;
    let child: ProcessHandleLike | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let settled = false;

    const appendOutput = (chunk: string | Uint8Array, stream: string) => {
      if (outputTruncated) return;
      const value = typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
      const remaining = this.outputLimitBytes - outputLength;
      if (remaining <= 0) {
        outputTruncated = true;
        return;
      }
      const captured = value.slice(0, remaining);
      output.push(`[${stream}] ${captured}`);
      outputLength += captured.length;
      if (captured.length < value.length) outputTruncated = true;
    };

    return new Promise((resolve) => {
      const finish = (status: ValidationResultStatus, exitCode?: number, error?: string) => {
        if (settled) return;
        settled = true;
        if (timer) clearTimeout(timer);
        if (options.signal?.removeEventListener) {
          options.signal.removeEventListener("abort", onAbort);
        }
        const diagnostics: Array<Record<string, unknown>> = [];
        if (output.length > 0) {
          diagnostics.push({
            kind: "process_output",
            output: output.join(""),
            truncated: outputTruncated,
          });
        }
        if (error) diagnostics.push({ kind: "runner_error", message: error });
        resolve({
          event_id: this.createEventId(),
          schema_version: 1,
          session_id: action.session_id,
          task_id: action.task_id,
          revision: action.revision,
          source: "local",
          validation_scope: action.validation_scope,
          status,
          started_at: startedAt,
          finished_at: this.now(),
          ...(exitCode === undefined ? {} : { exit_code: exitCode }),
          summary: {
            command_name: action.command[0],
            diagnostics,
          },
          ...(action.run_id === undefined ? {} : { run_id: action.run_id }),
          ...(action.step_id === undefined ? {} : { step_id: action.step_id }),
        });
      };

      const onAbort = () => {
        finish("cancelled", undefined, "validation cancelled by caller");
        child?.kill("SIGTERM");
      };

      if (options.signal?.aborted) {
        finish("cancelled", undefined, "validation cancelled before start");
        return;
      }
      options.signal?.addEventListener("abort", onAbort, { once: true });

      try {
        child = this.spawn(action.command[0], action.command.slice(1), {
          cwd: action.working_directory,
          shell: false,
        });
      } catch (error) {
        finish("failed", undefined, error instanceof Error ? error.message : "process failed to start");
        return;
      }

      child.stdout?.on("data", (chunk) => appendOutput(chunk, "stdout"));
      child.stderr?.on("data", (chunk) => appendOutput(chunk, "stderr"));
      child.once("error", (error) => {
        finish("failed", undefined, error instanceof Error ? error.message : "process error");
      });
      child.once("close", (code) => {
        const exitCode = typeof code === "number" ? code : undefined;
        finish(exitCode === 0 ? "passed" : "failed", exitCode);
      });
      timer = setTimeout(() => {
        finish("timeout", undefined, `validation exceeded ${action.timeout_seconds} seconds`);
        child?.kill("SIGTERM");
      }, action.timeout_seconds * 1000);
    });
  }

  private validateAction(action: PendingAction): void {
    if (!action.command.length || action.command.some((part) => !part)) {
      throw new ValidationRunnerError("invalid_action", "validation command must be non-empty");
    }
    if (!isValidationOperation(action.operation)) {
      throw new ValidationRunnerError("invalid_action", "validation operation is not allowed");
    }
    if (!Number.isInteger(action.timeout_seconds) || action.timeout_seconds <= 0) {
      throw new ValidationRunnerError("invalid_action", "validation timeout must be positive");
    }
  }
}
