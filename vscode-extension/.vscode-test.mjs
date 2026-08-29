export default {
  files: "e2e/**/*.test.mjs",
  extensionDevelopmentPath: new URL(".", import.meta.url).pathname,
  workspaceFolder: new URL("./e2e/fixtures", import.meta.url).pathname,
  version: "stable",
};
