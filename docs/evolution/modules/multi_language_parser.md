# MultiLanguageParser（已删除）

> 第九十一轮深扫（2026-08-15）| 删除轮次（2026-09-26）| 定位：被 LanguageAdapter 体系取代的多语言依赖解析器

## 结论：整模块删除

本模块生产零引用，被 `app/agent/adapters/language_adapter.py`（`LanguageAdapterRegistry`，消费方含 architect、cross_validator、integrity_validator、dependency_graph、spec_first/traditional/incremental 生成链 5 大消费族）完整取代。MLP9 判定为「被取代型孤儿」，删除意愿高于「未接线型孤儿」。

2026-09-26 按用户确认执行清理：

- 删除 `app/agent/multi_language_parser.py`（392 行）
- 删除 `tests/unit/test_multi_language_parser.py`（597 行）
- 删除 `docs/features/MULTI-LANGUAGE-DEPENDENCY-PARSER.md`
- 移除 `app/agent/capability_registry.py` 中的 `LanguageDependencyParser` 登记条目（零引用模块登记随模块删除一并取消）

生产依赖分析继续由 `app/agent/adapters/language_adapter.py` 与 `app/agent/dependency_graph.py` 承担。

## 历史发现（供删除决策引用，代码已不存在）

深扫确认 MLP1-MLP9 缺陷，记录如下以便追溯「测试全绿 ≠ 解析正确」这一主线：

- **MLP1 [P2]** `_remove_comments_and_strings` 只移除注释、字符串剥离零实现，`string_regex` 定义但从未引用——docstring 内行首 `import` 被误解析为依赖。
- **MLP2 [P2]** Go 第三个 pattern `"\s*([^"]+)\s*"` 匹配任意双引号字符串，字符串常量被误报为依赖。
- **MLP3 [P2]** Go 多行 import `import\s*\((?:[^)]*?)\)` 无捕获组，`findall` 返回整段文本成为垃圾依赖条目。
- **MLP4 [P2]** Java pattern 双捕获组，`next((m for m in match if m))` 取第一个非空组，`import static java.lang.Math.PI` → `'static .java'`。
- **MLP5 [P3]** JS 扩展名补全依赖文件系统 `exists()`，非确定性；`"typescript"` 分支永不触达。
- **MLP6 [P3]** C# `using Path = System.IO.Path` 取别名而非命名空间。
- **MLP7 [P3]** 无锁模块级单例 `get_parser`（JP4 家族）。
- **MLP8 [P3]** 文档宣称 14 种语言实为 13 键；`.R` 扩展名因 `suffix.lower()` 永不可达。
- **MLP9 [P2]** 被 LanguageAdapter 取代的双轨并存未清理（本次删除即其处置）。

其 597 行测试在设计上强度不足（`in` 子集断言漏垃圾条目、`len >= 1` 漏取错组、字符串用例规避行首 import 真实场景），是「弱断言掩盖实现缺陷」的实证。删除后该隐患随实现一并消除。

## 主线关联

- **「存在≠正确」解析端主线**：MLP1 与 JP1（标量穿透）、FD1（检测端失真）同族——解析器语义缺陷通过弱断言测试「合法化」。
- **双轨/并存主线**：MLP9 与 AJP2（json_parser 双入口）、CR1（三套审查三轨契约）同族，本模块是其中最极端的「一套被全量生产消费、一套仅测试消费」。
- **死代码归档**：与 UPL1、SL1、MAR1、SCT5 等「能力未接线」家族的区别是本模块曾有接线意图后被替代，故优先删除。
