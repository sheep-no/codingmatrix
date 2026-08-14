# ConsistencyChecker 深扫（consistency_checker.py，208 行）

> 第八十一轮推演 | 2026-08-13 | 定位：简化版一致性检查器——OpenAPI schema 漂移 / 导出函数签名变化 / 配置文件被修改，「只记录不阻断」

## 1. 模块定位

docstring 声明的使用场景：「增量修改后确认旧行为没被破坏」「文件生成后快速验证」（:11-12）。三个检查维度：函数签名漂移、配置文件漂移、OpenAPI schema 漂移。产出 SchemaDrift 列表 + get_drift_report 文本报告。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | **无生产消费方（孤儿）** | app/ 全目录零 import（rg 仅 tests 引用）；health.py:138 的 `check_all()` 是 services/health_checker.py 的 HealthChecker（独立类，:25），与 ConsistencyChecker 无关 |
| 测试 | tests/unit/test_consistency_checker.py（57 行） | 3 用例：无原始目录跳过 / 签名变更检出 / 无变更 |

## 2. 深扫发现

### P2 项

- **CC1 生产代码零消费方（孤儿模块）**——docstring 声称的「增量修改后确认旧行为没被破坏」「文件生成后快速验证」两个场景**全链路零接线**：增量修改（incremental_modify.py）、文件生成（orchestrator_files.py/spec_first）均无任何 import ConsistencyChecker 的代码。模块存在、实现完整、有测试，但生产从未被调用——**「能力未接线」家族最新成员**（UPL1/SL1/SHS1 同类），且它面向的是最痛的「增量修改回归确认」场景（IM1 每次简单变更都会破坏旧行为，此检查器恰是解药却从未接线）。

### P3 项

- **CC2 签名比较只比参数名——默认值/类型注解/装饰器变化全漏检（实测）**——`:102-103` 只取 `[arg.arg for arg in node.args.args]`（参数名列表）：`def foo(a, b)` → `def foo(a, b=1)`（默认值变化，实测 drift 空）、`def foo(a: int, b)` → `def foo(a: str, b)`（类型注解变化）**都不报**；装饰器（如 FastAPI `@app.get("/x")` 路由元数据）完全不在比较范围——「导出函数签名变化」实际只覆盖参数名增减，签名语义的多数变化漏检。
- **CC3 单向比较：只查删除不回查新增（实测）**——`_check_signature_drift` 只遍历 `original_signatures`（:72），新增函数不进比较；`_check_config_drift` 只报 `original_deps - new_deps` 删除（:128），新增依赖不报（实测 requirements 加 requests 无 drift）；`_check_openapi_drift` 只报 `original_paths - new_paths` 删除（:169），新增端点不报。一致性检查方向单向——「旧行为没被破坏」的检查正确方向（旧→新删除），但新增变更面完全无覆盖。
- **CC4 config_files 列表虚设：4 个文件只有 requirements.txt 有逻辑（实测）**——`:113 config_files = ['requirements.txt', 'package.json', 'Dockerfile', '.env.example']` 循环内只有 `if config_name == 'requirements.txt'` 分支做依赖比对；package.json/Dockerfile/.env.example **存在时只读文件不比对任何内容**（实测 package.json 依赖版本 1.0→2.0 零 drift）。3/4 的文件检查是空操作——「检查配置文件是否被意外修改」只对 requirements.txt 生效，且只检查依赖删除。
- **CC5 OpenAPI 只比 paths 键集合——method/参数/schema 变化全漏**——`:166-167` 只比较 `original_paths - new_paths`（路径键集合）；同一端点 method 变化（GET→POST）、参数变化、响应 schema 变化**完全不检测**——「OpenAPI schema 是否漂移」实际只检测路径删除。且 `_load_openapi` 的 yaml 分支 import yaml 未捕获 ImportError（:189-190 在 try 内，被 :191 except 兜住转 None，静默丢失 yaml 文件检查）。

## 3. 演化方向

### 3.1 接线到增量修改链路（核心价值）

CC1 是孤儿，但其用途（增量修改回归确认）与 IM1 痛点直接对应——IncrementalModify 每次简单变更/降级重试都可能破坏旧行为，此检查器是现成的回归确认工具。接线点候选：incremental_modify 修改完成后、orchestrator_files 文件生成后调用 `check_all(original_dir)` 收集 drift 并入产物报告。这使「只记录不阻断」的检查器从孤儿变成增量链路的正式 Gate（§5.6 支柱 2 验证端补充）。

### 3.2 检查深度补齐

若接线：CC2 补类型注解/默认值/装饰器到签名比较（AST 全信息而非仅参数名）；CC3 补新增方向（函数/依赖/端点新增都记录，severity info）；CC4 为 package.json/Dockerfile/.env.example 补实际比对逻辑（版本/内容 diff）；CC5 补 method/参数级比较。这些是「检查器可用性」条件——当前漏检面使即便接线也会漏报真实回归。

## 4. 主线关联

- **「能力未接线」家族再例**：CC1 与 UPL1（用户偏好）、SL1（Q-Learning）、FPC1（修复模式复用）、SHS1（阴影扫描）同类——模块完整但生产零消费，且 CC 是其中唯一面向「回归确认」的组件，与 IM1（增量破坏旧行为）构成「有解药未用」的对照
- **检查器虚设家族**：CC4（4 文件只有 1 文件有逻辑）+ CC5（paths 键集合 = 部分检查）与 RL1（openapi 一致性检查空操作）、AC7（声明不产出）同族——检查器存在但检查深度不足或空操作
- **单向检查**：CC3 与 IV1（缺失模块不进 missing_files）、CV4（前端 API 检查空操作）同族——只查删除/单向面，新增方向无覆盖

## 5. 测试状态

test_consistency_checker.py 3 用例覆盖了「无原始目录/签名变更检出/无变更」三个正路径，但**全部断言只查 `len(drifts) > 0` 或 `== 0`**——签名变更用例（:39-43）只验证检出存在，未验证 old_value/new_value 内容；CC2 漏检面（默认值/类型/装饰器）、CC3 单向、CC4 空操作、CC5 paths 级局限**全部零覆盖**——测试通过恰恰掩盖了检查器的漏检能力。
