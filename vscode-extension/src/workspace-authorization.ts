export interface WorkspaceRoot {
  workspace_id: string;
  root: string;
}

export type RealpathLike = (path: string) => Promise<string>;

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

  constructor(realpath: RealpathLike = async (path) => path) {
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

  async resolve(workspaceId: string, relativePath: string): Promise<string> {
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
    const canonicalCandidate = normalizePath(await this.realpath(candidate));
    if (!containsPath(workspace.root, canonicalCandidate)) {
      throw new WorkspaceAuthorizationError(
        "path_outside_workspace",
        "validation path resolves outside the workspace",
      );
    }
    return canonicalCandidate;
  }
}
