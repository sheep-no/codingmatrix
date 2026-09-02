import { AgentHostEnvelope, AgentHostSession } from "./agent-host.js";
import { ApprovalBridge } from "./approval-bridge.js";
import type { CloudConnection } from "./connection.js";
import { ToolDispatcher } from "./tool-dispatcher.js";
import type { LocalValidationResult } from "./protocol.js";

export interface AgentHostRuntimeOptions {
  session: AgentHostSession;
  dispatcher: ToolDispatcher;
  connection?: Pick<CloudConnection, "fetchPendingActions" | "submitResult"> & Partial<Pick<CloudConnection, "fetchAgentHostActions" | "submitEvent">>;
  approvalBridge?: ApprovalBridge;
  onEvent?: (event: AgentHostEnvelope) => void | Promise<void>;
  onSessionControl?: (action: "pause" | "resume" | "cancel") => void | Promise<void>;
  onSkillRevoke?: (skillName: string) => void | Promise<void>;
  onSkillSync?: (skills: Record<string, unknown>) => void | Promise<void>;
}

export class AgentHostRuntimeError extends Error {
  constructor(public readonly code: "session_mismatch" | "policy_mismatch" | "session_paused" | "session_cancelled", message: string) {
    super(message);
    this.name = "AgentHostRuntimeError";
  }
}

export class AgentHostRuntime {
  private readonly session: AgentHostSession;
  private readonly dispatcher: ToolDispatcher;
  private connection?: Pick<CloudConnection, "fetchPendingActions" | "submitResult"> & Partial<Pick<CloudConnection, "fetchAgentHostActions" | "submitEvent">>;
  private readonly onEvent: (event: AgentHostEnvelope) => void | Promise<void>;
  private readonly approvalBridge?: ApprovalBridge;
  private readonly onSessionControl?: AgentHostRuntimeOptions["onSessionControl"];
  private readonly onSkillRevoke?: AgentHostRuntimeOptions["onSkillRevoke"];
  private readonly onSkillSync?: AgentHostRuntimeOptions["onSkillSync"];
  private controlStatus: "active" | "paused" | "cancelled" = "active";

  constructor(options: AgentHostRuntimeOptions) {
    this.session = options.session;
    this.dispatcher = options.dispatcher;
    this.connection = options.connection;
    this.approvalBridge = options.approvalBridge;
    this.onEvent = options.onEvent ?? (() => undefined);
    this.onSessionControl = options.onSessionControl;
    this.onSkillRevoke = options.onSkillRevoke;
    this.onSkillSync = options.onSkillSync;
  }

  setConnection(connection: AgentHostRuntimeOptions["connection"]): void {
    this.connection = connection;
  }

  async process(action: AgentHostEnvelope): Promise<unknown> {
    if (action.kind === "policy_update") return this.applyPolicyUpdate(action);
    if (action.kind === "approval_decision") return this.applyApprovalDecision(action);
    if (action.kind === "session_control") return this.applySessionControl(action);
    if (action.kind === "skill_revoke") return this.applySkillRevoke(action);
    const snapshot = this.session.snapshot();
    if (action.session_id !== snapshot.session_id) {
      throw new AgentHostRuntimeError("session_mismatch", "action belongs to another session");
    }
    if (action.policy_version !== undefined && action.policy_version !== snapshot.policy_version) {
      throw new AgentHostRuntimeError("policy_mismatch", "action uses a stale policy version");
    }
    if (this.controlStatus === "paused") throw new AgentHostRuntimeError("session_paused", "session is paused");
    if (this.controlStatus === "cancelled") throw new AgentHostRuntimeError("session_cancelled", "session is cancelled");
    if (action.capability === "skill_runtime" && action.kind === "tool_action") {
      return this.applySkillSync(action);
    }
    if (!snapshot.policy.auto_approve && this.approvalBridge) {
      const approved = await this.approvalBridge.request(action);
      if (!approved) return { status: "rejected", action_id: action.message_id };
    }
    const result = await this.dispatcher.dispatch(action);
    if (isLocalValidationResult(result)) {
      if (!this.connection) {
        await this.emitResult({
          message_id: `${action.message_id}:result`,
          schema_version: action.schema_version,
          session_id: action.session_id,
          task_id: action.task_id,
          revision: action.revision,
          kind: "tool_result",
          capability: action.capability,
          policy_version: snapshot.policy_version,
          payload: result,
        });
      } else {
        await this.connection.submitResult(result);
      }
      return result;
    }
    const event: AgentHostEnvelope = {
      message_id: `${action.message_id}:result`,
      schema_version: action.schema_version,
      session_id: action.session_id,
      task_id: action.task_id,
      revision: action.revision,
      kind: "tool_result",
      capability: action.capability,
      policy_version: snapshot.policy_version,
      payload: result,
    };
    if (this.connection?.submitEvent) await this.connection.submitEvent(event);
    else await this.emitResult(event);
    return result;
  }

