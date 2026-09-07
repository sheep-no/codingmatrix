import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  WorkspaceAuthorization,
  WorkspaceAuthorizationError,
} from "../dist/workspace-authorization.js";

test("authorizes and resolves paths inside one workspace", async () => {
  const authorization = new WorkspaceAuthorization(async (path) => path);
  await authorization.grant("workspace-1", "/projects/demo");

  assert.equal(await authorization.resolve("workspace-1", "tests/unit"), "/projects/demo/tests/unit");
  assert.equal(authorization.isAuthorized("workspace-1"), true);
});

test("supports independent multi-workspace authorization", async () => {
  const authorization = new WorkspaceAuthorization(async (path) => path);
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
  const authorization = new WorkspaceAuthorization(async (path) => path);
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

test("uses the filesystem realpath implementation by default", async () => {
  const parent = await mkdtemp(join(tmpdir(), "codingmatrix-workspace-auth-"));
  const root = join(parent, "workspace");
  const outside = join(parent, "outside");
  await Promise.all([mkdir(root), mkdir(outside)]);
  try {
    await symlink(outside, join(root, "linked"));
    const authorization = new WorkspaceAuthorization();
    await authorization.grant("workspace-1", root);
    await assert.rejects(
      authorization.resolve("workspace-1", "linked"),
      (error) => error instanceof WorkspaceAuthorizationError && error.code === "path_outside_workspace",
    );
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("rejects a missing write target reached through a dangling symlink", async () => {
  const parent = await mkdtemp(join(tmpdir(), "codingmatrix-workspace-auth-"));
  const root = join(parent, "workspace");
  await mkdir(root);
  try {
    await symlink(join(parent, "outside", "created.txt"), join(root, "linked.txt"));
    const authorization = new WorkspaceAuthorization();
    await authorization.grant("workspace-1", root);
    await assert.rejects(
      authorization.resolve("workspace-1", "linked.txt", { allowMissingLeaf: true }),
      (error) => error instanceof WorkspaceAuthorizationError && error.code === "path_outside_workspace",
    );
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("revokes workspace authorization", async () => {
  const authorization = new WorkspaceAuthorization(async (path) => path);
  await authorization.grant("workspace-1", "/projects/demo");

  assert.equal(authorization.revoke("workspace-1"), true);
  assert.equal(authorization.isAuthorized("workspace-1"), false);
  assert.equal(authorization.revoke("workspace-1"), false);
});
