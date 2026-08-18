# LanguageAdapter 体系深扫（adapters 子包 1613 行：language_adapter 281 + python 400 + javascript 486 + generic 416 + __init__ 30）

> 第一百零六轮推演 | 2026-08-17 | 定位：语言适配层——解析各语言导入/文件类型/符号定义，供生成链依赖推断使用

## 1. 模块定位

`app/agent/adapters/` 是语言适配层（LanguageAdapter 体系），提供统一接口处理不同编程语言差异：导入语法解析、文件类型推断、包/模块结构规则、符号定义提取。四个实现：

- `language_adapter.py`（281 行）：抽象基类 `LanguageAdapter`（9 个抽象方法）+ `LanguageAdapterRegistry` 注册表（类级全局单例）+ `ImportInfo`/`SymbolDefinition` 数据类
- `python.py`（400 行）：`PythonLanguageAdapter`——仅注册 `.py/.pyw/.pyi`，PYTHON_BUILTINS（79 项）+ COMMON_THIRD_PARTY（50 项）双集合判定项目模块，PATH_TYPE_RULES 60 条路径规则
- `javascript.py`（486 行）：`JavaScriptLanguageAdapter`——仅注册 `.js/.jsx/.ts/.tsx/.mjs/.cjs`，NODE_BUILTINS + COMMON_THIRD_PARTY，PATH_TYPE_RULES 100 条
- `generic.py`（416 行）：`GenericLanguageAdapter`——**所有未知语言的 fallback**，不解析语法，依赖 Architect 的 file_plan 声明（`_file_plan_data` 类级缓存）+ 宽松通用模式猜测

**活跃模块**（多详档引用为「生产正主」——multi_language_parser 详档指出 LanguageAdapter 体系 5 大消费族全量接线）。调用链：

- `spec_first_generate.py:131/:214/:2196`：`get_adapter(detected_language)` 三处（SPFG 详档）
- `traditional_generate.py:157-159`：`get_adapter(detected_language)`（TG 详档）
- `incremental_modify.py:57-61`：`get_adapter(detected_language)`（IM 详档）
- `architect.py:676-682/:823-825`：`detect_language` + `get_adapter` 两处（依赖注入）
- `integrity_validator.py:139-147`：`get_adapter('javascript'/'go'/'java')`——**go/java 未注册，静默落 generic**（IV 详档）
- `dependency_graph.py:181-182`：`set_file_plan_data(file_plan)`——写入 Generic 类级缓存（DG 详档）

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 上游 | `dependency_graph.py:181-182` | `set_file_plan_data` 每次 build 调用 |
| 上游 | `spec_first_generate.py:131/:214/:2196` | 语言检测 → get_adapter |
| 上游 | `integrity_validator.py:139-147` | get_adapter('javascript'/'go'/'java') |
| 下游 | 依赖图 import 解析 / 文件类型推断 / 缺失依赖检测 | parse_imports/resolve_import_to_file/infer_file_type/is_project_module |
| 旁系 | `multi_language_parser.py` | 被取代型孤儿（生产正主即本体系） |

## 2. 深扫发现

### P2 项

