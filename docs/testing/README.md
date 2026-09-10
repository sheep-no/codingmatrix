# 测试文档

> 最后核对：2026-09-10

- [测试指南](TESTING.md)：pytest、Vitest、Playwright、VS Code Extension Host 与 Flutter 的当前目录、命令、配置和验收记录。
- [文档索引](../README.md)：返回项目文档主目录。

当前自动化测试分布在 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`src/**/*.test.js`、`vscode-extension/test/`、`vscode-extension/e2e/` 和 `flutter_client/test/`。测试结果受 Redis、数据库、浏览器、VS Code Electron、Flutter SDK、模型供应商和测试账号等运行条件影响，引用数字时应同时保留测试范围与日期。
