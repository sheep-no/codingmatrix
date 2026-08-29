import assert from "node:assert/strict";
import test from "node:test";
import { ResultSanitizer } from "../dist/result-sanitizer.js";
import { MemoryResultStorage, ResultStore } from "../dist/result-store.js";

const result = {
  event_id: "result-1",
  schema_version: 1,
  session_id: "session-1",
  task_id: "task-1",
  revision: 2,
  source: "local",
  validation_scope: "local_runtime",
  status: "failed",
  started_at: "2026-08-29T00:00:00Z",
  finished_at: "2026-08-29T00:01:00Z",
  exit_code: 1,
  summary: { command_name: "pytest", diagnostics: [] },
};

test("redacts labeled secrets and bearer tokens", () => {
  const sanitized = new ResultSanitizer().sanitize({
    ...result,
    summary: {
      command_name: "pytest",
      diagnostics: [{ message: "api_key=real-secret Bearer real-token" }],
    },
  });

  assert.equal(sanitized.uploadable, true);
  assert.equal(sanitized.redacted, true);
  assert.match(sanitized.result.summary.diagnostics[0].message, /\[REDACTED\]/);
  assert.doesNotMatch(sanitized.result.summary.diagnostics[0].message, /real-secret|real-token/);
});

test("redacts sensitive object fields and private keys", () => {
  const sanitized = new ResultSanitizer().sanitize({
    ...result,
    summary: {
      command_name: "pytest",
      diagnostics: [{ password: "secret-value", key: "safe-value", pem: "-----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----" }],
    },
  });

  assert.equal(sanitized.uploadable, true);
  assert.equal(sanitized.result.summary.diagnostics[0].password, "[REDACTED]");
  assert.doesNotMatch(sanitized.result.summary.diagnostics[0].pem, /PRIVATE KEY/);
});

test("stores sanitized results with event id deduplication", async () => {
  const store = new ResultStore(new MemoryResultStorage(), { now: () => "queued" });
  await store.enqueue(result);
  await store.enqueue(result);

  const pending = await store.listPending();
  assert.equal(pending.length, 1);
  assert.equal(pending[0].queued_at, "queued");
  assert.equal(await store.acknowledge("result-1"), true);
  assert.equal(await store.acknowledge("result-1"), false);
  assert.deepEqual(await store.listPending(), []);
});

test("persists results across store instances", async () => {
  const storage = new MemoryResultStorage();
  const first = new ResultStore(storage);
  await first.enqueue(result);

  const second = new ResultStore(storage);
  assert.equal((await second.listPending()).length, 1);
});
