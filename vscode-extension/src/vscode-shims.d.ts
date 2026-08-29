declare module "vscode" {
  export interface Disposable { dispose(): void; }
  export interface ExtensionContext { subscriptions: Disposable[]; }
  export interface WorkspaceFolder { name: string; uri: { fsPath: string }; }
  export interface Webview { html: string; onDidReceiveMessage(listener: (message: unknown) => void): Disposable; postMessage(message: unknown): PromiseLike<boolean>; }
  export interface WebviewPanel { webview: Webview; onDidDispose(listener: () => void): Disposable; reveal(viewColumn?: ViewColumn): void; dispose(): void; }
  export interface Window { createWebviewPanel(viewType: string, title: string, showOptions: ViewColumn, options?: { enableScripts?: boolean }): WebviewPanel; }
  export interface Commands { registerCommand(command: string, callback: (...args: unknown[]) => unknown): Disposable; }
  export const window: Window;
  export const commands: Commands;
  export const workspace: { workspaceFolders?: WorkspaceFolder[] };
  export enum ViewColumn { One = 1 }
}
