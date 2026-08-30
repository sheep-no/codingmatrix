import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const globalNodeModules = resolve(dirname(process.execPath), "..", "lib", "node_modules");
const { runTests } = await import(pathToFileURL(
  join(globalNodeModules, "@vscode", "test-electron", "out", "index.js"),
).href);

const userDataDir = mkdtempSync(join(tmpdir(), "codingmatrix-vscode-e2e-"));
const localNoProxy = ["127.0.0.1", "localhost", "::1"];
for (const variable of ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]) {
  delete process.env[variable];
}
for (const variable of ["NO_PROXY", "no_proxy"]) {
  const existing = process.env[variable]?.split(",").filter(Boolean) ?? [];
  process.env[variable] = [...new Set([...existing, ...localNoProxy])].join(",");
}
try {
  const exitCode = await runTests({
    extensionDevelopmentPath: extensionRoot,
    extensionTestsPath: join(extensionRoot, "e2e", "suite.mjs"),
    launchArgs: [
      join(extensionRoot, "e2e", "fixtures"),
      `--user-data-dir=${userDataDir}`,
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--proxy-server=direct://",
      "--proxy-bypass-list=*",
    ],
  });
  process.exitCode = exitCode;
} finally {
  rmSync(userDataDir, { recursive: true, force: true });
}
