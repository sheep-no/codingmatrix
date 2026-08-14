# TestSelector 演化详档

- 文件：`app/agent/test_selector.py`（215 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：智能测试选择——基于「同目录 → 高依赖 → 冒烟」三层策略，从全量测试中选出「最小但充分」的测试集，供 OrchestratorTesting 执行

## 职责

`select_tests`（:24-72）串行执行三层：

1. `_select_same_directory_tests`（:74-107）：修改文件目录 → 映射到测试目录 → 找同目录测试
2. `_select_high_dependency_tests`（:109-144）：命中高风险模块 → rglob 全选测试
3. `_select_smoke_tests`（:146-187）：名称含 smoke/core/basic 关键字的测试，最多 10 个，不足 5 个时补足前几个
4. 空结果回退全量（:59-62）

## 消费方

- `orchestrator_testing.py:116-117`：`TestSelector(project_root)` → 已被 **OT16 [P2]** 拦截（无参构造 TypeError 恒失败）——**select_tests 从未被执行过**

## 实测确认的 bug

### TS1 [P2] 同目录层映射错位——修改源码文件恒选不到测试

- 位置：:94 `test_path = os.path.join(test_dir, file_dir)`
- 实测：修改 `src/foo.py` → 映射到 `tests/src/`（目录不存在）→ 空。测试实际在 `tests/test_foo.py`，但映射逻辑把整个修改文件目录拼到 test_location 后面，未做 src→tests 前缀替换、未做扁平命名（test_foo.py ↔ foo.py）匹配
- 影响：第一层对绝大多数真实项目（源码在 src/app/lib 下、测试在 tests 下）恒空——只有修改文件恰好位于 test_location 目录下时才可能命中

### TS6 [P2] 「最小充分集」从未实现——三层结果恒≈全量

- 位置：:179-185 冒烟补足 + :59-62 空回退 + :137 高依赖 rglob
- 实测（tests 目录含 3 个测试文件）：
  - 修改 `src/foo.py`（无任何依赖）→ 结果 `['test_smoke.py','test_auth.py','test_foo.py']` = 全量
  - 修改 `src/auth.py`（明确 high_dependency）→ 结果同全量
  - 修改测试文件本身 → 结果同全量
- 根因（三层各自失效叠加）：
  - 同目录层因 TS1 恒空
  - 冒烟层 :179-185 「不足 5 个就补前几个」——测试集 ≤5 个时把全量当冒烟；即便 >5 个也常补足到 5
  - 高依赖层 :137 一旦命中就 `rglob` 全部测试（非「相关」测试）
  - :59-62 兜底再全量
- 影响：**智能测试选择是装饰性的**——「最小充分集」从未生效，无论输入什么，输出几乎总是全量。与 OT16（构造失败）+ IA3（无影响传播）构成测试选择能力三连失效

### TS2 [P2] 高风险命中 = 全选，且子串匹配假阳性

- 位置：:121-142
- 实测：修改 `src/auth.py` → `any(risk in f for risk in risk_files)` 命中 → rglob 全选全部测试（不是「选择 auth 相关测试」）
- 且 `risk in f` 是**子串匹配**——risk 含 `auth` 时 `authentication.py`、`my_author.py` 全命中；无路径边界
- 影响：高风险模块修改触发的是全量测试（与回退等价），第二层也退化为全量

## 其余发现

### TS4 [P3] naming_convention 只认 Python 两种

- 位置：:99-102/:136-139/:166-169/:207-210
- 事实：只有 `test_*.py` / `*_test.py` 两种分支，JS（`*.test.js`）、Go（`*_test.go`）等命名全不识别 → 多语言项目测试全漏。与多语言主线同源

### TS5 [P3] 冒烟关键字硬编码英文

- 位置：:156 `['smoke','core','basic','critical','essential']`
- 影响：文件名含中文/其他命名约定时冒烟层永远空，只能靠补足逻辑兜底

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| TS6 | P2 | 最小充分集核心承诺失效 |
| TS1 | P2 | 同目录映射错位，第一层恒空 |
| TS2 | P2 | 高风险层退化为全选 |
| TS4 | P3 | 多语言命名不识别 |
| TS5 | P3 | 冒烟关键字不可配置 |

## 关联

- OT16 [P2]：消费方构造失败，select_tests 从未执行——**先修 OT16**
- IA3 [P2]：无影响传播 → TestSelector 没有「受影响文件」输入，第一/二层缺数据
- TR/FD 链：最终测试集交 TestRunner 执行，选择失效 = 每次都跑全量（等同无智能选择）
- 测试状态：test_selector **零单元测试**（tests/unit 无对应文件）
