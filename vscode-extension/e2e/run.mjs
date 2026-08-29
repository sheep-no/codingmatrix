import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const globalNodeModules = resolve(dirname(process.execPath), "..", "lib", "node_modules");
const { runTests } = await import(pathToFileURL(
  join(globalNodeModules, "@vscode", "test-electron", "out", "index.js"),
).href);

const exitCode = await runTests({
  extensionDevelopmentPath: extensionRoot,
  extensionTestsPath: join(extensionRoot, "e2e", "suite.mjs"),
  launchArgs: [join(extensionRoot, "e2e", "fixtures")],
});
process.exitCode = exitCode;
