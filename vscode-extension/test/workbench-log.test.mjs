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
    addEventListener() {},
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
  const vscode = { postMessage() {} };
  return {
    document,
    window,
    vscode,
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
