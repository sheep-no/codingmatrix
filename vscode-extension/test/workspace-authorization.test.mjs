import assert from "node:assert/strict";
import test from "node:test";
import {
  WorkspaceAuthorization,
  WorkspaceAuthorizationError,
} from "../dist/workspace-authorization.js";

test("authorizes and resolves paths inside one workspace", async () => {
  const authorization = new WorkspaceAuthorization();
  await authorization.grant("workspace-1", "/projects/demo");

  assert.equal(await authorization.resolve("workspace-1", "tests/unit"), "/projects/demo/tests/unit");
  assert.equal(authorization.isAuthorized("workspace-1"), true);
});

test("supports independent multi-workspace authorization", async () => {
  const authorization = new WorkspaceAuthorization();
  await authorization.grant("workspace-1", "/projects/one");
  await authorization.grant("workspace-2", "/projects/two");

  assert.deepEqual(authorization.listAuthorized(), [
    { workspace_id: "workspace-1", root: "/projects/one" },
    { workspace_id: "workspace-2", root: "/projects/two" },
  ]);
  await assert.rejects(
    authorization.resolve("workspace-1", "../two/file.txt"),
    (error) => error instanceof WorkspaceAuthorizationError && error.code === "path_outside_workspace",
  );
});

test("rejects absolute paths and unknown workspaces", async () => {
  const authorization = new WorkspaceAuthorization();
  await authorization.grant("workspace-1", "/projects/demo");

  await assert.rejects(authorization.resolve("workspace-1", "/etc/hosts"));
  await assert.rejects(
    authorization.resolve("unknown", "README.md"),
    (error) => error instanceof WorkspaceAuthorizationError && error.code === "unauthorized_workspace",
  );
});

test("rejects symlink targets resolved outside the workspace", async () => {
  const authorization = new WorkspaceAuthorization(async (path) =>
    path.endsWith("/linked") ? "/outside/secret" : path,
  );
  await authorization.grant("workspace-1", "/projects/demo");

  await assert.rejects(
    authorization.resolve("workspace-1", "linked"),
    (error) => error instanceof WorkspaceAuthorizationError && error.code === "path_outside_workspace",
  );
});

test("revokes workspace authorization", async () => {
  const authorization = new WorkspaceAuthorization();
  await authorization.grant("workspace-1", "/projects/demo");

  assert.equal(authorization.revoke("workspace-1"), true);
  assert.equal(authorization.isAuthorized("workspace-1"), false);
  assert.equal(authorization.revoke("workspace-1"), false);
});
