import { AgentHostEnvelope } from "./agent-host.js";

export interface ApprovalBridgeOptions {
  onRequest?: (request: AgentHostEnvelope) => void | Promise<void>;
  createRequestId?: (action: AgentHostEnvelope) => string;
}

export class ApprovalBridge {
  private readonly pending = new Map<string, { resolve: (approved: boolean) => void }>();
  private readonly onRequest: (request: AgentHostEnvelope) => void | Promise<void>;
  private readonly createRequestId: (action: AgentHostEnvelope) => string;

  constructor(options: ApprovalBridgeOptions = {}) {
    this.onRequest = options.onRequest ?? (() => undefined);
    this.createRequestId = options.createRequestId ?? ((action) => `${action.message_id}:approval`);
  }

  request(action: AgentHostEnvelope): Promise<boolean> {
    const requestId = this.createRequestId(action);
    return new Promise((resolve) => {
      this.pending.set(requestId, { resolve });
      void this.onRequest({
        message_id: requestId,
        schema_version: action.schema_version,
        session_id: action.session_id,
        task_id: action.task_id,
        revision: action.revision,
        kind: "approval_request",
        capability: action.capability,
        policy_version: action.policy_version,
        payload: { action },
      });
    });
  }

  decide(requestId: string, approved: boolean): boolean {
    const pending = this.pending.get(requestId);
    if (!pending) return false;
    this.pending.delete(requestId);
    pending.resolve(approved);
    return true;
  }

  dispose(): void {
    for (const pending of this.pending.values()) pending.resolve(false);
    this.pending.clear();
  }
}
