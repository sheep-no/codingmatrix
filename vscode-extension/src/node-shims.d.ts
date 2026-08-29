declare module "node:crypto" {
  export function createHash(algorithm: string): {
    update(value: string, encoding: string): { digest(encoding: string): string };
  };
}

declare module "node:fs/promises" {
  export function readFile(path: string, encoding: "utf8"): Promise<string>;
  export function stat(path: string): Promise<{ isFile(): boolean }>;
  export function writeFile(path: string, content: string, encoding: "utf8"): Promise<void>;
}

declare class Buffer extends Uint8Array {
  static from(value: string, encoding: "utf8"): Buffer;
  static byteLength(value: string, encoding: "utf8"): number;
  readonly byteLength: number;
  subarray(start?: number, end?: number): Buffer;
  toString(encoding: "utf8"): string;
}
