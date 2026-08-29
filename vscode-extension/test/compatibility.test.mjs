import assert from "node:assert/strict";
import test from "node:test";
import {
  assertCompatible,
  CompatibilityError,
} from "../dist/compatibility.js";

test("accepts a compatible schema and plugin version range", () => {
  assert.doesNotThrow(() => assertCompatible({
    schema_versions: [1, 2],
    plugin_version: { min: "0.1.0", max: "0.2.0" },
  }));
});

test("rejects a cloud without the supported schema version", () => {
  assert.throws(
    () => assertCompatible({ schema_versions: [2] }),
    (error) => error instanceof CompatibilityError && error.code === "unsupported_schema_version",
  );
});

test("rejects a plugin version outside the cloud range", () => {
  assert.throws(
    () => assertCompatible({ schema_versions: [1], plugin_version: { min: "0.2.0" } }),
    (error) => error instanceof CompatibilityError && error.code === "unsupported_plugin_version",
  );
});

test("rejects malformed handshake versions", () => {
  assert.throws(
    () => assertCompatible({ schema_versions: [1], plugin_version: { max: "latest" } }),
    (error) => error instanceof CompatibilityError && error.code === "invalid_handshake",
  );
});
