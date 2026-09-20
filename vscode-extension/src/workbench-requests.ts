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
    case "learning":
      return connection.fetchLearningStats();
    case "concurrent_limits":
      return connection.fetchConcurrentLimits();
    case "cache_stats":
      return connection.fetchCacheStats();
    case "cache_clear":
      return connection.clearAgentCache(cacheClearMode(params.mode));
    case "decision_submit":
      return connection.submitDecisions(
        requiredStringParam(params.session_id, "session_id"),
        requiredChoiceParams(params.decisions),
      );
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

// Clearing the cache is the only mutating workbench request; an unknown mode
// falls back to the safe "expired" scope instead of wiping every entry.
function cacheClearMode(value: unknown): "expired" | "all" {
  return value === "all" ? "all" : "expired";
}

// A decision is a closed id -> option-label map, so every entry has to be a
// non-empty string. An empty map is rejected because the server answers
// "ignored" and the stream would keep waiting without a real choice.
function requiredChoiceParams(value: unknown): Record<string, string> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("缺少参数：decisions");
  }
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) throw new Error("缺少参数：decisions");
  const choices: Record<string, string> = {};
  for (const [id, label] of entries) {
    if (!id.trim()) throw new Error("参数 decisions 含空标识");
    if (typeof label !== "string" || !label.trim()) throw new Error(`决策 ${id} 未选择选项`);
    choices[id] = label.trim();
  }
  return choices;
}
