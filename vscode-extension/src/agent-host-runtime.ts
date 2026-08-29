import { AgentHostEnvelope, AgentHostSession } from "./agent-host.js";
import type { CloudConnection } from "./connection.js";
import { ToolDispatcher } from "./tool-dispatcher.js";
import type { LocalValidationResult } from "./protocol.js";

export interface AgentHostRuntimeOptions {
  session: AgentHostSession;
  dispatcher: ToolDispatcher;
  connection?: Pick<CloudConnection, "fetchPendingActions" | "submitResult">;
  onEvent?: (event: AgentHostEnvelope) => void | Promise<void>;
}

export class AgentHostRuntimeError extends Error {
  constructor(public readonly code: "session_mismatch" | "policy_mismatch", message: string) {
    super(message);
    this.name = "AgentHostRuntimeError";
  }
}

export class AgentHostRuntime {
  private readonly session: AgentHostSession;
  private readonly dispatcher: ToolDispatcher;
  private readonly connection?: Pick<CloudConnection, "fetchPendingActions" | "submitResult">;
  private readonly onEvent: (event: AgentHostEnvelope) => void | Promise<void>;

  constructor(options: AgentHostRuntimeOptions) {
    this.session = options.session;
    this.dispatcher = options.dispatcher;
    this.connection = options.connection;
    this.onEvent = options.onEvent ?? (() => undefined);
  }

  async process(action: AgentHostEnvelope): Promise<unknown> {
    const snapshot = this.session.snapshot();
    if (action.session_id !== snapshot.session_id) {
      throw new AgentHostRuntimeError("session_mismatch", "action belongs to another session");
    }
    if (action.policy_version !== undefined && action.policy_version !== snapshot.policy_version) {
      throw new AgentHostRuntimeError("policy_mismatch", "action uses a stale policy version");
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
    await this.emitResult(event);
    return result;
  }

  async poll(): Promise<number> {
    if (!this.connection) return 0;
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

function isLocalValidationResult(value: unknown): value is LocalValidationResult {
  return typeof value === "object" && value !== null
    && "source" in value && value.source === "local"
    && "event_id" in value && typeof value.event_id === "string";
}
