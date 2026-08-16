# DependencyRules 深扫（dependency_rules.py，183 行）

> 第九十七轮推演 | 2026-08-16 | 定位：文件类型→依赖类型的映射规则（DEPENDENCY_RULES）与文件路径→类型映射（PATH_TYPE_RULES）+ 扩展名兜底（EXTENSION_TYPE_MAP），dependency_graph 链活跃消费

## 1. 模块定位

纯数据模块：三张静态规则表驱动依赖图的文件类型推断与规则兜底依赖注入。

- `DEPENDENCY_RULES`（:11-53，25 个类型）：文件类型到依赖类型的映射，被 `dependency_graph._auto_add_dependencies` 消费
- `PATH_TYPE_RULES`（:56-161，77 条）：文件路径模式到类型的映射，被 `dependency_graph._infer_file_type` 消费（**仅无 language_adapter 时**）
- `EXTENSION_TYPE_MAP`（:164-183，17 个扩展名）：扩展名兜底，被 `dependency_graph._infer_file_type` 末尾使用

**活跃生产模块**，唯一直接 import 方 dependency_graph.py：

- `dependency_graph.py:24`：import 三张表
- `dependency_graph.py:51-52`：挂为类属性
- `dependency_graph.py:559`：`DEPENDENCY_RULES.get(node.file_type, [])` → `_auto_add_dependencies`（:543-568）按类型全连接加边
- `dependency_graph.py:927-929`：`PATH_TYPE_RULES` 用 `path == pattern or path.startswith(pattern) or path.endswith(pattern)` 匹配
- `dependency_graph.py:939`：`EXTENSION_TYPE_MAP.get(ext, 'utils')` 兜底

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `dependency_graph.py:559` | `_auto_add_dependencies`（活跃：build_from_architecture 第三步） |
| 被消费 | `dependency_graph.py:927/:939` | `_infer_file_type`（仅无 language_adapter 时走 PATH_TYPE_RULES/EXTENSION_TYPE_MAP） |
| 被消费 | `orchestrate_endpoints.py:203` | `DependencyGraph.load()` 无 adapter 加载（:206 用 `file_type=="frontend"` 判语言） |
| 关联 | `adapters/python.py:64`、`adapters/javascript.py:59` | **独立副本的 PATH_TYPE_RULES**（生产主路径 adapter 自带，不消费本模块） |
| 未消费 | `architecture_inspector.py` | 变量名 `dependency_rules` 是架构设计 dict 键，非本模块 import |
| 测试 | `tests/unit/test_dependency_rules.py`（37 用例） | 全部结构断言，零消费语义断言 |

## 2. 深扫发现

### P2 项

- **DR1 [P2] `_infer_file_type` 对嵌套目录全部漏配（实测）**——dependency_graph.py:928 用 `path.startswith(pattern) or path.endswith(pattern)` 匹配，而 `PATH_TYPE_RULES` 的目录模式（`"api/"`/`"services/"`/`"utils/"`）只对**顶层目录或路径尾部**生效：实测 `app/api/users.py`、`backend/services/user_service.py`、`src/utils/helpers.py` **全部落到 EXTENSION_TYPE_MAP → `.py` 不在 map → 兜底 `'utils'`**。对比 python adapter 用 `f"/{pattern}" in f"{file_path}/"`（python.py:268-269）能正确识别嵌套目录（`app/api/users.py`→api）——**同一份规则数据在两个消费方使用不同匹配语义**，dependency_graph 侧的 startswith/endswith 语义使主流嵌套结构（app/、src/、backend/ 前缀）全部漏配。
- **DR2 [P2] `.py` 扩展名缺失 → Python 文件兜底恒 'utils'（实测）**——`EXTENSION_TYPE_MAP`（:164-183）**没有 `.py` 键**，而 Python 是依赖推断的主语言。任何未命中 PATH_TYPE_RULES 的 `.py` 文件（顶层 `main.py`、`app.py`、以及嵌套目录漏配的 DR1 场景）全部落入 `EXTENSION_TYPE_MAP.get(ext, 'utils')` 的 `'utils'` 兜底。实测 `main.py`→utils、`app/api/users.py`→utils。python adapter 兜底是 `'unknown'`（python.py:299），两处兜底语义不一致，且 `'utils'` 在 DEPENDENCY_RULES 中依赖 `["config","env"]`（:27）——**误判为 utils 的文件会被注入错误的依赖链**。
- **DR3 [P2] 三套 PATH_TYPE_RULES 并存且 `schemas.py` 类型冲突（全库确认）**——本模块（:109 `("schemas.py", "types")`）、python adapter（:112 `("schemas.py", "schema")`）、javascript adapter（:96 `("schemas", "schema")`）各有一份手工复制的规则，**`schemas.py` 被映射为不同类型**（types vs schema），而 DEPENDENCY_RULES 中 `types` 依赖 `["config"]`、`schema` 依赖 `["model","types"]`——同一文件名经不同路径推断后注入的依赖链不同。三份数据无单一来源，升级即漂移（SCT6 双份配置家族，此处三份）。
- **DR4 [P2] `_auto_add_dependencies` 类型全连接爆炸（实测）**——`:559-566` 对无 LLM imports 的文件，按其 file_type 在 DEPENDENCY_RULES 中的依赖类型**全连接所有该类型文件**：实测 2 个 api 文件 + 3 个 service 文件 → `api/a.py` 依赖全部 3 个 service 文件、总边数 6（=2×3）。`test` 类型依赖 `["model","service","api"]`（:48）→ 测试文件连接**所有** model/service/api 文件，O(n×m) 边爆炸。依赖上下文注入（`get_context_for_file`）被无关依赖边污染，多文件项目上下文质量退化。`view`/`controller`/`router`/`api` 四种类型规则相同（:35-38）加重此问题。