- **AD1 [P2] Python `is_project_module` 前缀白名单漏检——项目根包被误判为外部模块（实测）**——python.py:378 `project_prefixes = ['app','src','lib','pkg','internal','core']`，顶层模块名不在白名单即返回 False——实测 `is_project_module('banking_system.models')` 和 `('myapp.core')` 均 False，仅 `app.*` 系 True——**项目根包名不在白名单（banking_system/myapp 等真实项目根名）时，整个项目的内部模块都被判为外部模块 → 依赖边丢失、外部依赖误判**（integrity_validator 详档 IV5「前缀白名单漏检」症状的实现侧根因确认——修复点是 python.py:378 的 project_prefixes 而非白名单外再补名单，正确语义应为「非 stdlib/第三方即项目内」）。
- **AD2 [P2] JS `is_project_module` 无项目前缀白名单——项目内绝对路径导入恒判外部（实测）**——javascript.py:440-462 只认相对导入（`.` 开头）与别名（`@/`、`src/`），**无 python 侧 project_prefixes 等价机制**——实测 `is_project_module('models/user')` False 而 `('./models/user')` True——JS/TS 项目「从根目录导入」的常见写法（`import {User} from 'models/user'`）恒被判为第三方依赖，与 Python 侧行为不对称。
- **AD9 [P2] JS `resolve_import_to_file` 不解析项目内绝对路径——依赖边丢失（实测）**——javascript.py:273-290 只处理相对导入与 `@/`/`src/` 别名，**项目内绝对路径（`models/user`、`services/payment`）返回空候选列表**——实测 `resolve_import_to_file(ImportInfo(module='models/user'), 'app/main.ts')` → `[]`——配合 AD2（判为外部），JS 项目「根导入」写法在依赖图侧既不被识别为项目模块也不被解析到文件，依赖边完全丢失。
- **AD11 [P2] Python 相对导入层级丢失——`from ..x` 解析到当前目录而非回溯上层（实测）**——python.py:178-179 相对导入 `module = module.lstrip('.')` 把 `..models` 剥成 `models`，**丢弃层级信息**，resolve_import_to_file:240-246 基于 `Path(current_file).parent` 直接拼接——实测 `from ..models import X` 在 `app/api/users.py` → 候选为 `app/api/models.py`（应为 `app/models.py`）——**多级相对导入依赖边错配**（`..`/`...` 层级未回溯），且 resolve 时 is_relative 已为 True 无法区分单级/多级。
- **AD12 [P2] Generic `_file_plan_data` 类级共享可变状态——多项目互相污染（全库确认）**——generic.py:87 `_file_plan_data` 是类属性，:416 注册的是**单例实例**（`LanguageAdapterRegistry._adapters["generic"] = GenericLanguageAdapter()`），dependency_graph.py:181-182 每次 build 调 `set_file_plan_data`（:100-104 整体覆写类属性）——**所有 DependencyGraph 实例与全部下游共享同一 Generic 单例与同一 file_plan 缓存**，多项目/并发时后构建者覆盖先构建者，前者的 file_plan 导入/类型推断全部失效（SM1/MCP1 全局单例家族；且 Python/JS 虽为无状态单例无此问题，但 get_adapter 返回同一实例的语义使将来加状态即踩坑）。

### P3 项

- **AD3 [P3] `parse_imports` 逐行正则，多行 import 全漏（实测 AD7）**——python.py:160/javascript.py:160 逐行 `for line in content.split('\n')`，`from x import (a,\n b)`、`import {a,\n b} from 'm'` 跨行括号分组不解析；`from . import utils` 实测 module=''（python.py:172 `[\w.]*` 匹配空串）→ resolve 返回空；行尾注释 `# comment` 未剥离（`from a import b  # 注释` 的 symbols 含注释尾）。
- **AD5 [P3] `_guess_imports` Go 标准库未过滤**——generic.py:206 `stdlib_prefixes = ['std','system','core','posix','win32']`，Go 的 `import "fmt"`/`"strings"`/`"os"` 等标准库不在前缀集 → 被当项目模块进入候选；且每行只匹配第一个模式（:196 break），`#include` 与 `import` 并存行只取一个。
- **AD6 [P3] Python `extract_definitions` 类内方法提为顶层符号**——python.py:304-350 用 `stripped`（去缩进）匹配，类内方法 `def add(self,...)` 被提为顶层函数、嵌套函数同理；多行函数签名截断于第一个 `)`（SE5 同族）；装饰器行/`@property` 不影响但装饰器下定义正常提取。
- **AD8 [P3] `detect_language` 混合语言项目回 generic——全栈项目导入解析退化**——language_adapter.py:248 `dominant_count / total_known > 0.5` 严格大于，Python+JS 均衡的全栈项目（如 5 py + 5 ts）落 generic → 主语言导入解析走 `_guess_imports` 宽松猜测而非精确解析（架构师 file_plan 有 imports 时正常，无则退化）。
- **AD10 [P3] JS `extract_definitions` `export default function` 漏检 + TS 泛型箭头函数**——javascript.py:343 正则 `^(?:export\s+)?(?:async\s+)?function` 中间插 `default ` 时不匹配——`export default function foo(){}` 漏检；:358 箭头函数 `(?:\([^)]*\)|\w+)\s*=>` 不匹配泛型 `<T>(x:T) =>`。
- **AD13 [P3] `get_adapter('go'/'java')` 静默落 generic——调用方误以为专用适配器**——integrity_validator.py:145/:147 调 `LanguageAdapterRegistry.get_adapter('go')`/`('java')`，注册表仅 python/javascript/generic 三适配器（go/java 无实现）→ 静默返回 generic——fallback 设计本身合理但**调用方无任何感知**（依赖 generic 的 file_plan 语义而非 Go/Java 语法解析），若调用方期待专用解析能力则静默降级（EC3/DGV1 静默降级家族）。

