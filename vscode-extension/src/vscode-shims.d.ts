declare module "vscode" {
  export interface Disposable { dispose(): void; }
  export interface Memento {
    get<T>(key: string, fallback: T): T;
    update<T>(key: string, value: T): Promise<void>;
  }
  export interface ExtensionContext { subscriptions: Disposable[]; globalState: Memento; }
  export interface FileSystemWatcher extends Disposable {
    onDidCreate(listener: (uri: { fsPath: string }) => void): Disposable;
    onDidChange(listener: (uri: { fsPath: string }) => void): Disposable;
    onDidDelete(listener: (uri: { fsPath: string }) => void): Disposable;
  }
  export interface WorkspaceFolder { name: string; uri: { fsPath: string }; }
  export interface Webview { html: string; onDidReceiveMessage(listener: (message: unknown) => void): Disposable; postMessage(message: unknown): PromiseLike<boolean>; }
  export interface WebviewPanel { webview: Webview; onDidDispose(listener: () => void): Disposable; reveal(viewColumn?: ViewColumn): void; dispose(): void; }
  export interface Window { createWebviewPanel(viewType: string, title: string, showOptions: ViewColumn, options?: { enableScripts?: boolean }): WebviewPanel; }
  export interface Diagnostic {
    message: string;
    severity: number;
    source?: string;
    code?: string | number | { value: string | number; target: Uri };
    range: { start: Position; end: Position };
  }
  export interface Position { line: number; character: number; }
  export interface Uri { fsPath: string; }
  export interface Commands {
    registerCommand(command: string, callback: (...args: unknown[]) => unknown): Disposable;
    executeCommand<T = unknown>(command: string, ...args: unknown[]): Promise<T>;
  }
  export const window: Window;
  export const commands: Commands;
  export const workspace: {
    workspaceFolders?: WorkspaceFolder[];
    getConfiguration(section?: string): { get<T>(key: string, defaultValue?: T): T | undefined };
    createFileSystemWatcher(globPattern: string): FileSystemWatcher;
  };
  export const languages: { getDiagnostics(): Array<[Uri, Diagnostic[]]> };
  export enum ViewColumn { One = 1 }
}
