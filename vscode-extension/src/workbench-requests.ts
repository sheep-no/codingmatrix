import { WorkbenchRequest } from "./agent-workbench.js";
import { CloudConnection } from "./connection.js";

// The workbench panels read user-scoped data through one typed channel. Params
// are validated here so a malformed webview message cannot reach the cloud API.
export async function dispatchWorkbenchRequest(
  connection: CloudConnection,
  request: WorkbenchRequest,
): Promise<unknown> {
  const params = request.params;
  switch (request.resource) {
    case "history_list": {
      const limit = optionalIntegerParam(params.limit, "limit", 1);
      const offset = optionalIntegerParam(params.offset, "offset", 0);
      return connection.listConversations({
        ...(limit === undefined ? {} : { limit }),
        ...(offset === undefined ? {} : { offset }),
      });
    }
    case "history_messages":
      return connection.fetchConversationHistory(requiredIntegerParam(params.conversation_id, "conversation_id"), {
        limit: optionalIntegerParam(params.limit, "limit", 1) ?? 50,
      });
    case "history_delete":
      return connection.deleteConversation(requiredIntegerParam(params.conversation_id, "conversation_id"));
    case "model_config":
      return connection.fetchAgentModelConfig();
    case "token_usage":
      return connection.fetchTokenUsage();
    case "snapshot_list":
      return connection.listSnapshots(requiredStringParam(params.session_id, "session_id"));
    case "snapshot_rollback":
      return connection.rollbackToSnapshot(
        requiredStringParam(params.session_id, "session_id"),
        requiredStringParam(params.target_tag, "target_tag"),
      );
    case "snapshot_diff":
      return connection.fetchSnapshotDiff(
        requiredStringParam(params.session_id, "session_id"),
        requiredStringParam(params.from_tag, "from_tag"),
        requiredStringParam(params.to_tag, "to_tag"),
      );
    case "performance":
      return connection.fetchPerformance();
    default:
      throw new Error(`不支持的工作台请求：${request.resource satisfies never}`);
  }
}

function requiredStringParam(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`缺少参数：${field}`);
  return value.trim();
}

function requiredIntegerParam(value: unknown, field: string): number {
  if (value === undefined || value === null || value === "") throw new Error(`缺少参数：${field}`);
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`参数 ${field} 必须为正整数`);
  return parsed;
}

function optionalIntegerParam(value: unknown, field: string, minimum: number): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum) throw new Error(`参数 ${field} 无效`);
  return parsed;
}
