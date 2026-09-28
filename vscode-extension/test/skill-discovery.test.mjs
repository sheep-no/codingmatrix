import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { discoverWorkspaceSkills } from "../dist/skill-discovery.js";

async function createRoot(prefix) {
  const parent = await mkdtemp(join(tmpdir(), `codingmatrix-skill-${prefix}-`));
  const root = join(parent, "ws");
  await mkdir(root, { recursive: true });
  return { parent, root };
}

async function writeSkill(root, relative, content) {
  const path = join(root, relative);
  await mkdir(join(path, ".."), { recursive: true });
  await writeFile(path, content, "utf8");
}

test("discovers SKILL.md from all three roots with namespaced names", async () => {
  const { parent, root } = await createRoot("roots");
  try {
    await writeSkill(root, ".claude/skills/foo/SKILL.md", "claude body");
    await writeSkill(root, "skills/bar/SKILL.md", "skills body");
    await writeSkill(root, "data/custom_skills/note.md", "note body");

    const discovered = await discoverWorkspaceSkills(root);

    assert.deepEqual(Object.keys(discovered).sort(), [
      "workspace:ws:bar",
      "workspace:ws:foo",
      "workspace:ws:note",
    ]);
    assert.equal(discovered["workspace:ws:foo"].content, "claude body");
    assert.equal(
      discovered["workspace:ws:foo"].path,
      ".claude/skills/foo/SKILL.md",
    );
    assert.equal(discovered["workspace:ws:bar"].content, "skills body");
    assert.equal(discovered["workspace:ws:bar"].path, "skills/bar/SKILL.md");
    assert.equal(discovered["workspace:ws:note"].content, "note body");
    assert.equal(
      discovered["workspace:ws:note"].path,
      "data/custom_skills/note.md",
    );
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("only data/custom_skills accepts plain markdown", async () => {
  const { parent, root } = await createRoot("markdown");
  try {
    await writeSkill(root, ".claude/skills/readme.md", "skip me");
    await writeSkill(root, "skills/other.md", "skip me too");
    await writeSkill(root, "data/custom_skills/ok.md", "keep me");

    const discovered = await discoverWorkspaceSkills(root);

    assert.deepEqual(Object.keys(discovered), ["workspace:ws:ok"]);
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("keeps nested skill paths under the namespace", async () => {
  const { parent, root } = await createRoot("nested");
  try {
    await writeSkill(root, "data/custom_skills/sub/deep/SKILL.md", "deep body");

    const discovered = await discoverWorkspaceSkills(root);

    assert.deepEqual(Object.keys(discovered), ["workspace:ws:sub/deep"]);
    assert.equal(
      discovered["workspace:ws:sub/deep"].path,
      "data/custom_skills/sub/deep/SKILL.md",
    );
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("skips skills above the size limit", async () => {
  const { parent, root } = await createRoot("size");
  try {
    await writeSkill(root, "skills/small/SKILL.md", "ok");
    await writeSkill(
      root,
      "skills/huge/SKILL.md",
      "x".repeat(100 * 1024 + 1),
    );

    const discovered = await discoverWorkspaceSkills(root);

    assert.deepEqual(Object.keys(discovered), ["workspace:ws:small"]);
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("returns an empty map when no skill directories exist", async () => {
  const { parent, root } = await createRoot("empty");
  try {
    const discovered = await discoverWorkspaceSkills(root);

    assert.deepEqual(discovered, {});
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});

test("namespaces each workspace folder separately", async () => {
  const { parent, root } = await createRoot("multi");
  try {
    const alpha = join(root, "alpha");
    const beta = join(root, "beta");
    await writeSkill(alpha, "skills/a/SKILL.md", "alpha body");
    await writeSkill(beta, "skills/a/SKILL.md", "beta body");

    const discovered = await discoverWorkspaceSkills([
      { name: "alpha", path: alpha },
      { name: "beta", path: beta },
    ]);

    assert.deepEqual(Object.keys(discovered).sort(), [
      "workspace:alpha:a",
      "workspace:beta:a",
    ]);
    assert.equal(discovered["workspace:alpha:a"].content, "alpha body");
    assert.equal(discovered["workspace:beta:a"].content, "beta body");
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
});
