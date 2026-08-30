declare module "node:crypto" {
  export function createHash(algorithm: string): {
    update(value: string, encoding: string): { digest(encoding: string): string };
  };
}

declare module "node:fs/promises" {
  export function readFile(path: string, encoding: "utf8"): Promise<string>;
  export function readdir(path: string, options: { withFileTypes: true }): Promise<Array<{
    name: string;
    isDirectory(): boolean;
  }>>;
  export function stat(path: string): Promise<{ isFile(): boolean }>;
  export function writeFile(path: string, content: string, encoding: "utf8"): Promise<void>;
}

declare module "node:path" {
  export function join(...parts: string[]): string;
  export function relative(from: string, to: string): string;
}

declare module "node:child_process" {
  export function spawn(command: string, args: string[], options: { cwd: string; shell: false }): {
    stdout?: { on(event: "data", listener: (chunk: string | Uint8Array) => void): void };
    stderr?: { on(event: "data", listener: (chunk: string | Uint8Array) => void): void };
    once(event: "error" | "close", listener: (value?: unknown) => void): void;
    kill(signal?: string): boolean;
  };
}

declare module "node:http" {
  export function request(url: URL, options: { method: string; headers?: Record<string, string> }, callback: (response: {
    statusCode?: number;
    on(event: "data", listener: (chunk: Uint8Array) => void): void;
    on(event: "end", listener: () => void): void;
    on(event: "error", listener: (error: unknown) => void): void;
  }) => void): {
    on(event: "error", listener: (error: unknown) => void): void;
    write(body: string): void;
    end(): void;
    destroy(): void;
  };
}

declare module "node:https" {
  export { request } from "node:http";
}

declare class Buffer extends Uint8Array {
  static from(value: string, encoding: "utf8"): Buffer;
  static byteLength(value: string, encoding: "utf8"): number;
  readonly byteLength: number;
  subarray(start?: number, end?: number): Buffer;
  toString(encoding: "utf8"): string;
}
