import { lstat as fsLstat, realpath as fsRealpath } from "node:fs/promises";

export interface WorkspaceRoot {
  workspace_id: string;
  root: string;
}

export type RealpathLike = (path: string) => Promise<string>;

export interface ResolveOptions {
  allowMissingLeaf?: boolean;
}

export class WorkspaceAuthorizationError extends Error {
  constructor(
    public readonly code: "invalid_workspace" | "unauthorized_workspace" | "path_outside_workspace",
    message: string,
  ) {
    super(message);
    this.name = "WorkspaceAuthorizationError";
  }
}

function isAbsolutePath(path: string): boolean {
  return path.startsWith("/") || path.startsWith("\\") || /^[A-Za-z]:[\\/]/.test(path);
}

function normalizePath(path: string): string {
  const value = path.replaceAll("\\", "/");
  const prefix = /^[A-Za-z]:/.test(value) ? value.slice(0, 2).toLowerCase() : "";
  const body = prefix ? value.slice(2) : value;
  const segments: string[] = [];
  for (const segment of body.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (segments.length > 0) segments.pop();
      continue;
    }
    segments.push(segment);
  }
  const root = prefix ? `${prefix}/` : "/";
  return segments.length ? `${root}${segments.join("/")}` : root;
}

function containsPath(root: string, candidate: string): boolean {
  return candidate === root || candidate.startsWith(`${root}/`);
}

export class WorkspaceAuthorization {
  private readonly workspaces = new Map<string, WorkspaceRoot>();
  private readonly realpath: RealpathLike;

  constructor(realpath: RealpathLike = fsRealpath) {
    this.realpath = realpath;
  }

  async grant(workspaceId: string, root: string): Promise<WorkspaceRoot> {
    if (!workspaceId.trim() || !isAbsolutePath(root)) {
      throw new WorkspaceAuthorizationError(
        "invalid_workspace",
        "workspace id and absolute root are required",
      );
    }
    const normalizedRoot = normalizePath(root);
    const canonicalRoot = normalizePath(await this.realpath(normalizedRoot));
    if (!isAbsolutePath(canonicalRoot)) {
      throw new WorkspaceAuthorizationError(
        "invalid_workspace",
        "workspace root must resolve to an absolute path",
      );
    }
    const workspace = { workspace_id: workspaceId, root: canonicalRoot };
    this.workspaces.set(workspaceId, workspace);
    return workspace;
  }

  revoke(workspaceId: string): boolean {
    return this.workspaces.delete(workspaceId);
  }

  isAuthorized(workspaceId: string): boolean {
    return this.workspaces.has(workspaceId);
  }

  listAuthorized(): WorkspaceRoot[] {
    return [...this.workspaces.values()].map((workspace) => ({ ...workspace }));
  }

  async resolve(workspaceId: string, relativePath: string, options: ResolveOptions = {}): Promise<string> {
    const workspace = this.workspaces.get(workspaceId);
    if (!workspace) {
      throw new WorkspaceAuthorizationError(
        "unauthorized_workspace",
        `workspace ${workspaceId} is not authorized`,
      );
    }
    if (!relativePath || isAbsolutePath(relativePath)) {
      throw new WorkspaceAuthorizationError(
        "path_outside_workspace",
        "validation paths must be relative to the workspace",
      );
    }
    const candidate = normalizePath(`${workspace.root}/${relativePath}`);
    if (!containsPath(workspace.root, candidate)) {
      throw new WorkspaceAuthorizationError(
        "path_outside_workspace",
        "validation path escapes the workspace",
      );
    }
    const canonicalCandidate = normalizePath(await this.resolveCanonical(candidate, options.allowMissingLeaf === true));
    if (!containsPath(workspace.root, canonicalCandidate)) {
      throw new WorkspaceAuthorizationError(
        "path_outside_workspace",
        "validation path resolves outside the workspace",
      );
    }
    return canonicalCandidate;
  }

  assertResolvedPath(workspaceId: string, path: string): void {
    const workspace = this.workspaces.get(workspaceId);
    if (!workspace) {
      throw new WorkspaceAuthorizationError(
        "unauthorized_workspace",
        `workspace ${workspaceId} is not authorized`,
      );
    }
    const candidate = normalizePath(path);
    if (!isAbsolutePath(candidate) || !containsPath(workspace.root, candidate)) {
      throw new WorkspaceAuthorizationError(
        "path_outside_workspace",
        "validation path resolves outside the workspace",
      );
    }
  }

  private async resolveCanonical(candidate: string, allowMissingLeaf: boolean): Promise<string> {
    try {
      return await this.realpath(candidate);
    } catch (error) {
      if (!allowMissingLeaf || !isFileMissing(error)) throw error;
      try {
        await fsLstat(candidate);
        throw new WorkspaceAuthorizationError(
          "path_outside_workspace",
          "validation path cannot be a dangling symbolic link",
        );
      } catch (lstatError) {
        if (!isFileMissing(lstatError)) throw lstatError;
      }
      const separator = candidate.lastIndexOf("/");
      const parent = candidate.slice(0, separator) || "/";
      const leaf = candidate.slice(separator + 1);
      return `${normalizePath(await this.realpath(parent))}/${leaf}`;
    }
  }
}

function isFileMissing(error: unknown): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === "ENOENT";
}