  private applyPolicyUpdate(action: AgentHostEnvelope): unknown {
    const payload = action.payload;
    if (!isRecord(payload) || action.policy_version === undefined || !isRecord(payload.policy)) {
      throw new AgentHostRuntimeError("policy_mismatch", "policy update requires a version and policy payload");
    }
    const policy = this.session.applyPolicyUpdate({
      policy_version: action.policy_version,
      policy: payload.policy,
    });
    const setPolicy = this.dispatcher.setPolicy;
    if (typeof setPolicy === "function") setPolicy.call(this.dispatcher, policy);
    return policy;
  }

  private applyApprovalDecision(action: AgentHostEnvelope): boolean {
    if (!this.approvalBridge || !isRecord(action.payload)) return false;
    const requestId = action.payload.request_id;
    const approved = action.payload.approved;
    if (typeof requestId !== "string" || typeof approved !== "boolean") return false;
    const snapshot = this.session.snapshot();
    if (action.session_id !== snapshot.session_id) {
      throw new AgentHostRuntimeError("session_mismatch", "approval belongs to another session");
    }
    return this.approvalBridge.decide(requestId, approved);
  }

  private async applySessionControl(action: AgentHostEnvelope): Promise<string> {
    if (!isRecord(action.payload) || !isSessionControl(action.payload.action)) {
      throw new AgentHostRuntimeError("session_mismatch", "session control action is invalid");
    }
    if (action.session_id !== this.session.snapshot().session_id) {
      throw new AgentHostRuntimeError("session_mismatch", "control belongs to another session");
    }
    this.controlStatus = action.payload.action === "cancel" ? "cancelled" : action.payload.action === "pause" ? "paused" : "active";
    await this.onSessionControl?.(action.payload.action);
    return this.controlStatus;
  }

  private async applySkillRevoke(action: AgentHostEnvelope): Promise<boolean> {
    if (!isRecord(action.payload) || typeof action.payload.skill_name !== "string") {
      throw new AgentHostRuntimeError("policy_mismatch", "skill revoke requires skill_name");
    }
    if (action.session_id !== this.session.snapshot().session_id) {
      throw new AgentHostRuntimeError("session_mismatch", "skill revoke belongs to another session");
    }
    await this.onSkillRevoke?.(action.payload.skill_name);
    return true;
  }

  private async applySkillSync(action: AgentHostEnvelope): Promise<boolean> {
    if (!isRecord(action.payload) || !["sync", "sync_user"].includes(String(action.payload.operation)) || !isRecord(action.payload.skills)) {
      throw new AgentHostRuntimeError("policy_mismatch", "skill sync requires a skills object");
    }
    await this.onSkillSync?.(action.payload.skills);
    return true;
  }

  async poll(): Promise<number> {
    if (!this.connection) return 0;
    if (this.connection.fetchAgentHostActions) {
      const actions = await this.connection.fetchAgentHostActions();
      for (const action of actions) await this.process(action);
      return actions.length;
    }
    const policyVersion = this.session.snapshot().policy_version;
    const actions = await this.connection.fetchPendingActions();
    for (const action of actions) {
      await this.process({
        message_id: action.event_id,
        schema_version: action.schema_version,
        session_id: action.session_id,
        task_id: action.task_id,
        revision: action.revision,
        kind: "tool_action",
        capability: "validation",
        policy_version: policyVersion,
        payload: action,
      });
    }
    return actions.length;
  }

  private async emitResult(event: AgentHostEnvelope): Promise<void> {
    await this.onEvent(event);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSessionControl(value: unknown): value is "pause" | "resume" | "cancel" {
  return value === "pause" || value === "resume" || value === "cancel";
}

function isLocalValidationResult(value: unknown): value is LocalValidationResult {
  return typeof value === "object" && value !== null
    && "source" in value && value.source === "local"
    && "event_id" in value && typeof value.event_id === "string";
}
