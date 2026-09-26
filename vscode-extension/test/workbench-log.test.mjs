import assert from "node:assert/strict";
import test from "node:test";
import { createAgentWorkbenchHtml } from "../dist/agent-workbench.js";

function createHarness() {
  const listeners = [];
  const elements = new Map();
  const makeElement = () => ({
    id: "",
    textContent: "",
    className: "",
    hidden: false,
    checked: false,
    disabled: false,
    value: "",
    title: "",
    children: [],
    scrollTop: 0,
    scrollHeight: 0,
    style: {},
    classList: { toggle() {}, add() {}, remove() {} },
    listeners: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
    appendChild(child) {
      this.children.push(child);
    },
    removeChild(child) {
      this.children = this.children.filter((entry) => entry !== child);
    },
    getAttribute() {
      return null;
    },
    setAttribute() {},
    querySelectorAll() {
      return [];
    },
    get firstElementChild() {
      return this.children[0];
    },
    get childElementCount() {
      return this.children.length;
    },
  });
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, makeElement());
      return elements.get(id);
    },
    createElement() {
      return makeElement();
    },
    querySelectorAll() {
      return [];
    },
  };
  const window = {
    addEventListener(_type, callback) {
      listeners.push(callback);
    },
  };
  const requests = [];
  const vscode = { postMessage(message) { requests.push(message); } };
  return {
    document,
    window,
    vscode,
    requests,
    respond(request, data) {
      for (const callback of listeners) {
        callback({ data: { type: 'workbench_response', request_id: request.request_id, ok: true, data } });
      }
    },
    messages: document.getElementById("messages"),
    emit(event) {
      for (const callback of listeners) {
        callback({ data: { type: "workbench_event", event } });
      }
    },
  };
}

function boot() {
  const html = createAgentWorkbenchHtml();
  const match = html.match(/<script nonce="codingmatrix-agent-host">([\s\S]*?)<\/script>/);
  assert.ok(match, "workbench html should embed the workbench script");
  const harness = createHarness();
  const factory = new Function("acquireVsCodeApi", "document", "window", match[1]);
  factory(() => harness.vscode, harness.document, harness.window);
  return harness;
}

test("drops heartbeat frames from the workbench log", () => {
  const harness = boot();
  harness.emit({ type: "heartbeat" });
  assert.equal(harness.messages.childElementCount, 0);
});

test("unwraps passthrough thinking frames and wrapped progress frames", () => {
  const harness = boot();
  harness.emit({ type: "thinking", agent: "architect", message: "正在分析需求" });
  harness.emit({ type: "progress", data: { step: "generating", percentage: 40 } });
  harness.emit({ type: "file", path: "src/index.html" });
  harness.emit({ type: "step_detail", description: "校验依赖图" });
  assert.deepEqual(
    harness.messages.children.map((child) => child.textContent),
    [
      "thinking：正在分析需求",
      "progress：generating",
      "file：src/index.html",
      "step_detail：校验依赖图",
    ],
  );
});

test("caps the workbench log at one hundred entries", () => {
  const harness = boot();
  for (let index = 0; index < 150; index += 1) {
    harness.emit({ type: "log", data: { message: `消息 ${index}` } });
  }
  assert.equal(harness.messages.childElementCount, 100);
  assert.equal(harness.messages.firstElementChild.textContent, "log：消息 50");
  assert.equal(harness.messages.children[99].textContent, "log：消息 149");
});

test("renders backend string role mappings after model refresh", async () => {
  const harness = boot();
  harness.document.getElementById('models-refresh').listeners.click();
  for (const request of harness.requests) {
    harness.respond(request, request.resource === 'model_config'
      ? { roles: { architect: 'qwen3-8b', frontend: 'deepseek-r1' } }
      : {});
  }
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(
    harness.document.getElementById('model-roles').children.map(row => row.children[1].textContent),
    ['qwen3-8b', 'deepseek-r1'],
  );
});

test("does not duplicate the fix prefix in learning stats", async () => {
  const harness = boot();
  harness.document.getElementById('learning-refresh').listeners.click();
  const payload = {
    learned_patterns: 2,
    total_fixes_recorded: 3,
    total_sessions: 0,
    overall_success_rate: 0,
    top_errors: [
      { error_type: 'validation_error', error_message: 'error1', frequency: 5, success_rate: 1, fix_description: '修复: error1' },
      { error_type: 'validation_error', error_message: 'error2', frequency: 1, success_rate: 0, fix_description: '修复语法错误（检查括号）' },
    ],
  };
  for (const request of harness.requests) harness.respond(request, payload);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(
    harness.document.getElementById('learning-errors').children.map(item => item.children[1].textContent),
    [
      'error1 · 频次 5 · 成功率 100.0% · 修复：error1',
      'error2 · 频次 1 · 成功率 0.0% · 修复：语法错误（检查括号）',
    ],
  );
});
