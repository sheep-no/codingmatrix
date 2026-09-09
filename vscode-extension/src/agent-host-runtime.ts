import { AgentHostEnvelope, AgentHostSession, SKILL_RUNTIME_OPERATIONS } from "./agent-host.js";
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
  private readonly actionExecutions = new Map<string, Promise<unknown>>();
  private readonly activeActions = new Map<string, AbortController>();
  private connectionGeneration = 0;
  private activePoll?: { generation: number; promise: Promise<number> };

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
    this.cancelActiveActions();
    this.connectionGeneration += 1;
    this.activePoll = undefined;
    this.connection = connection;
  }

  resetForHandshake(): void {
    this.cancelActiveActions();
    this.actionExecutions.clear();
    this.controlStatus = "active";
  }

  cancelActiveActions(): void {
    for (const controller of this.activeActions.values()) controller.abort();
    this.activeActions.clear();
    this.approvalBridge?.dispose();
  }

  async process(action: AgentHostEnvelope): Promise<unknown> {
    return this.processWithConnection(action, this.connection);
  }

  private async processWithConnection(
    action: AgentHostEnvelope,
    connection: AgentHostRuntimeOptions["connection"],
  ): Promise<unknown> {
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
    if (action.kind !== "tool_action") {
      return this.executeToolAction(action, snapshot, connection);
    }
    const executionKey = `${action.session_id}:${action.message_id}`;
    const existing = this.actionExecutions.get(executionKey);
    if (existing) return existing;
    const execution = this.executeToolAction(action, snapshot, connection, executionKey);
    this.actionExecutions.set(executionKey, execution);
    void execution.then(
      () => this.trimActionExecutions(),
      () => {
        if (this.actionExecutions.get(executionKey) === execution) this.actionExecutions.delete(executionKey);
      },
    );
    this.trimActionExecutions();
    return execution;
  }

  private trimActionExecutions(): void {
    while (this.actionExecutions.size > 1000) {
      let completedKey: string | undefined;
      for (const key of this.actionExecutions.keys()) {
        if (!this.activeActions.has(key)) {
          completedKey = key;
          break;
        }
      }
      if (!completedKey) return;
      this.actionExecutions.delete(completedKey);
    }
  }

  private async executeToolAction(
    action: AgentHostEnvelope,
    snapshot: ReturnType<AgentHostSession["snapshot"]>,
    connection: AgentHostRuntimeOptions["connection"],
    executionKey?: string,
  ): Promise<unknown> {
    const controller = new AbortController();
    if (executionKey) this.activeActions.set(executionKey, controller);
    try {
      if (!snapshot.policy.auto_approve && this.approvalBridge) {
        const approved = await this.approvalBridge.request(action);
        if (!approved) return { status: "rejected", action_id: action.message_id };
      }
      const result = await this.dispatcher.dispatch(action, { signal: controller.signal });
      if (isLocalValidationResult(result)) {
        if (!connection) {
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
          await connection.submitResult(result);
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
      if (connection?.submitEvent) await connection.submitEvent(event);
      else await this.emitResult(event);
      return result;
    } finally {
      if (executionKey && this.activeActions.get(executionKey) === controller) {
        this.activeActions.delete(executionKey);
      }
    }
  }

  private applyPolicyUpdate(action: AgentHostEnvelope): unknown {
    const payload = action.payload;
    if (!isRecord(payload) || action.policy_version === undefined || !isRecord(payload.policy)) {
      throw new AgentHostRuntimeError("policy_mismatch", "policy update requires a version and policy payload");
    }
    if (action.session_id !== this.session.snapshot().session_id) {
      throw new AgentHostRuntimeError("session_mismatch", "policy update belongs to another session");
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
    if (action.payload.action === "cancel") {
      this.cancelActiveActions();
    }
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
    if (!isRecord(action.payload) || !SKILL_RUNTIME_OPERATIONS.includes(String(action.payload.operation) as typeof SKILL_RUNTIME_OPERATIONS[number]) || !isRecord(action.payload.skills)) {
      throw new AgentHostRuntimeError("policy_mismatch", "skill sync requires a skills object");
    }
    await this.onSkillSync?.(action.payload.skills);
    return true;
  }

  async poll(): Promise<number> {
    const generation = this.connectionGeneration;
    if (this.activePoll?.generation === generation) return this.activePoll.promise;
    const connection = this.connection;
    const poll = this.pollOnce(connection, generation);
    this.activePoll = { generation, promise: poll };
    try {
      return await poll;
    } finally {
      if (this.activePoll?.promise === poll) this.activePoll = undefined;
    }
  }

  private async pollOnce(connection: AgentHostRuntimeOptions["connection"], generation: number): Promise<number> {
    if (!connection) return 0;
    if (connection.fetchAgentHostActions) {
      const actions = await connection.fetchAgentHostActions();
      if (generation !== this.connectionGeneration) return 0;
      for (const action of actions) {
        await this.processWithConnection(action, connection);
        if (generation !== this.connectionGeneration) return 0;
      }
      return actions.length;
    }
    const policyVersion = this.session.snapshot().policy_version;
    const actions = await connection.fetchPendingActions();
    if (generation !== this.connectionGeneration) return 0;
    for (const action of actions) {
      await this.processWithConnection({
        message_id: action.event_id,
        schema_version: action.schema_version,
        session_id: action.session_id,
        task_id: action.task_id,
        revision: action.revision,
        kind: "tool_action",
        capability: "validation",
        policy_version: policyVersion,
        payload: action,
      }, connection);
      if (generation !== this.connectionGeneration) return 0;
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
