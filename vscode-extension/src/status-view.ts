import {
  LocalValidationResult,
  PendingAction,
  ValidationResultStatus,
} from "./protocol.js";

export type ValidationViewStatus =
  | "waiting_for_confirmation"
  | "running"
  | ValidationResultStatus;

export interface ValidationDiagnostic {
  readonly message: string;
  readonly severity: "info" | "warning" | "error";
  readonly location?: string;
}

export interface ValidationTaskSnapshot {
  readonly action_id: string;
  readonly session_id: string;
  readonly task_id: string;
  readonly revision: number;
  readonly workspace_id: string;
  readonly validation_scope: PendingAction["validation_scope"];
  readonly operation: PendingAction["operation"];
  readonly status: ValidationViewStatus;
  readonly started_at?: string;
  readonly finished_at?: string;
  readonly elapsed_seconds?: number;
  readonly can_cancel: boolean;
  readonly diagnostics: ValidationDiagnostic[];
}

export interface ValidationTaskDisplay extends ValidationTaskSnapshot {
  readonly title: string;
  readonly impact: string;
  readonly notification: string;
}

export class ValidationStatusView {
  private readonly now: () => number;
  private readonly tasks = new Map<string, ValidationTaskSnapshot>();
  private readonly cancellation = new Map<string, () => void>();

  constructor(options: { now?: () => number } = {}) {
    this.now = options.now ?? (() => Date.now());
  }

  showAction(action: PendingAction, workspaceAuthorized: boolean): ValidationTaskDisplay {
    const snapshot: ValidationTaskSnapshot = {
      action_id: action.action_id,
      session_id: action.session_id,
      task_id: action.task_id,
      revision: action.revision,
      workspace_id: action.workspace_id,
      validation_scope: action.validation_scope,
      operation: action.operation,
      status: "waiting_for_confirmation",
      can_cancel: false,
      diagnostics: workspaceAuthorized
        ? []
        : [{
            message: "workspace authorization is required before validation can run",
            severity: "warning",
          }],
    };
    this.tasks.set(action.action_id, snapshot);
    return this.display(snapshot);
  }

  start(action: PendingAction, onCancel: () => void): ValidationTaskDisplay {
    const startedAt = new Date(this.now()).toISOString();
    const snapshot: ValidationTaskSnapshot = {
      action_id: action.action_id,
      session_id: action.session_id,
      task_id: action.task_id,
      revision: action.revision,
      workspace_id: action.workspace_id,
      validation_scope: action.validation_scope,
      operation: action.operation,
      status: "running",
      started_at: startedAt,
      elapsed_seconds: 0,
      can_cancel: true,
      diagnostics: [],
    };
    this.tasks.set(action.action_id, snapshot);
    this.cancellation.set(action.action_id, onCancel);
    return this.display(snapshot);
  }

  cancel(actionId: string): ValidationTaskDisplay | undefined {
    const snapshot = this.tasks.get(actionId);
    if (!snapshot || snapshot.status !== "running") return undefined;
    this.cancellation.get(actionId)?.();
    const cancelled: ValidationTaskSnapshot = {
      ...snapshot,
      status: "cancelled",
      finished_at: new Date(this.now()).toISOString(),
      elapsed_seconds: this.elapsed(snapshot.started_at),
      can_cancel: false,
      diagnostics: [{ message: "validation cancelled by user", severity: "warning" }],
    };
    this.tasks.set(actionId, cancelled);
    this.cancellation.delete(actionId);
    return this.display(cancelled);
  }

  complete(result: LocalValidationResult): ValidationTaskDisplay | undefined {
    const current = [...this.tasks.values()].find(
      (task) => task.session_id === result.session_id
        && task.task_id === result.task_id
        && task.revision === result.revision
        && task.validation_scope === result.validation_scope,
    );
    if (!current) return undefined;
    const completed: ValidationTaskSnapshot = {
      ...current,
      status: result.status,
      finished_at: result.finished_at,
      elapsed_seconds: this.elapsed(result.started_at, result.finished_at),
      can_cancel: false,
      diagnostics: result.summary.diagnostics.map((diagnostic) => ({
        message: this.diagnosticMessage(diagnostic),
        severity: result.status === "passed"
          ? "info"
          : result.status === "waiting_for_confirmation" ? "warning" : "error",
        ...(typeof diagnostic.file === "string" ? { location: diagnostic.file } : {}),
      })),
    };
    this.tasks.set(current.action_id, completed);
    this.cancellation.delete(current.action_id);
    return this.display(completed);
  }

  get(actionId: string): ValidationTaskDisplay | undefined {
    const snapshot = this.tasks.get(actionId);
    return snapshot ? this.display(snapshot) : undefined;
  }

  private display(snapshot: ValidationTaskSnapshot): ValidationTaskDisplay {
    return {
      ...snapshot,
      title: `${snapshot.operation} (${snapshot.validation_scope})`,
      impact: this.impactFor(snapshot.operation),
      notification: this.notificationFor(snapshot.status),
      diagnostics: snapshot.diagnostics.map((diagnostic) => ({ ...diagnostic })),
    };
  }

  private elapsed(startedAt?: string, finishedAt?: string): number | undefined {
    if (!startedAt) return undefined;
    const end = finishedAt ? Date.parse(finishedAt) : this.now();
    return Math.max(0, Math.round((end - Date.parse(startedAt)) / 1000));
  }

  private diagnosticMessage(diagnostic: Record<string, unknown>): string {
    return typeof diagnostic.message === "string" ? diagnostic.message : "validation diagnostic";
  }

  private impactFor(operation: PendingAction["operation"]): string {
    if (operation === "build" || operation === "unit_test" || operation === "e2e_test") {
      return "runs local project verification";
    }
    if (operation === "dependency_check") return "inspects project dependencies";
    if (operation === "service_check") return "checks a local service";
    return "checks project syntax";
  }

  private notificationFor(status: ValidationViewStatus): string {
    if (status === "waiting_for_confirmation") return "validation awaits your confirmation";
    if (status === "running") return "validation is running";
    if (status === "passed") return "validation passed";
    return `validation ${status}`;
  }
}