## 3. 演化方向

LanguageAdapter 是生成链依赖推断的**入口语法层**（architect 依赖注入 + dependency_graph 边构建 + integrity_validator 校验三端消费），当前缺陷集中在「项目模块判定」与「导入解析精度」：
- **项目模块判定语义统一（AD1/AD2，最高优先）**：`is_project_module` 正确语义应为「非标准库、非第三方即项目内」，当前 Python 用前缀白名单（漏检真实根包名）、JS 无白名单——修复方向是移除/大幅扩展 project_prefixes（Python），JS 增加与 Python 对称的判定（或统一走「排除法」），一处修复同时恢复依赖图与完整性校验两端的项目内模块识别。
- **导入解析精度（AD9/AD11）**：JS `resolve_import_to_file` 增加项目内绝对路径分支（基于已注册根目录映射），Python 相对导入保留层级数（`is_relative` 增加 level 字段或在 resolve 时按 `.` 数量回溯）。
- **全局状态隔离（AD12）**：`_file_plan_data` 从类属性改为实例属性 + DependencyGraph 实例持有独立 adapter（或 set_file_plan_data 返回新实例），消除多项目互相污染。
- **适配器覆盖规划（AD13）**：go/java 是否补专用适配器（integrity_validator 已声称使用），或调用方显式判断返回 generic 并记录。

**修复优先级**：AD1/AD2（项目模块误判，影响依赖图与完整性校验两端）> AD9/AD11（依赖边丢失/错配）> AD12（全局状态污染）> AD3 > AD10 > AD6 > AD8 > AD5 > AD13。

## 4. 主线关联

- **「检测端失真」主线（LD 详档同族）**：`is_project_module` 是「是否为项目模块」的二元判定，AD1 使 Python 真实根包恒判外部、AD2 使 JS 根导入恒判外部——与 language_detector（LD1/LD2 漏检→错误语言）同属生成链入口决策失真，错误判定级联到依赖图（边丢失）→ 完整性校验（IV5）→ 缺失文件补全。
- **「正则解析≠语法解析」主线（SE1/SE4 详档同族）**：三适配器 `extract_definitions`/`parse_imports` 全为逐行正则——SE 详档已建档 JS 类方法不提取，本轮 AD3（多行 import）/AD6（类内方法提为顶层）/AD10（export default 漏检）是同族正则精度缺失的 adapter 侧实例。
- **「全局单例共享状态」家族（SM1/MCP1/EC4 同族）**：AD12 使 Generic 的 file_plan 缓存成为跨项目共享可变全局——与 classification_history 全局单例（EC4）、MCP 单例（MCP1）同族，多项目并发即污染。
- **「静默降级无感知」家族（EC3/DGV1/OA1 同族）**：AD13 的 go/java 落 generic 无任何提示。
- **「已接线 ≠ 正确」主线**：LanguageAdapter 体系是 multi_language_parser 详档「生产正主」，5 大消费族全量接线（接线状态良好），但接线后的解析质量（AD1/AD2/AD9/AD11）决定依赖图质量——接线完整 + 实现缺陷，与 CMP（CMP1 子串假阳性）同属「已接线但解析失真」。

## 5. 测试状态

**近零测试覆盖**——grep `tests/` 中 adapters 相关用例：`LanguageAdapterRegistry`/`PythonLanguageAdapter`/`JavaScriptLanguageAdapter`/`GenericLanguageAdapter` 直接断言几乎没有（对比 multi_language_parser 597 行测试——其测试全绿的正是被本体系取代的旧实现，而本体系本身无直接测试）。AD1/AD2/AD9/AD11 四个 P2 项均实测可一次调用复现，但无任何用例保护——「生产正主无测试、被取代者测试全绿」是本模块测试状态最突出特征（multi_language_parser 详档「测试全绿 ≠ 解析正确」的反向印证）。
