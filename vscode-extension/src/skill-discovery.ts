import { readFile, readdir } from "node:fs/promises";
import { join, relative } from "node:path";

export type DiscoveredSkill = {
  name: string;
  path: string;
  content: string;
};

export type WorkspaceSkillRoot = { name: string; path: string };

const MAX_SKILL_BYTES = 100 * 1024;

export async function discoverWorkspaceSkills(workspaceRoot: string | WorkspaceSkillRoot[]): Promise<Record<string, DiscoveredSkill>> {
  const folders = typeof workspaceRoot === "string"
    ? [{ name: workspaceRoot.split(/[\\/]/).pop() ?? "workspace", path: workspaceRoot }]
    : workspaceRoot;
  const discovered: Record<string, DiscoveredSkill> = {};
  for (const folder of folders) {
    const roots: Array<[string, boolean]> = [
      [join(folder.path, ".claude", "skills"), false],
      [join(folder.path, "skills"), false],
      [join(folder.path, "data", "custom_skills"), true],
    ];
    for (const [root, acceptMarkdown] of roots) {
      await scanDirectory(root, folder.path, discovered, acceptMarkdown, `workspace:${folder.name}`);
    }
  }
  return discovered;
}

async function scanDirectory(
  directory: string,
  workspaceRoot: string,
  discovered: Record<string, DiscoveredSkill>,
  acceptMarkdown: boolean,
  namespace: string,
): Promise<void> {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (isMissing(error)) return;
    throw error;
  }
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await scanDirectory(path, workspaceRoot, discovered, acceptMarkdown, namespace);
      continue;
    }
    if (entry.name !== "SKILL.md" && !(acceptMarkdown && entry.name.endsWith(".md"))) continue;
    const content = await readFile(path, "utf8");
    if (Buffer.byteLength(content, "utf8") > MAX_SKILL_BYTES) continue;
    const relativePath = relative(workspaceRoot, path).replaceAll("\\", "/");
    const skillPath = relativePath
      .replace(/^\.claude\/skills\//, "")
      .replace(/^skills\//, "")
      .replace(/^data\/custom_skills\//, "")
      .replace(/\/SKILL\.md$/, "")
      .replace(/\.md$/, "");
    const name = `${namespace}:${skillPath}`;
    discovered[name] = { name, path: relativePath, content };
  }
}

function isMissing(error: unknown): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === "ENOENT";
}