### P3 项

- **DR5 [P3] 未知类型兜底 `'utils'` 语义错位（静态确认）**——dependency_graph.py:939 `EXTENSION_TYPE_MAP.get(ext, 'utils')` 把一切未识别文件归为 `'utils'`，而 `'utils'` 在 DEPENDENCY_RULES 中是有明确依赖语义的类型（依赖 config/env），与 python adapter 的 `'unknown'` 兜底不一致。未识别文件被当成工具类注入依赖链，错误语义传播。
- **DR6 [P3] `endswith(pattern)` 后缀宽松匹配误报（实测）**——dependency_graph.py:928 `path.endswith(pattern)` 对文件名模式宽松命中：实测 `my_config.py`→config（:83 `("config.py", "config")`）、`my_utils.py`→utils（:115）。`database_config.py` 因 :73 有专门规则靠前覆盖未受影响，但任意 `xxx_config.py`/`xxx_utils.py` 命名都会被 endswith 误判，属子串匹配家族（PP5/FE1 同族）。
- **DR7 [P3] `view` 系目录规则重叠歧义（静态确认）**——`("views/", "view")`（:129）与 `("src/views/", "frontend_page")`（:145）并存：同一目录名 `views/` 在后端（`views/`→view）与前端（`src/views/`→frontend_page）映射到不同类型，且 `view` 与 `frontend_page` 的依赖链完全不同（view 依赖 service/schema/types，frontend_page 依赖 frontend_component）。路径前缀依赖顺序决定结果，规则设计上无歧义消除。
- **DR8 [P3] 测试 37 用例全结构断言零消费语义（静态确认）**——test_dependency_rules.py 全部断言常量结构（dict/list/引用一致性/无环 DFS），**零用例调用 `_infer_file_type`/`_auto_add_dependencies` 验证实际匹配行为**。DR1（嵌套目录漏配）、DR2（.py 缺失兜底）、DR4（全连接爆炸）全部实测可复现但无任何用例保护；测试用 `dict(PATH_TYPE_RULES)` 转换（:42 等）掩盖了顺序敏感匹配语义。

## 3. 演化方向

规则表是依赖图的「类型语义层」，数据本身结构完整（无环、引用一致），但**消费端匹配语义与数据设计意图脱节**：
- **匹配语义统一（DR1/DR6）**：dependency_graph 的 startswith/endswith 匹配应改为 python adapter 的 `f"/{pattern}" in f"{file_path}/"` 子串目录匹配——一次改动同时修复嵌套目录漏配与 endswith 宽松误报。
- **单一数据源（DR3）**：三套 PATH_TYPE_RULES（dependency_rules.py + python.py + javascript.py）应收敛为一份（§5.6 支柱 1 协议统一），`schemas.py` 类型冲突是已发生的漂移实例。
- **兜底语义（DR2/DR5）**：EXTENSION_TYPE_MAP 补 `.py` 键（映射到合理类型或新增 `'unknown'`），未知类型兜底改为 `'unknown'` 而非 `'utils'`，与 adapter 兜底对齐。
- **全连接改精确（DR4）**：`_auto_add_dependencies` 的类型级全连接应改为基于实际 import 引用（LLM imports 已解析的文件）或至少限制连接数，避免 O(n×m) 边爆炸污染上下文注入。

**修复优先级**：DR1（嵌套目录全漏配，结构缺陷）> DR2（.py 缺失主语言兜底错误）> DR3（三份规则漂移风险）> DR4（全连接边爆炸）> DR6（endswith 误报）> DR5（兜底语义）> DR7（view 歧义）> DR8（测试盲区）。

## 4. 主线关联

- **「同一能力双实现/多实现」主线**：DR3 是本主线在规则数据层的实例——dependency_rules.py / python.py / javascript.py 三份 PATH_TYPE_RULES，与 SCT6（双份模板配置）、SC1（shared_context 依赖图死链 vs dependency_graph 活跃）、GitOperations vs orchestrator_utils 裸 git 同族。生产主路径（带 adapter）实际用 adapter 自带副本，**本模块的 PATH_TYPE_RULES/EXTENSION_TYPE_MAP 只在无 adapter 场景生效**——规则表大部分处于「降级影子」状态。
- **检测/推断端失真家族**：DR1（嵌套目录漏配→utils）、DR2（.py 缺失→utils）与 LD1/LD2（语言检测漏检）、PP8（风险关键字子串误报）、FE1/BE1（file_type 子串假阳性）同族——**file_type 推断是依赖上下文注入与 DEPENDENCY_RULES 的输入，推断错误沿依赖链传播**。
- **「存在≠正确」**：DR4 全连接使规则兜底「产生依赖」但边语义错误——依赖图边数正确增长但内容失真，与 DGV 详档「检测目标与数据矛盾」同属「机制存在但语义未生效」。
- **测试断言强度**：DR8 与 MLP 详档「测试全绿 ≠ 解析正确」同族——37 用例结构断言掩盖消费语义缺陷。

## 5. 测试状态

**结构覆盖充分、语义覆盖为零**——test_dependency_rules.py 37 用例覆盖三张表的结构完整性（dict/list 类型、引用一致性、无环），但**全部不调用消费方**：`_infer_file_type`（嵌套目录/顶层/endswith 边界）、`_auto_add_dependencies`（全连接行为/边数）、`_infer_file_type` 与 python adapter 的一致性对比均无用例。DR1/DR2/DR4/DR6 全部实测可复现但无任何用例保护。规则表是依赖图类型推断与规则兜底注入的唯一输入，其消费语义端到端无回归保护。
