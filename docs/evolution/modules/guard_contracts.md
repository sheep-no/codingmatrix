# guard_contracts.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 守护合约（安全关键文件约束）
> 路径：`app/utils/guard_contracts.py`（286 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

「守护合约——安全关键文件约束规则」——定义核心文件/函数/类/变量的保护规则，Agent 修改代码前必须对照检查。三级严重度：CRITICAL（认证/加密/权限核心，修改需用户确认）、WARNING（影响面大，需说明风险）、NOTICE（记录变更）。规则机器可读（GuardRule dataclass），支持 existence/signature/type_check 三种检查类型。通过 GuardContracts 单例 + 便捷函数（check_file_against_contracts/get_applicable_rules）暴露。

## 2. 依赖链与消费方

**活跃消费（真实接线）**：
- `code_tasks.py:170/232-245`——Step 5 守护合约检查：`contracts.check_file(file_path, content)`（**变更后内容**）遍历 target_files，违规并入 guard_violations 返回结果 dict
- `helpers.py:184-189`（load_guard_contracts，被 helpers.py:196 get_agent_knowledge_base 间接引用——但后者零调用，见 ASK1 详档；guard_contracts 缓存键 _guard_contracts_cache 独立）→ `to_dict()` 注入 Agent 知识库

**零消费**：
- `check_file_against_contracts`（:262-265 便捷函数）——code_tasks.py:170 import 但实际走方法链；零生产调用
- `get_applicable_rules`（:268-280）——零调用
- `GuardRule.allowed_changes` 白名单字段（:25）——定义但检查逻辑（:202-226）从不引用

## 3. 发现

### GC1 [P2] 守护合约 existence 检查无变更前基线——「保护项删除」判定语义失真（全库确认）

- **Bug 代码**：:177-198 `check_file(file_path, content)`——只接收**变更后** content，无变更前快照；:203-212 check_type="existence"：`if pattern not in content: return Violation(描述「保护项可能已被删除」)`。
- **根因**：existence 语义是「变更后文件必须仍包含保护模式」——但无变更前内容，无法证明「删除」。任何变更后文件**本来就不含**某保护项时即误报「可能已被删除」（如 models 文件不含 created_at 字段）。code_tasks.py:243 实际调用传的正是变更后全文（read_text 后传入）——误报必然发生。
- **影响**：守护合约的「保护项被删除」判定是假阳性引擎（TR1/MAR8 家族）；声称「禁止删除」的 CRITICAL 规则（GC-001/GC-003）建立在不可证明的判定上。

### GC2 [P2] 守护合约违规只记录不阻断——CRITICAL「禁止修改」无强制力（DGV1 放行家族）

- **Bug 代码**：code_tasks.py:235-245——守护合约检查后 guard_violations 仅 append 进结果 dict 返回；无任何抛异常/中断修改流程逻辑——即使触发 GC-001（认证核心函数，CRITICAL）违规，修改照常完成落盘。
- **根因**：模块 docstring 声称「CRITICAL 修改需用户确认」「禁止修改或修改签名」——但消费方 code_tasks 把违规当「附注」返回，无阻断机制、无确认流程（与 LLM 提示注入的「建议」同级）。
- **影响**：守护合约是「只报告不拦截」的防护（与 DR2 docker 安全扫描只告警/SCM2 健康失败放行同族）——**防护层全线「违规放行」**；guard_violations 返回后 code_tasks 结果 dict 无任何调用方处理违规语义（retry_count/success 均与违规无关）。

### GC3 [P3] check_type="signature" 实际不检签名——只查函数名存在性（语义错误）

- **Bug 代码**：:214-224——`(def|class)\s+{pattern}\s*[\(:]`——只确认「变更后文件仍有 `def 名字`」——函数从 `def foo(a, b)` 改为 `def foo(a)`（签名变更）仍匹配 `def foo` 前缀 → **漏报签名变更**；与 existence 检查（:203-212）实际等效（都是「内容含某模式」），check_type 双模式无行为差异——「signature」检查名不副实。
- **影响**：GC-001/GC-002/GC-006/GC-007 的 signature 规则全部退化为存在性检查；签名变更（参数增删/顺序变化）静默放行。

### GC4 [P3] 便捷函数 check_file_against_contracts/get_applicable_rules 零消费（能力未接线方法级）

