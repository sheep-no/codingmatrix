# 多语言依赖解析器

> 最后核对：2026-09-03
> 状态：独立实现和单元测试活跃；Agent 生产依赖图未接入

## 当前状态

`app/agent/multi_language_parser.py` 提供基于扩展名和正则表达式的静态 import 解析。当前只有 `tests/unit/test_multi_language_parser.py` 直接引用该模块。

生产依赖分析由 `app/agent/dependency_graph.py` 自行完成。该实现解析 Python、JavaScript、TypeScript、JSX、TSX 和 Vue，并结合 `app/agent/shadow_scanner.py` 扫描动态或隐式依赖。生产代码未导入 `LanguageDependencyParser`。

## 支持范围

支持范围以 `LanguageDependencyParser.LANGUAGE_PATTERNS` 为准：

| 语言键 | 扩展名 |
| --- | --- |
| `python` | `.py`、`.pyw`、`.pyx` |
| `javascript` | `.js`、`.jsx`、`.ts`、`.tsx`、`.mjs`、`.cjs` |
| `java` | `.java`、`.groovy` |
| `go` | `.go` |
| `rust` | `.rs` |
| `cpp` | `.c`、`.cpp`、`.cc`、`.cxx`、`.h`、`.hpp`、`.hxx` |
| `ruby` | `.rb`、`.rbw`、`.gemspec` |
| `php` | `.php` |
| `swift` | `.swift` |
| `kotlin` | `.kt`、`.kts` |
| `csharp` | `.cs` |
| `scala` | `.scala` |
| `r` | `.R`、`.r` |

TypeScript 与 JavaScript 共用 `javascript` 语言键。代码中的 `_normalize_import` 包含 `typescript` 分支，但语言检测不会返回该键。

## API

### `detect_language(filepath)`

根据文件后缀返回语言键，无法识别时返回 `None`。

### `parse_imports(filepath, content)`

解析文本并返回标准化依赖路径集合。标准化示例：

- Python：`package.module` 转为 `package/module.py`
- Java：`com.example.Type` 转为 `com/example/Type.java`
- Rust：`crate::module` 转为 `crate/module.rs`
- PHP：命名空间分隔符转为路径并追加 `.php`
- JavaScript：相对导入尝试解析本地扩展，默认追加 `.js`

### `parse_file(filepath)`

以 UTF-8 读取文件，读取和解析异常会记录日志并返回空集合。

### `get_language_stats(files)`

按可识别语言统计文件数量。

### `get_parser()`

返回进程级解析器单例，正则在实例初始化时预编译。

## 使用示例

```python
from app.agent.multi_language_parser import get_parser

parser = get_parser()
language = parser.detect_language("src/app.ts")
imports = parser.parse_imports(
    "src/app.ts",
    "import { createApp } from 'vue'",
)
```

## 实现限制

- 解析依赖正则匹配，无法提供 AST 级语义、条件编译或别名解析。
- `_remove_comments_and_strings` 当前移除注释并保留字符串，以便匹配字符串形式的模块名。
- Go 多行 import、Rust 组合式 `use`、宏生成依赖和动态表达式存在正则覆盖边界。
- 标准化结果是候选路径，不能直接证明文件存在。
- 原文档中的批量项目解析、缓存、并行更新、传递依赖和影响分析示例属于组合设想；该类自身未实现这些方法。

## 生产接入边界

接入 `DependencyGraph` 需要完成三项工作：统一模块名到项目文件的解析规则、保留现有 shadow dependency 结果、为现有 Python 与 JS/Vue 行为建立回归测试。接入完成前，业务文档应以 `dependency_graph.py` 的实际解析范围描述生产能力。

## 代码索引

- `app/agent/multi_language_parser.py`：独立解析器
- `tests/unit/test_multi_language_parser.py`：直接测试
- `app/agent/dependency_graph.py`：当前生产依赖图
- `app/agent/shadow_scanner.py`：当前隐式依赖扫描
