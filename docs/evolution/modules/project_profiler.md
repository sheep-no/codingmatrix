# ProjectProfiler 演化详档

- 文件：`app/agent/project_profiler.py`（791 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：项目模式识别——分析架构模式/分层/高风险区/测试约定，生成 ProjectProfile（语言指纹），是 TestSelector 的直接数据源

## 职责

1. 多语言规则表 `LANGUAGE_PROFILES`（:67-118）：python/javascript/go/rust/java 五语言的扩展名、测试约定、import 正则
2. `profile`（:243-300）：架构 + 风险区 + 测试约定 + 缓存（mtime 键）
3. `_analyze_architecture`（:339-361）：分层检测/Mixin 检测/聚合导出模块
4. `_analyze_risk_areas`（:483-518）：import 引用次数 → high_dependency；安全/数据库关键字 → security/data_critical
5. `_analyze_test_patterns`（:593-627）：test_location + naming_convention + fixture
6. `detect_project_language`（:744-787）：根 manifest + 扩展名计数定主语言

## 消费方

- `test_selector.py`：直接消费 TestPatterns.test_location/naming_convention + RiskAreas（TS1/TS2/TS4 的数据源）
- `orchestrator_utils.py`：`ProjectProfiler(output_dir, language)` + `detect_project_language`（OU 详档的 `_profile_project`）
- `orchestrator_testing.py`：ProjectProfile 类型
- 测试状态：**零单元测试**（tests/unit 无对应文件）

## 实测确认的 bug

### PP10 [P2] 外部包污染 high_dependency——`_is_project_module` 无点包判定缺失

- 位置：:547-573 `_is_project_module` 只检查绝对路径 + stdlib 前缀
- 实测：构造 5 个文件 `import flask` + `import requests` → `high_dependency=['flask.py','requests.py']`——**外部包被当项目高风险模块**
- 根因：docstring 注释（:538）声称「项目内模块以小写字母开头、不含点」，但实现只排除 stdlib 前缀——无点外部包（flask/requests/numpy）全判为项目模块
- 影响：任何被 5+ 文件 import 的外部包上榜 high_dependency → 下游 TestSelector TS2 把「修改含 flask 的路径」当高风险触发全量测试

### PP8 [P2] 风险关键字超短子串假阳性——`'db'` 命中任意含 db 文本

- 位置：:507/:509 `any(kw in content for kw in SECURITY_KEYWORDS/DATABASE_KEYWORDS)`
- 实测：`src/webapp.py` 内容含 "web dashboard... db query" → `data_critical=['src/webapp.py']`——`'db' in content` 命中任何含 "db" 的文本（web、db_、editor 等全中）
- 影响：data_critical/security_critical 列表被超短子串污染，风险区分析失真；`'db'` 与 `'session'` 同时出现在两组关键字（:179/:191）
- 修复方向：词边界匹配（\b）+ 最小长度阈值 + 按语言框架感知

## 其余发现

### PP5 [P3] `_is_test_dir` 子串匹配假阳性

- 位置：:335 `any(t in dir_name for t in test_dir_names)`
- 实测：`_is_test_dir('/x/contest')` = True、`_is_test_dir('/x/latested')` = True——含 "test" 子串的任意目录判为测试目录
- 另：Go 的 test_dir_names=() 空 → 该函数对 Go 恒 False

### PP15 [P3] `"typescript"` 分支死代码

- 位置：:635-638 `if self.language in ("javascript", "typescript")` + :579 同款
- 实测：`ProjectProfiler(root, language="typescript")` → `__init__` :236 不在 LANGUAGE_PROFILES → 回退 python——**typescript 分支不可达**（传 typescript 已回退）

### PP6 [P3] `_module_to_filename` 多语言映射近似

- 位置：:575-589
- 事实：JS 返回 `{module}.js`（相对路径无 index 处理）、Go 原样返回（无映射）、模块名到路径无精确性——high_dependency 里的文件名与实际路径结构可能不符

### PP3 [P3] `detect_project_language` 单语言选择 + manifest 只查根

- 位置：:756-786
- 事实：manifest 权重 100 只在根目录匹配（monorepo 子包不算）；多语言项目（前后端分离）只能选一个主语言——与 OU10（api/route 启发式）同族

### PP14 [P3] `test_location` 取 os.walk 首个测试目录

- 位置：:612 `patterns.test_location = test_dirs[0]`
- 事实：多测试目录（tests/ + test/）时取 os.walk 顺序首个，确定性不足；下游 TestSelector TS1 依赖该值映射

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| PP10 | P2 | 外部包污染高风险列表，直接误导 TS2 |
| PP8 | P2 | 超短子串污染风险区 |
| PP5 | P3 | 测试目录假阳性 |
| PP15 | P3 | 死分支 |
| PP6 | P3 | 文件名映射近似 |
| PP3 | P3 | 单语言选择 |
| PP14 | P3 | 测试目录确定性 |

## 关联

- TS1/TS2/TS4 [P2]：TestSelector 直接消费本模块产出——**PP10 污染 high_dependency → TS2 高风险判定失真**；PP14 的 test_location → TS1 同目录映射
- 多语言主线（IA2/TS4/AR16）：本模块是唯一有多语言规则的地方，但 `_detect_naming_convention` 的 typescript 分支死（PP15）
- 演化方向（EVOLUTION.md §5.6 支柱 4）：风险区分析应与共享真相源（依赖图）一致——本模块 import 计数与 DG 依赖图重复实现