- **Bug 代码**：:262-265/:268-280——check_file_against_contracts 零生产调用（code_tasks.py:170 import 但用 contracts.check_file 方法链，双路径并存）；get_applicable_rules 零调用。
- **影响**：与 GRD7/ASK1 同族——便捷函数层能力未接线；helpers.py 知识库注入的 to_dict 规则**只给 LLM 看**——LLM 是否按正则串规则自主约束行为无机制验证（规则执行与规则知识两轨分离）。

### GC5 [P3] 规则硬编码 + allowed_changes 死字段 + NOTICE 规则空操作（MCP1/SCT6 家族）

- **Bug 代码**：:45-175 `_load_default_rules` 硬编码 10 条规则——无 YAML/DB 外部化（改规则需改代码重发布）；:25 `allowed_changes` 白名单字段定义但 :202-226 检查逻辑从不引用——白名单机制从未实现；GC-009/GC-010（NOTICE 级）protected_patterns=[] → existence 循环空迭代 → **永不产生违规**——两条规则是空操作占位。
- **影响**：规则治理无配置化途径；「允许变更的白名单」设计承诺未落地；两条 NOTICE 规则形同虚设。

### GC6 [P3] 保护项子串匹配语义失真——GC-003 保护 "id" 恒不触发（FCT3/PP8 家族）

- **Bug 代码**：:205 `pattern not in content` 子串匹配——GC-003 protected_patterns 含 "id"（:94）——任何 models 代码几乎必含 "id" 子串（identifier/id_ 变量/id 字段）→ **GC-003 实际永不触发**；反之若字段真被删除但文件其他位置残留 "id" 子串 → 同样不触发。GC-001 同理 "hash_password" 等较长 token 若被删则子串消失会触发（较长 token 相对可靠）——但超短 token（"id"、"role"）保护恒失效。
- **影响**：超短保护项的存在性检查形同虚设（恒通过），与「保护字段删除」的目标背道而驰。

## 4. 演化方向

守护合约是**真实接线**的防护层（区别于 GRD1/ASK1 的未接线），核心问题在语义与强制力：
- **语义修复**（GC1/GC3/GC6）：check_file 需传变更前基线（diff 感知——删除保护项/签名变更才有意义）；「signature」检查需解析 AST 比对函数签名（参数名/个数/默认值）而非正则前缀匹配；超短保护项（"id"）改为精确符号匹配或字段级白名单
- **强制力决策**（GC2）：CRITICAL 违规应阻断修改流程（code_tasks Step 5 抛异常/要求用户确认回调），与「守护合约」承诺对齐——或显式声明「仅提示」降级为建议（当前是隐式放行）
- **规则外部化**（GC5）：迁移 YAML（复用 configs/ 目录模式）+ allowed_changes 白名单实现 + 移除/实现 NOTICE 空操作
- **收敛**（GC4）：便捷函数与 code_tasks 方法链统一单一入口；知识库注入的 to_dict 补充「强制力语义」（哪些违规会阻断）

## 5. 主线关联

- **DGV1 违规放行家族**：GC2（违规只记录不阻断）与 DR2（docker 安全扫描只告警）/SCM2（健康失败当通过）/GRD3（磁盘检查失败放行）同族——**防护层全线「检测不拦截」**：注入检测（GRD1 未接线）、路径安全（FCT 承担）、守护合约（GC2 记录不阻断）——三条防护轨道的共同失效模式
- **假阳性家族**：GC1（无基线误报删除）/GC6（"id" 恒不触发）加入 TR1/MAR8/PP8 判定失真族
- **能力未接线方法级**：GC4（便捷函数零消费）+ GC5（allowed_changes 死字段）加入 GRD7/ASK1/SCT6 家族
- **接线状态分档新基准**：guard_contracts 是**活跃接线**模块（code_tasks:243 真实执行）——与 guardrails（2/6 接线）、agent_skills（0/5 接线）形成「防护层接线度」三分：活跃/部分/全死——守护合约是唯一真实执行的防护，但执行结果不阻断（GC2）使其效力归零

## 6. 测试状态

- **零单元测试**：tests/ 下无任何 GuardContracts/check_file_against_contracts 引用
- GC1 误报判定、GC3 签名漏报、GC6 恒不触发均无测试约束——守护合约 10 条规则的真实触发行为无任何验证（修复时建议：以规则为 fixture 建参数化测试——每条规则构造「删除/签名变更/保留」三态样本断言违规语义）
